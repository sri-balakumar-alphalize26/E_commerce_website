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

plus `modes`, `movedToExpress`, `movedWhy` and `branch` (below).

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

from odoo import api, models

# A product is Express if it carries a delivery promise, exactly as the app
# decides it: `groups[p.delivery ? "all" : "quick"]`.
QUICK, EXPRESS = 'quick', 'all'


class Mart369Cart(models.AbstractModel):
    _name = 'mart369.cart'
    _description = '369 Mart Bill'

    # ------------------------------------------------------------- reading

    @api.model
    def _mart369_resolve(self, items):
        """{'41': 2, 'f3': 1} -> [(template, qty)], unknown ids dropped.

        Ids arrive as strings because that is what the card carries and what
        the app compares with ===. Anything that is not a published product is
        dropped rather than refused: a basket that has sat in a browser for a
        week should still check out with what is left in it.
        """
        wanted = {}
        for key, qty in (items or {}).items():
            try:
                pid, count = int(key), int(qty)
            except (TypeError, ValueError):
                continue
            if count > 0:
                wanted[pid] = wanted.get(pid, 0) + count
        if not wanted:
            return []

        templates = self.env['product.template'].sudo().search([
            ('id', 'in', list(wanted)), ('is_published', '=', True),
        ])
        return [(tmpl, wanted[tmpl.id]) for tmpl in templates]

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
        Branch = self.env['stock.warehouse'].sudo()
        any_ready = any(b._mart369_ready()
                        for b in Branch.search([('mart369_quick', '=', True)]))
        lat, lng = address.partner_latitude, address.partner_longitude
        if any_ready and (lat or lng):
            where['branches'] = Branch._mart369_quick_branches(lat, lng)
            if not where['branches']:
                where['reason'] = 'far'
            return where
        area = self.env['mart369.service.area']._mart369_match(address.zip)
        if area:
            where['area_quick'] = bool(area.quick)
            if not area.quick:
                where['reason'] = 'area'
        return where

    @api.model
    def _mart369_mode_of(self, product, qty=1, where=None):
        """(mode, branch) for one line. `branch` is the one that would hand it
        over, when Quick came from a branch; otherwise an empty recordset."""
        none = self.env['stock.warehouse'].browse()
        if product.mart_delivery_text:
            return EXPRESS, none
        where = where or {}
        if where.get('branches') is not None:
            for branch, __ in where['branches']:
                if branch._mart369_has_stock(product, qty):
                    return QUICK, branch
            return EXPRESS, none
        if where.get('area_quick') is not None:
            return (QUICK if where['area_quick'] else EXPRESS), none
        return QUICK, none

    # ---------------------------------------------------------- the totals

    @api.model
    def _mart369_bill(self, items, coupon=None, slot_fee=0.0, address=None):
        """The whole bill, in the shape the cart page prints.

        `address` is a res.partner the caller has already checked belongs to
        the customer; see the module docstring for what it changes."""
        Rule = self.env['mart369.delivery.rule']
        rules = Rule._mart369_rules()
        lines = self._mart369_resolve(items)

        price_ctx = self.env['mart369.serializable'].sudo()._price_context_for(
            self.env['product.template'].sudo().browse([t.id for t, __ in lines]))

        mrp = gross = 0.0
        sub = {QUICK: 0.0, EXPRESS: 0.0}
        present = {QUICK: False, EXPRESS: False}
        count = 0
        where = self._mart369_where(address)
        modes = {}
        branches = self.env['stock.warehouse'].browse()
        moved = 0

        for tmpl, qty in lines:
            entry = price_ctx.get(tmpl.id) or {}
            price = entry.get('price')
            if price is None:
                price = tmpl.list_price
            was = entry.get('mrp') or price

            mode, branch = self._mart369_mode_of(tmpl, qty, where)
            modes[str(tmpl.id)] = mode
            branches |= branch
            if mode == EXPRESS and not tmpl.mart_delivery_text:
                moved += 1
            present[mode] = True
            sub[mode] += price * qty
            gross += price * qty
            mrp += was * qty
            count += qty

        # One delivery fee per storefront, waived once that storefront's own
        # subtotal clears its free-delivery line. Two can stack, which is what
        # the app does when a basket mixes Quick and Express.
        fees = 0.0
        for mode in (QUICK, EXPRESS):
            rule = rules.get(mode)
            if rule and present[mode] and sub[mode] < (rule.free_above or 0.0):
                fees += rule.fee or 0.0
        fees += max(0.0, slot_fee or 0.0)

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

        quick_rule = rules.get(QUICK)
        blocked = bool(present[QUICK] and quick_rule
                       and sub[QUICK] < (quick_rule.min_order or 0.0))

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
            # does, but not with this item), 'area' (the pincode is Express).
            'movedToExpress': moved,
            'movedWhy': (where['reason'] or 'stock') if moved else '',
            'branch': branches[:1].name or '',
        }

    @api.model
    def _mart369_unknown(self, items, lines):
        """Ids the basket asked for that no longer exist or are unpublished.

        Sent so the app can tell the customer which line vanished, rather than
        quietly charging a smaller total than the basket showed.
        """
        found = {str(tmpl.id) for tmpl, __ in lines}
        return [str(key) for key in (items or {}) if str(key) not in found]
