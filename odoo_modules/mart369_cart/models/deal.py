"""Deals - a price cut on chosen products, for a window.

Not a coupon. A coupon is typed at the cart and works on basket sums; it can
never make a *card* cheaper, and a shopper browsing has no idea it exists. A
deal is the opposite: the price on the card is already lower, for everybody,
whether or not they know why.

**Where the discount is applied, and why here.**

Every price the app ever shows goes through one function - `_price_context_for`
on `mart369.serializable`. The card calls it, the cart bill calls it, and
placing an order calls it to write `price_unit`. Three surfaces, one pricer,
so they cannot disagree. A deal hooks into exactly that function.

The obvious Odoo answer would be a dated `product.pricelist.item`, and it was
the first plan. Two things ruled it out here:

* This database carries three pricelists all called "Default", none bound to
  the website and none selectable. Which one a shopper is served is resolved
  per request off their partner record, so writing items to one of them is a
  coin toss - and a deal that silently never applies is the worst possible
  failure for a feature about money.
* `_get_sales_prices` reads `request.pricelist`, so it only works inside an
  HTTP request. Outside one - tests, crons, the shell - it raises and the
  pricer quietly falls back to the list price. A pricelist deal would be
  invisible to every one of those.

Applying the cut here costs one thing worth stating plainly: Odoo's own
`/shop` and the sale order form do not know about it. Neither is used - this
storefront is the app, and `_mart369_write_lines` already bypasses Odoo's line
pricing to write `price_unit` from this same pricer.

**The window is read, never scheduled.** Like a saved home page and unlike a
cron, a deal is live because the dates say so at the moment somebody asks. It
is therefore right even if nobody was awake at midnight, and right even if the
server was down when the window opened.
"""

import logging
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

KIND_CHOICES = [
    ('percent', 'Percentage off'),
    ('amount', 'Amount off'),
]


class Mart369Deal(models.Model):
    _name = 'mart369.deal'
    _description = '369 Mart Deal'
    _order = 'sequence, id'

    sequence = fields.Integer(default=10)
    name = fields.Char(
        string='Name', required=True,
        help="What this is for, e.g. Diwali weekend. Staff see it; shoppers "
             "see the lower price, not the name.")
    note = fields.Char(
        string='Note', help="A line for whoever opens this in six months.")

    product_ids = fields.Many2many(
        'product.template', string='Products', required=True,
        help="What is on offer. A product in two live deals takes the better "
             "of the two, never both.")

    kind = fields.Selection(
        KIND_CHOICES, string='Discount', required=True, default='percent')
    value = fields.Float(
        string='Off', default=0.0,
        help="A percentage, or an amount in the shop's currency.")
    floor = fields.Float(
        string='Never below', default=0.0,
        help="A price the discount will not take a product under. 0 for no "
             "floor. A deal can never make anything free.")

    starts_on = fields.Datetime(
        string='Starts', help="Empty means it is on as soon as it is switched on.")
    ends_on = fields.Datetime(
        string='Ends', help="Empty means it runs until you switch it off.")

    active = fields.Boolean(default=True)

    # Removing a deal puts it here first. Not `active`: switching a deal off
    # is something an operator does on purpose and undoes on purpose, while
    # removing one starts a clock. One flag cannot mean both.
    deleted_at = fields.Datetime(
        string='Moved to Trash', index=True, copy=False,
        help="When it was removed. It waits here before it goes for good.")
    trash_days_left = fields.Integer(
        string='Days left', compute='_compute_trash_days_left')

    product_count = fields.Integer(
        string='Products', compute='_compute_product_count', store=True,
        help="Stored so a list can sort and filter on it.")
    live = fields.Boolean(
        string='On right now', compute='_compute_live',
        search='_search_live',
        help="Switched on, and inside its window.")

    @api.model
    def _mart369_trash_days(self):
        """How long the Trash keeps a deal. 0 means keep until deleted.

        `trash_days` is added to `mart369.config` by mart369_home, which this
        module does not depend on - so it is read only if it is there, and
        falls back to the same thirty days that module defaults to.
        """
        config = self.env['mart369.config'].sudo()._get()
        if 'trash_days' in config._fields:
            return config._trash_days()
        return 30

    @api.depends('deleted_at')
    def _compute_trash_days_left(self):
        keep = self._mart369_trash_days()
        now = fields.Datetime.now()
        for deal in self:
            if not deal.deleted_at or not keep:
                deal.trash_days_left = 0
                continue
            left = (deal.deleted_at + timedelta(days=keep)) - now
            # Rounded up: "0 days left" on something that still has hours
            # reads as "already gone".
            deal.trash_days_left = max(0, -(-left.total_seconds() // 86400))

    def action_trash(self):
        """To the Trash, not gone."""
        self.write({'deleted_at': fields.Datetime.now()})
        return True

    def action_restore(self):
        """Back out of it, exactly as it went in - including switched off."""
        self.write({'deleted_at': False})
        return True

    def _kept(self):
        return self.filtered(lambda d: not d.deleted_at)

    def _trashed(self):
        return self.filtered(lambda d: d.deleted_at)

    @api.depends('product_ids')
    def _compute_product_count(self):
        for deal in self:
            deal.product_count = len(deal.product_ids)

    @api.depends('active', 'starts_on', 'ends_on', 'deleted_at')
    def _compute_live(self):
        """A deal in the Trash is never live.

        Put here rather than at each call site on purpose. `live` is what the
        pricer, the offers page, the home row and the cache edges all read, so
        a deal that is removed has to stop changing prices in one move - a
        removed deal that still discounts things is the worst failure this
        feature has.
        """
        now = fields.Datetime.now()
        for deal in self:
            deal.live = bool(
                deal.active
                and not deal.deleted_at
                and (not deal.starts_on or deal.starts_on <= now)
                and (not deal.ends_on or deal.ends_on >= now))

    def _search_live(self, operator, value):
        """So a screen can ask for the ones running, in one query."""
        if operator not in ('=', '!=') or not isinstance(value, bool):
            raise ValidationError(self.env._(
                'On right now can only be searched as true or false.'))
        now = fields.Datetime.now()
        wanted = (operator == '=') == value
        if wanted:
            return [
                ('active', '=', True),
                ('deleted_at', '=', False),
                '|', ('starts_on', '=', False), ('starts_on', '<=', now),
                '|', ('ends_on', '=', False), ('ends_on', '>=', now),
            ]
        return [
            '|', '|', '|', ('active', '=', False),
            ('deleted_at', '!=', False),
            ('starts_on', '>', now),
            ('ends_on', '<', now),
        ]

    @api.constrains('kind', 'value')
    def _check_value(self):
        for deal in self:
            if deal.kind == 'percent' and not (0 < deal.value <= 90):
                raise ValidationError(self.env._(
                    'A percentage deal has to be between 1 and 90. Anything '
                    'more and the shop is paying people to take things.'))
            if deal.kind == 'amount' and deal.value <= 0:
                raise ValidationError(self.env._(
                    'An amount deal has to take something off.'))

    # ------------------------------------------------------------ the prices

    @api.model
    def _mart369_live_deals(self):
        """Every deal running right now, cheapest lookup first.

        One search per pricing pass rather than one per product: the pricer
        runs over a whole page of cards at a time, and a query per card is
        the quickest way to make a listing slow.
        """
        return self.sudo().search([('live', '=', True)])

    def _mart369_apply(self, price):
        """This deal's price for something currently priced at `price`."""
        self.ensure_one()
        if price <= 0:
            return price
        if self.kind == 'percent':
            cut = price * (self.value or 0.0) / 100.0
        else:
            cut = self.value or 0.0
        out = price - cut
        if self.floor:
            out = max(out, self.floor)
        # Never free, never negative, whatever the numbers say.
        return max(out, 0.01) if out < 0.01 else out

    @api.model
    def _mart369_price_map(self, templates):
        """{template_id: discounted price} for whichever of these are on offer.

        Only the products a deal actually names appear, so the caller can tell
        "no deal" from "a deal that happens to change nothing".

        A product caught by two live deals gets the better one, not both -
        stacking is how a shop ends up selling at a loss because two people
        each set up a sensible-looking offer.
        """
        deals = self._mart369_live_deals()
        if not deals or not templates:
            return {}
        listed = {t.id: t.list_price for t in templates}
        out = {}
        for deal in deals:
            for tmpl in deal.product_ids:
                was = listed.get(tmpl.id)
                if was is None:
                    continue
                priced = deal._mart369_apply(was)
                out[tmpl.id] = min(out.get(tmpl.id, was), priced)
        # Anything a deal named but did not actually make cheaper is dropped,
        # so a card never draws a strike-through over the same number.
        return {tid: price for tid, price in out.items()
                if price < (listed.get(tid) or 0.0)}

    @api.model
    def _mart369_product_ids(self):
        """Which products are on offer right now, for the offers page.

        This is the whole reason a deal is a record rather than a rule: you
        cannot ask a price "which products are cheap today", but you can ask
        this.
        """
        deals = self._mart369_live_deals()
        return deals.product_ids.ids if deals else []

    @api.model
    def _mart369_next_edge(self):
        """When the next window opens or closes, or None.

        Pages are cached for a while. Without this a card cached a minute
        before a deal starts still shows the old price after it has started,
        while the cart - which is never cached - already uses the new one, and
        the customer is told two different numbers.
        """
        now = fields.Datetime.now()
        edges = []
        for deal in self.sudo().search([('active', '=', True)]):
            for edge in (deal.starts_on, deal.ends_on):
                if edge and edge > now:
                    edges.append(edge)
        return min(edges) if edges else None

    @api.model
    def _cron_purge_deals(self):
        """Empty the Trash of anything past its retention. Runs nightly.

        Its own cron rather than mart369_home's, which sweeps the home page
        models: this module does not depend on that one, and a shop can
        install either without the other.
        """
        keep = self._mart369_trash_days()
        if not keep:
            return 0
        cutoff = fields.Datetime.now() - timedelta(days=keep)
        gone = self.with_context(active_test=False).search([
            ('deleted_at', '!=', False), ('deleted_at', '<', cutoff)])
        count = len(gone)
        gone.unlink()
        if count:
            _logger.info('369 Mart: emptied %s deal(s) from the Trash', count)
        return count

    # ------------------------------------------------------------ the demo

    @api.model
    def _mart369_load_demo(self):
        """Two deals to look at, built from whatever catalogue is installed.

        Called from `data/deal_demo.xml` rather than being records there,
        because a deal needs products and this module does not ship any. An
        XML `ref` to a demo product would tie `mart369_cart` to whichever
        catalogue module happened to be installed, and break the load for
        anyone who installs it against their own.

        Does nothing if there is already a deal, so upgrading a shop that has
        set up its own never sprouts examples.
        """
        if self.with_context(active_test=False).search_count([]):
            return False
        products = self.env['product.template'].search(
            [('is_published', '=', True), ('list_price', '>', 0)], limit=8)
        if len(products) < 2:
            # Nothing to put on offer. An empty shop gets the empty state,
            # which explains itself.
            return False

        half = max(1, len(products) // 2)
        self.create([{
            'name': self.env._('Weekend electronics'),
            'note': self.env._('An example - switch it off or delete it.'),
            'kind': 'percent',
            'value': 20.0,
            'product_ids': [(6, 0, products[:half].ids)],
            'ends_on': fields.Datetime.now() + timedelta(days=3),
        }, {
            'name': self.env._('Starting on Friday'),
            'note': self.env._('An example of a deal waiting for its window.'),
            'kind': 'percent',
            'value': 15.0,
            'product_ids': [(6, 0, products[half:].ids)],
            'starts_on': fields.Datetime.now() + timedelta(days=2),
        }])
        return True

    # ---------------------------------------------------------- the console

    def _mart369_admin_serialize(self):
        self.ensure_one()
        return {
            'id': self.id,
            'name': self.name or '',
            'note': self.note or '',
            'kind': self.kind or 'percent',
            'value': self.value or 0.0,
            'floor': self.floor or 0.0,
            'active': self.active,
            'live': self.live,
            'startsOn': fields.Datetime.to_string(self.starts_on) if self.starts_on else None,
            'endsOn': fields.Datetime.to_string(self.ends_on) if self.ends_on else None,
            'deletedAt': (fields.Datetime.to_string(self.deleted_at)
                          if self.deleted_at else None),
            'daysLeft': self.trash_days_left,
            'productCount': self.product_count,
            'products': [
                {'id': t.id, 'name': t.name,
                 'price': t.list_price,
                 'dealPrice': round(self._mart369_apply(t.list_price), 2)}
                for t in self.product_ids[:12]
            ],
        }

    @api.model
    def mart369_admin_list(self):
        deals = self.with_context(active_test=False).search([])
        kept = deals._kept()
        rows = [d._mart369_admin_serialize() for d in kept]
        return {
            'deals': rows,
            # Kept and trashed come back apart, so neither screen has to
            # remember to filter.
            'trash': [d._mart369_admin_serialize()
                      for d in deals._trashed().sorted(
                          key=lambda d: d.deleted_at, reverse=True)],
            'trashDays': self._mart369_trash_days(),
            'counts': {
                'all': len(rows),
                'live': sum(1 for r in rows if r['live']),
                'scheduled': sum(
                    1 for r in rows
                    if r['active'] and not r['live'] and r['startsOn']),
                'off': sum(1 for r in rows if not r['active']),
            },
            'onOffer': len(set(self._mart369_product_ids())),
            'currency': self.env['mart369.serializable']._mart369_shop_currency(),
        }
