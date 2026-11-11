"""The bill.

This is the module's reason to exist. `computeBill` in
components/home/Cart.jsx adds the basket up in the browser, from prices in the
browser's own bundle, applies a coupon whose arithmetic is a JavaScript closure,
and hands the result to the payment step. The customer's own machine decides
what it is charged.

Here the same arithmetic runs against Odoo's prices. Deliberately the *same*
arithmetic, step for step, including `Math.round` on a percentage: a bill that
disagreed with the one the app used to draw would look like a bug to everyone
who saw it, and "the server is right" is not a thing a shopper wants to read.

What is returned is what the cart page prints:

    mrp, items, sub{quick,all}, fees, couponValid, couponOff, total, saved,
    count, blocked

plus `modes`, `movedToExpress`, `movedWhy`, `branch` and `sellers` (below).

**Who sells it.** Once the shop has more than one company - one per hub -
each line also says which company sells it (`_mart369_seller`): the company
of the branch that hands it over Quick, else the product's own. The product
cards ask the same question through `_mart369_badges`.

**Quick or Express, per line.** With no address the product decides, as it
always has: a delivery promise (`mart_delivery_text`) makes it Express. With
an address, a Quick product stays Quick only if a branch that does Quick is
within its reach of the address's map pin *and* has the item in stock there
(see branch.py). An address with no pin falls back to its pincode's area. Until
a single branch is set up for Quick, and for a pincode no area covers, nothing
changes - the product decides, so switching this on is not a day when every
basket turns Express.

`groups`, `lines` and `feeFor` are not returned. The first two are the whole
product objects, which the app already holds, and the third is a function -
there is no JSON for a function. The app keeps building those itself.

On tax: the app has no tax line anywhere, so none is sent. Odoo's prices here
are what the customer pays, which is how Indian retail quotes a price. The GST
split belongs on the invoice, and that is mart369_order's job.
"""

from types import SimpleNamespace

from odoo import api, models

from .branch import has_pin, haversine_km, quick_time_text

# A product is Express if it carries a delivery promise, exactly as the app
# decides it: `groups[p.delivery ? "all" : "quick"]`.
QUICK, EXPRESS = 'quick', 'all'


class Mart369Cart(models.AbstractModel):
    _name = 'mart369.cart'
    _description = '369 Mart Bill'

    # ------------------------------------------------------------- reading

    @api.model
    def _mart369_resolve(self, items):
        """{'41': 2, 'v123': 1, 'f3': 1} -> [line], unknown ids dropped.

        Each line is {'key', 'tmpl', 'variant', 'chosen', 'qty'}. A plain
        number is a product and sells its first variant, as it always has;
        'v123' is the variant the customer picked on the product page (Brand,
        RAM, Colour). `chosen` lines are priced and named as their variant:
        every 'v123', and a plain number whose product has variants by now (a
        basket from before they were added), so its first variant is not sold
        at the product's price without its extras.

        Ids arrive as strings because that is what the card carries and what
        the app compares with ===. Anything that is not a published product is
        dropped rather than refused: a basket that has sat in a browser for a
        week should still check out with what is left in it.
        """
        Mixin = self.env['mart369.serializable']
        wanted = {}
        for key, qty in (items or {}).items():
            parsed = Mixin._mart369_parse_key(key)
            try:
                count = int(qty)
            except (TypeError, ValueError):
                continue
            if parsed and count > 0:
                wanted[parsed] = wanted.get(parsed, 0) + count
        if not wanted:
            return []

        templates = self.env['product.template'].sudo().search([
            ('id', 'in', [i for kind, i in wanted if kind == 'template']),
            ('is_published', '=', True),
        ])
        variants = Mixin._mart369_published_variants(
            [i for kind, i in wanted if kind == 'variant'])
        lines = [{'key': str(tmpl.id), 'tmpl': tmpl, 'variant': tmpl.product_variant_id,
                  'chosen': len(tmpl.product_variant_ids) > 1,
                  'qty': wanted[('template', tmpl.id)]}
                 for tmpl in templates]
        lines += [{'key': Mixin._mart369_variant_key(v), 'tmpl': v.product_tmpl_id,
                   'variant': v, 'chosen': True, 'qty': wanted[('variant', v.id)]}
                  for v in variants]
        return lines

    @api.model
    def _mart369_line_prices(self, lines):
        """{key: {'price', 'mrp'}} for resolved lines, in one pricing pass:
        a picked variant pays its own extras, a plain product its card price."""
        Mixin = self.env['mart369.serializable'].sudo()
        tmpl_ctx = Mixin._price_context_for(
            self.env['product.template'].sudo().union(*[l['tmpl'] for l in lines]))
        chosen = self.env['product.product'].sudo().union(
            *[l['variant'] for l in lines if l['chosen']])
        variant_ctx = Mixin._price_context_for_variants(chosen) if chosen else {}
        out = {}
        for line in lines:
            if line['chosen']:
                out[line['key']] = variant_ctx.get(line['variant'].id) or {}
            else:
                out[line['key']] = tmpl_ctx.get(line['tmpl'].id) or {}
        return out

    @api.model
    def _mart369_where(self, address):
        """What the per-line rule needs to know about an address, worked out
        once per bill rather than once per line.

        {'branches': [(branch, km)] or None, 'area_quick': bool or None,
         'reason': str}. None means "no opinion": fall back to the product.
        """
        where = {'branches': None, 'area_quick': None, 'reason': ''}
        if not address:
            return where
        hubs = self._mart369_hub_where(address)
        if hubs:
            return hubs
        Branch = self.env['stock.warehouse'].sudo()
        any_ready = any(b._mart369_ready()
                        for b in Branch.search([('mart369_quick', '=', True)]))
        lat, lng = address.partner_latitude, address.partner_longitude
        if any_ready and (lat or lng):
            where['branches'] = Branch._mart369_quick_branches(lat, lng)
            if not where['branches']:
                where['reason'] = 'far'
            return where
        if any_ready:
            # Branches decide Quick by distance now, and a pincode alone has
            # none to measure: Express, and the shop asks for the location.
            # A shop with no branch set up keeps the area's own switch below.
            where['area_quick'] = False
            where['reason'] = 'nopin'
            return where
        area = self.env['mart369.service.area']._mart369_match(address.zip)
        if area:
            where['area_quick'] = bool(area.quick)
            if not area.quick:
                where['reason'] = 'area'
        return where

    @api.model
    def _mart369_mode_of(self, product, qty=1, where=None, variant=None):
        """(mode, branch) for one line. `branch` is the one that would hand it
        over, when Quick came from a branch; otherwise an empty recordset.
        `variant`, when the customer picked one, is the stock that counts."""
        none = self.env['stock.warehouse'].browse()
        where = where or {}
        if where.get('hubs') is not None:
            offer = self._mart369_hub_offer(product, qty, where, variant=variant)
            return offer['mode'], offer['branch']
        if self._mart369_express_only(product):
            return EXPRESS, none
        if where.get('branches') is not None:
            for branch, __ in where['branches']:
                if product.company_id and branch.company_id != product.company_id:
                    continue    # another company's product is not this branch's
                if branch._mart369_has_stock(product, qty, variant=variant):
                    return QUICK, branch
            return EXPRESS, none
        if where.get('area_quick') is not None:
            return (QUICK if where['area_quick'] else EXPRESS), none
        return QUICK, none

    @api.model
    def _mart369_express_only(self, product):
        """A product with its own delivery promise never goes Quick."""
        return bool(product.mart_delivery_text)

    # ------------------------------------------------------------- the hubs

    @api.model
    def _mart369_hub_where(self, address):
        """The hub rules' view of an address, or None to use the old rule.

        On only when the hub table has a row (hub_rule.py) and the address
        has a map pin. Every branch with a pin is a hub, measured from the
        address, nearest first; the nearest is the customer's own hub.
        """
        table = self.env['mart369.hub.rule']._mart369_table()
        if not table:
            return None
        lat, lng = address.partner_latitude, address.partner_longitude
        if not has_pin(lat, lng):
            return None
        hubs = sorted(
            ((b, haversine_km(lat, lng, b.mart369_lat, b.mart369_lng))
             for b in self.env['stock.warehouse'].sudo().search([])
             if has_pin(b.mart369_lat, b.mart369_lng)),
            key=lambda pair: pair[1])
        if not hubs:
            return None
        reaches = any(b._mart369_ready() and km <= b.mart369_quick_km for b, km in hubs)
        return {'branches': None, 'area_quick': None, 'reason': '' if reaches else 'far',
                'hubs': hubs, 'home': hubs[0][0], 'table': table}

    @api.model
    def _mart369_hub_tier(self, branch, km, home, table):
        """How this branch would deliver to an address `km` away, whose own
        hub is `home`: {'mode', 'when', 'cargo', 'maybe', 'rank'}.

        Close enough for its Quick reach: Quick, in a time worked out from
        the distance (branch.quick_time_text - 10 mins to pack, 5 a km).
        Up to its "Quick if possible" reach: Express, which may come Quick.
        Otherwise the table: its row for (this branch, the customer's hub), or
        plain Express when no row says how. `rank` picks between hubs - Quick
        first, then the fewest days, then the nearest.
        """
        if branch._mart369_ready() and km <= branch.mart369_quick_km:
            return {'mode': QUICK, 'when': quick_time_text(km), 'cargo': False,
                    'maybe': False, 'rank': (0, 0, km)}
        row = table.get((branch.id, home.id))
        when = (row.arrives or '') if row else ''
        cargo = bool(row and row.cargo)
        days = row.days if row else 99
        if branch.mart369_maybe_km and km <= branch.mart369_maybe_km:
            return {'mode': EXPRESS, 'when': when, 'cargo': cargo, 'maybe': True,
                    'rank': (1, days, km)}
        return {'mode': EXPRESS, 'when': when, 'cargo': cargo, 'maybe': False,
                'rank': (2, days, km)}

    @api.model
    def _mart369_hub_offer(self, product, qty, where, variant=None):
        """The best way to get this item to the address, from any hub that
        has it: {'mode', 'branch', 'when', 'cargo', 'maybe'}. The customer's
        own hub out of stock? The next hub steps in. No hub has it: Express,
        as before, from nobody in particular."""
        none = self.env['stock.warehouse'].browse()
        home = where['home']
        held = []           # every hub that has it, as it would deliver
        for branch, km in where['hubs']:
            if product.company_id and branch.company_id != product.company_id:
                # Another company's product is not this branch's to sell.
                continue
            if not branch._mart369_has_stock(product, qty, variant=variant):
                continue
            held.append(dict(self._mart369_hub_tier(branch, km, home, where['table']),
                             branch=branch))
        held.sort(key=lambda offer: offer['rank'])
        # Where it is in stock, fastest first, for the product page:
        # "Not in stock at Ruwi, your nearest branch. In stock at Sohar (Next day)".
        stock_at = [{'name': o['branch'].company_id.name or o['branch'].name or '',
                     'mode': o['mode'], 'when': o['when'], 'cargo': o['cargo']}
                    for o in held]
        at_home = any(o['branch'] == home for o in held)
        if not held:
            return {'mode': EXPRESS, 'branch': none, 'when': '', 'cargo': False, 'maybe': False,
                    'stockAt': [], 'home': home, 'atHome': False}
        best = dict(held[0], stockAt=stock_at, home=home, atHome=at_home)
        if self._mart369_express_only(product):
            # Its own promise wins; the hub still decides who sells it.
            best.update(mode=EXPRESS, when=product.mart_delivery_text, maybe=False)
        best.pop('rank', None)
        return best

    @api.model
    def _mart369_offer_notes(self, offer):
        """What a card or a cart line adds from the hub rules, only what is
        set: {'when': 'Next day', 'cargo': True, 'maybe': True}. Empty while
        the hub rules are off, so the shop shows what it always did."""
        notes = {}
        if offer.get('when'):
            notes['when'] = offer['when']
        if offer.get('cargo'):
            notes['cargo'] = True
        if offer.get('maybe'):
            notes['maybe'] = True
        return notes

    @api.model
    def _mart369_offer(self, product, qty=1, where=None, variant=None):
        """{'mode', 'branch', 'when'?, 'cargo'?, 'maybe'?} for one line: the
        hub rules' full answer when they are on, else `_mart369_mode_of`'s
        (ours or the WhatsApp bridge's)."""
        where = where or {}
        if where.get('hubs') is not None:
            return self._mart369_hub_offer(product, qty, where, variant=variant)
        mode, branch = self._mart369_mode_of(product, qty, where, variant=variant)
        return {'mode': mode, 'branch': branch}

    # ------------------------------------------------------------ the seller

    @api.model
    def _mart369_sellers_on(self):
        """"Sold by" means something only once the shop has more than one
        company (one per hub: Ruwi, Sohar, Salalah). A one-company shop shows
        no seller anywhere, exactly as before."""
        return self.env['res.company'].sudo().search_count([]) > 1

    @api.model
    def _mart369_seller(self, product, branch=None):
        """{'id', 'name'} of the company that sells this line.

        The branch that would hand it over Quick decides first - a
        `stock.warehouse` here, or the bridge's `sa.delivery.shop`, whose
        company is its warehouse's. Otherwise the product's own company, and a
        product shared by every company is sold by the shop's own.
        """
        company = self.env['res.company']
        if branch:
            if 'company_id' in branch._fields:
                company = branch.company_id
            elif 'warehouse_id' in branch._fields:
                company = branch.warehouse_id.company_id
        # A product that belongs to one company is only ever that company's.
        company = product.company_id or company or self.env.company
        company = company.sudo()
        return {'id': company.id, 'name': company.name or ''}

    @api.model
    def _mart369_badges(self, keys, address=None, pin=None):
        """What each product card says about delivery, for this customer.

        {'sellers': bool, 'badges': {key: {'mode', 'eta'?, 'seller'?}}}

        The same rule as the bill, one item at a time, so a card and the cart
        never disagree. With no address, a pincode alone still counts (a guest
        who only typed one); with neither, the product decides, as it always
        has. Keys that are not published products are left out.
        """
        keys = [str(k).strip() for k in (keys or []) if str(k).strip()]
        if not address and pin:
            # Never saved: both versions of `_mart369_where` (ours and the
            # WhatsApp bridge's) only read a pin and a pincode off it.
            address = self.env['res.partner'].new({'zip': str(pin).strip()})
        where = self._mart369_where(address)
        rules = self.env['mart369.delivery.rule']._mart369_rules()
        sellers = self._mart369_sellers_on()
        badges = {}
        for line in self._mart369_resolve({key: 1 for key in keys}):
            tmpl = line['tmpl']
            offer = self._mart369_offer(tmpl, 1, where, variant=line['variant'])
            mode, branch = offer['mode'], offer['branch']
            entry = {'mode': mode}
            rule = rules.get(mode)
            eta = (tmpl.mart_delivery_text if self._mart369_express_only(tmpl)
                   else (rule.eta if rule else '')) or ''
            if eta:
                entry['eta'] = eta
            entry.update(self._mart369_offer_notes(offer))
            if sellers:
                entry['seller'] = self._mart369_seller(tmpl, branch)
            if 'stockAt' in offer:
                # Hub rules on: which hubs hold it, and whether the customer's
                # own (nearest) one does - the product page names them.
                entry['stockAt'] = offer['stockAt']
                entry['home'] = offer['home'].company_id.name or offer['home'].name or ''
                entry['atHome'] = offer['atHome']
            badges[line['key']] = entry
        return {'sellers': sellers, 'badges': badges}

    @api.model
    def _mart369_fees(self, rules, present, sub, gross, slot_fee):
        """The delivery fee for this basket.

        One fee per storefront, waived once that storefront's own subtotal
        clears its free-delivery line - two can stack, which is what the app
        does when a basket mixes Quick and Express - plus the slot's.
        """
        fees = 0.0
        for mode in (QUICK, EXPRESS):
            rule = rules.get(mode)
            if rule and present[mode] and sub[mode] < (rule.free_above or 0.0):
                fees += rule.fee or 0.0
        return fees + max(0.0, slot_fee or 0.0)

    @api.model
    def _mart369_blocked(self, rules, present, sub, gross):
        """A Quick basket under the Quick minimum cannot be ordered."""
        quick_rule = rules.get(QUICK)
        return bool(present[QUICK] and quick_rule
                    and sub[QUICK] < (quick_rule.min_order or 0.0))

    # ---------------------------------------------------------- the totals

    @api.model
    def _mart369_bill(self, items, coupon=None, slot_fee=0.0, address=None):
        """The whole bill, in the shape the cart page prints.

        `address` is a res.partner the caller has already checked belongs to
        the customer; see the module docstring for what it changes."""
        Rule = self.env['mart369.delivery.rule']
        rules = Rule._mart369_rules()
        lines = self._mart369_resolve(items)
        price_ctx = self._mart369_line_prices(lines)

        mrp = gross = 0.0
        sub = {QUICK: 0.0, EXPRESS: 0.0}
        present = {QUICK: False, EXPRESS: False}
        count = 0
        where = self._mart369_where(address)
        modes = {}
        branches = []           # who would hand each Quick line over, by name
        moved = 0
        sellers_on = self._mart369_sellers_on()
        sellers = {}            # which company sells each line, when there are several
        notes = {}              # the hub rules' when / cargo / maybe, per line
        rows = []               # (seller, branch, key, qty, mode, value) for the parts

        for line in lines:
            tmpl, qty = line['tmpl'], line['qty']
            entry = price_ctx.get(line['key']) or {}
            price = entry.get('price')
            if price is None:
                price = tmpl.list_price
            was = entry.get('mrp') or price

            # The variant the order will sell - picked, or the product's first
            # - is the stock that counts, never its siblings' together.
            offer = self._mart369_offer(tmpl, qty, where, variant=line['variant'])
            mode, branch = offer['mode'], offer['branch']
            modes[line['key']] = mode
            line_notes = self._mart369_offer_notes(offer)
            if line_notes:
                notes[line['key']] = line_notes
            if sellers_on:
                sellers[line['key']] = self._mart369_seller(tmpl, branch)
                rows.append((sellers[line['key']], branch, line['key'], qty, mode, price * qty))
            # The hub rules also name the hub an Express line ships from;
            # `branch` stays what it always was - who hands a Quick line over.
            if branch and mode == QUICK and branch.name not in branches:
                branches.append(branch.name)
            if mode == EXPRESS and not self._mart369_express_only(tmpl):
                moved += 1
            present[mode] = True
            sub[mode] += price * qty
            gross += price * qty
            mrp += was * qty
            count += qty

        parts = (self._mart369_parts(rows, rules)
                 if sellers_on and self._mart369_split_allowed() else [])
        if parts:
            # One delivery per seller, each at that hub's own fees (or the
            # shop's), and the slot's fee once.
            fees = sum(p['fees'] for p in parts) + max(0.0, slot_fee or 0.0)
        else:
            fees = self._mart369_fees(rules, present, sub, gross, slot_fee)

        sums = {'items': gross, QUICK: sub[QUICK], EXPRESS: sub[EXPRESS], 'fees': fees}

        # Every live code priced against this basket, so the coupon sheet can
        # say what each one saves without the browser knowing how a discount
        # is worked out - the same reason `calc` is not in a coupon's payload.
        Coupon = self.env['mart369.coupon'].sudo()
        offers = []
        for record in Coupon.search([]):
            if not record._mart369_live():
                continue
            offers.append({
                'code': record.code or '',
                'off': round(record._mart369_discount(sums), 2),
                'need': round(max(0.0, (record.min_spend or 0.0)
                                  - record._mart369_base(sums)), 2),
            })

        coupon_record = self.env['mart369.coupon']._mart369_find(coupon)
        coupon_off = coupon_record._mart369_discount(sums) if coupon_record else 0.0
        coupon_valid = bool(coupon_record) and coupon_off > 0

        blocked = self._mart369_blocked(rules, present, sub, gross)

        total = max(0.0, gross + fees - coupon_off)
        return {
            'mrp': round(mrp, 2),
            'items': round(gross, 2),
            'sub': {'quick': round(sub[QUICK], 2), 'all': round(sub[EXPRESS], 2)},
            'fees': round(fees, 2),
            'coupons': offers,
            'couponValid': coupon_valid,
            'couponOff': round(coupon_off, 2),
            'total': round(total, 2),
            'saved': round(mrp - gross + coupon_off, 2),
            'count': count,
            'blocked': blocked,
            'unknown': self._mart369_unknown(items, lines),
            # Which storefront each line landed in, so the cart groups by the
            # server's answer and not by its own reading of the product.
            'modes': modes,
            # Quick items that went Express because of where they are going,
            # and why: 'far' (no Quick branch reaches the pin), 'stock' (one
            # does, but not with this item), 'area' (the pincode is Express),
            # 'nopin' (branches measure Quick and the address has no map pin).
            'movedToExpress': moved,
            'movedWhy': (where['reason'] or 'stock') if moved else '',
            'branch': branches[0] if branches else '',
            # {key: {id, name}}: who sells each line. Empty on a one-company
            # shop, where the cart shows no seller.
            'sellers': sellers,
            # {key: {when?, cargo?, maybe?}}: only lines the hub rules said
            # something about. Empty while the hub table is.
            'notes': notes,
            # A basket from two or more sellers comes as one order per seller
            # (mart369_order places them): [{seller, keys, qty, items, fees,
            # mode, hubId}]. Empty for a one-seller basket, which is one order
            # as it always was.
            'parts': [dict(p, fees=round(p['fees'], 2), items=round(p['items'], 2))
                      for p in parts] if len(parts) > 1 else [],
        }

    # ------------------------------------------------------------ the parts

    @api.model
    def _mart369_split_allowed(self):
        """Whether a basket from several sellers becomes one order per seller.
        The WhatsApp bridge's own delivery stack keeps one order per basket
        (it says so in its own override)."""
        return True

    @api.model
    def _mart369_hub_rules(self, rules, hub):
        """The delivery rules for a part a hub ships: its own fee and
        free-delivery amount when it has set them, else the shop's. The Quick
        minimum and the promise stay the shop's."""
        if not hub or not hub.mart369_own_fees:
            return rules
        out = {}
        for mode, fee in ((QUICK, hub.mart369_quick_fee), (EXPRESS, hub.mart369_express_fee)):
            base = rules.get(mode)
            out[mode] = SimpleNamespace(
                fee=fee or 0.0, free_above=hub.mart369_free_above or 0.0,
                min_order=base.min_order if base else 0.0,
                eta=base.eta if base else '', label=base.label if base else '')
        return out

    @api.model
    def _mart369_parts(self, rows, rules):
        """The basket split by seller: one entry per company, in the order the
        lines came, each with what its own delivery costs."""
        Branch = self.env['stock.warehouse'].sudo()
        groups = {}
        for seller, branch, key, qty, mode, value in rows:
            part = groups.get(seller['id'])
            if part is None:
                part = groups[seller['id']] = {
                    'seller': seller, 'keys': [], 'qty': {}, 'items': 0.0,
                    'hub': Branch.browse(),
                    'sub': {QUICK: 0.0, EXPRESS: 0.0},
                    'present': {QUICK: False, EXPRESS: False}}
            part['keys'].append(key)
            part['qty'][key] = qty
            part['items'] += value
            part['sub'][mode] += value
            part['present'][mode] = True
            if (branch and not part['hub'] and branch._name == 'stock.warehouse'
                    and branch.company_id.id == seller['id']):
                part['hub'] = branch
        out = []
        for company_id, part in groups.items():
            hub = part['hub'] or Branch.search([('company_id', '=', company_id)], limit=1)
            fees = self._mart369_fees(self._mart369_hub_rules(rules, hub), part['present'],
                                      part['sub'], part['items'], 0.0)
            out.append({
                'seller': part['seller'], 'keys': part['keys'], 'qty': part['qty'],
                'items': part['items'], 'fees': fees,
                'mode': QUICK if part['sub'][QUICK] else EXPRESS,
                'hubId': hub.id or False,
            })
        return out

    @api.model
    def _mart369_unknown(self, items, lines):
        """Ids the basket asked for that no longer exist or are unpublished.

        Sent so the app can tell the customer which line vanished, rather than
        quietly charging a smaller total than the basket showed.
        """
        found = {line['key'] for line in lines}
        return [str(key) for key in (items or {}) if str(key).strip() not in found]
