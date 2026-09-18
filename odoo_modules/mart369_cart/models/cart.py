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
    def _mart369_mode_of(self, product):
        return EXPRESS if product.mart_delivery_text else QUICK

    # ---------------------------------------------------------- the totals

    @api.model
    def _mart369_bill(self, items, coupon=None, slot_fee=0.0):
        """The whole bill, in the shape the cart page prints."""
        Rule = self.env['mart369.delivery.rule']
        rules = Rule._mart369_rules()
        lines = self._mart369_resolve(items)

        price_ctx = self.env['mart369.serializable'].sudo()._price_context_for(
            self.env['product.template'].sudo().browse([t.id for t, __ in lines]))

        mrp = gross = 0.0
        sub = {QUICK: 0.0, EXPRESS: 0.0}
        present = {QUICK: False, EXPRESS: False}
        count = 0

        for tmpl, qty in lines:
            entry = price_ctx.get(tmpl.id) or {}
            price = entry.get('price')
            if price is None:
                price = tmpl.list_price
            was = entry.get('mrp') or price

            mode = self._mart369_mode_of(tmpl)
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
            'couponValid': coupon_valid,
            'couponOff': round(coupon_off, 2),
            'total': round(total, 2),
            'saved': round(mrp - gross + coupon_off, 2),
            'count': count,
            'blocked': blocked,
            'unknown': self._mart369_unknown(items, lines),
        }

    @api.model
    def _mart369_unknown(self, items, lines):
        """Ids the basket asked for that no longer exist or are unpublished.

        Sent so the app can tell the customer which line vanished, rather than
        quietly charging a smaller total than the basket showed.
        """
        found = {str(tmpl.id) for tmpl, __ in lines}
        return [str(key) for key in (items or {}) if str(key) not in found]
