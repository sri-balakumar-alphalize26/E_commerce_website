"""Placing an order.

The one rule: **the order is priced here, and nowhere else.** The basket arrives
as a list of ids and quantities, and every number on the resulting order is
computed from Odoo's own prices through `mart369.cart._mart369_bill` - the same
code the cart page already asks for its totals, so the bill the customer was
shown and the order they get are the same arithmetic, not two implementations
that agree most of the time.

Nothing here trusts a total, a discount or a fee that came from the browser.

Order of operations, and why:

1. **Idempotency first.** The app generates its own order number and can retry
   (payment.js:75 builds it from a timestamp slice, which can collide and does
   repeat on a double tap). Placing twice with one number places once.
2. **Address before money**, so a basket cannot be priced against somebody
   else's pincode.
3. **Re-price**, and refuse a basket the cart page would have blocked.
4. **Create, then check.** After the lines are written the order's own total is
   compared with the bill's, and a disagreement raises rather than quietly
   charging the customer a number nobody showed them.

On tax: the app quotes tax-inclusive prices, the way Indian retail does, so the
order total must equal the bill total exactly. If the company has set a 369 Mart
tax it is applied **price-included** and GST is split out on the invoice; with
none set, lines carry no tax and the invoice carries no GST - which is where
things already stood, not a regression. Either way the customer pays the number
they were shown.
"""

import logging
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# What the app calls the priority fee at checkout (Checkout.jsx:26).
PRIORITY_LABEL = 'Priority delivery'


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # -------------------------------------------------------------- placing

    @api.model
    def _mart369_place(self, partner, body):
        """Turn a basket into a real order. Returns the sale.order.

        `partner` is the signed-in customer. `body` is what the app posted.
        """
        ref = (body.get('ref') or body.get('id') or '').strip()
        if not ref:
            raise UserError(self.env._('That order is missing its order number.'))

        # 1. Seen this number before?
        existing = self.sudo().search([('mart369_ref', '=', ref)], limit=1)
        if existing:
            if existing.partner_id != partner:
                # Someone else's number. Say nothing useful about it.
                raise UserError(self.env._('That order number is not available.'))
            if existing.mart369_state not in ('draft', False):
                # Paid for, or on its way. This is a retry, not a second order.
                return existing
            # Still a draft: nobody has been asked to pack it and no money has
            # moved, so it is the same basket being settled - rewrite it. The
            # app asks for the order before choosing how to pay, because
            # whether cash is allowed is a question about the order, and the
            # customer can still go back and change the slot after that.

        # 2. The address, and that it is really theirs.
        address = self._mart369_address_for(partner, body.get('address_id'))

        # 3. The bill, from Odoo's prices.
        items = body.get('items') or {}
        if not isinstance(items, dict):
            items = self._mart369_items_from_pairs(items)
        if not items:
            raise UserError(self.env._('There is nothing in this basket.'))

        slot, slot_fee = self._mart369_slot_for(body)
        # With the address, so Quick or Express is decided for where this is
        # going - near a branch that has it, or not.
        bill = self.env['mart369.cart'].sudo()._mart369_bill(
            items, coupon=body.get('coupon'), slot_fee=slot_fee, address=address)

        if bill['blocked']:
            raise UserError(self.env._(
                'This basket is below the minimum for a Quick order.'))
        if not bill['count']:
            raise UserError(self.env._('Nothing in this basket is still on sale.'))

        coupon = self.env['mart369.coupon']._mart369_find(body.get('coupon'))
        if coupon and not bill['couponValid']:
            coupon = self.env['mart369.coupon'].browse()
        if coupon:
            self._mart369_check_coupon(coupon, partner)

        # The server's answer, not the app's: which items are Quick now depends
        # on the address and the branches' stock, which the browser cannot see.
        mode = self._mart369_mode_of_bill(bill)

        # 4. The order.
        values = {
            'carrier_id': self._mart369_carrier(partner).id or False,
            'partner_id': partner.id,
            'partner_shipping_id': address.id if address else partner.id,
            'partner_invoice_id': partner.id,
            'mart369_ref': ref,
            'mart369_state': 'draft',
            'mart369_mode': mode,
            'mart369_slot_key': slot.key if slot else False,
            'mart369_slot_day': self._mart369_slot_day(slot),
            'mart369_slot_label': body.get('slot') or self._mart369_slot_label(slot),
            'mart369_eta': body.get('eta') or '',
            'mart369_instructions': (body.get('instructions') or '').strip() or False,
            'mart369_whatsapp': bool(body.get('whatsapp')),
            'mart369_coupon_id': coupon.id if coupon else False,
            'mart369_coupon_off': bill['couponOff'] if coupon else 0.0,
            'mart369_due_at': self._mart369_due_at(slot, mode),
        }
        if existing:
            order = existing
            order.order_line.sudo().unlink()
            order.write(values)
        else:
            order = self.sudo().create(values)
        order._mart369_write_lines(items, bill, coupon)
        order._mart369_check_total(bill)
        return order

    @api.model
    def _mart369_carrier(self, partner):
        """How this order is being delivered.

        Nothing set one before, and an order with no delivery method is an
        order Odoo will not take cash for: `delivery` refuses cash unless the
        carrier allows it, so every basket was quietly refused at the moment
        of paying. Prefer a carrier that does allow cash - which is the one
        the shop's own delivery is - and settle for any if none does.
        """
        Carrier = self.env['delivery.carrier'].sudo()
        usable = Carrier.search([
            '|', ('company_id', '=', False),
            ('company_id', '=', self.env.company.id),
        ])
        return next(
            (c for c in usable if c.allow_cash_on_delivery),
            usable[:1] or Carrier.browse(),
        )

    # -------------------------------------------------------------- the lines

    def _mart369_write_lines(self, items, bill, coupon):
        """Basket lines at the bill's prices, then fees, then the coupon."""
        self.ensure_one()
        Cart = self.env['mart369.cart'].sudo()
        lines = Cart._mart369_resolve(items)
        templates = self.env['product.template'].sudo().browse([t.id for t, __ in lines])
        prices = self.env['mart369.serializable'].sudo()._price_context_for(templates)
        tax = self._mart369_tax()

        values = []
        for tmpl, qty in lines:
            variant = tmpl.product_variant_id
            if not variant:
                # A template with no variant cannot be sold; the bill counted
                # it, so refuse rather than silently charge for nothing.
                raise UserError(self.env._(
                    '%s cannot be ordered right now.', tmpl.display_name))
            entry = prices.get(tmpl.id) or {}
            price = entry.get('price')
            if price is None:
                price = tmpl.list_price
            values.append({
                'order_id': self.id,
                'product_id': variant.id,
                'name': tmpl.display_name,
                'product_uom_qty': qty,
                'price_unit': price,
                'mart369_mrp': entry.get('mrp') or price,
                'tax_ids': [(6, 0, tax.ids)],
            })

        for label, amount in self._mart369_fee_lines(bill):
            values.append(self._mart369_charge_line(label, amount, 'fee', tax))

        if coupon and bill['couponOff']:
            values.append(self._mart369_charge_line(
                coupon.code, -bill['couponOff'], 'coupon', tax))

        self.env['sale.order.line'].sudo().create(values)

    def _mart369_fee_lines(self, bill):
        """The fees as the app shows them: delivery, then anything the slot added."""
        self.ensure_one()
        fees = bill.get('fees') or 0.0
        if not fees:
            return []
        return [(self.env._('Delivery'), fees)]

    def _mart369_charge_line(self, label, amount, kind, tax):
        """A fee or a discount: a real line, but not a basket item."""
        self.ensure_one()
        product = self._mart369_charge_product(kind)
        return {
            'order_id': self.id,
            'product_id': product.id,
            'name': label,
            'product_uom_qty': 1,
            'price_unit': amount,
            'mart369_kind': kind,
            'tax_ids': [(6, 0, tax.ids)],
        }

    @api.model
    def _mart369_charge_product(self, kind):
        """The service product a fee or discount line hangs off.

        The data records are templates; an order line wants the variant.
        """
        xmlid = ('mart369_order.product_delivery_fee' if kind == 'fee'
                 else 'mart369_order.product_coupon')
        template = self.env.ref(xmlid, raise_if_not_found=False)
        product = template.sudo().product_variant_id if template else None
        if not product:
            raise UserError(self.env._(
                'The 369 Mart fee products are missing. Reinstall 369 Mart Orders.'))
        return product

    # ---------------------------------------------------------------- checks

    def _mart369_check_total(self, bill):
        """The order and the bill must agree to the paisa.

        They are the same arithmetic on the same prices, so a difference means a
        tax or a price has quietly changed - and the customer would be charged
        something they were never shown.

        One exception, and only one: the order came out **cheaper** than the
        quote. That happens when a deal opens while somebody is on the payment
        screen, and refusing it would mean telling a customer their order
        failed because the shop decided to charge them less. The quote is
        honoured as the ceiling and the lower price stands.

        Dearer is still refused, always. That is the direction that takes money
        somebody did not agree to.
        """
        self.ensure_one()
        currency = self.currency_id
        difference = currency.compare_amounts(self.amount_total, bill['total'])
        if difference < 0:
            _logger.info(
                'mart369: order %s came to %s, under the %s quoted - a price '
                'moved in the customer\'s favour between the two',
                self.mart369_ref, self.amount_total, bill['total'])
            return True
        if difference > 0:
            _logger.error(
                'mart369: order %s totals %s but the bill said %s',
                self.mart369_ref, self.amount_total, bill['total'])
            raise UserError(self.env._(
                "We could not price this order. Nothing has been charged - "
                "please try again."))
        return True

    @api.model
    def _mart369_check_coupon(self, coupon, partner):
        """Usage caps, which the browser had no way to enforce."""
        if coupon.limit_total and coupon.used_count >= coupon.limit_total:
            raise UserError(self.env._('That coupon has been fully used.'))
        if coupon.limit_per_customer:
            mine = self.sudo().search_count([
                ('partner_id', '=', partner.id),
                ('mart369_coupon_id', '=', coupon.id),
                ('mart369_state', '!=', 'cancelled'),
            ])
            if mine >= coupon.limit_per_customer:
                raise UserError(self.env._(
                    'You have already used that coupon.'))
        return True

    @api.model
    def _mart369_address_for(self, partner, address_id):
        """The delivery address, but only if it hangs off this customer.

        Same rule as every other route: someone else's id is not an error
        message, it is simply not found.
        """
        if not address_id:
            return self.env['res.partner'].browse()
        try:
            address_id = int(address_id)
        except (TypeError, ValueError):
            raise UserError(self.env._('That delivery address was not found.'))
        address = self.env['res.partner'].sudo().browse(address_id).exists()
        if not address or address.parent_id != partner:
            raise UserError(self.env._('That delivery address was not found.'))
        return address

    # ----------------------------------------------------------------- slots

    @api.model
    def _mart369_slot_for(self, body):
        """(slot, its fee). An unknown slot key is not fatal - the order still
        has a promise on it - but it books nothing."""
        key = (body.get('slot_key') or '').strip()
        if not key:
            return self.env['mart369.delivery.slot'].browse(), 0.0
        slot = self.env['mart369.delivery.slot'].sudo().search(
            [('key', '=', key)], limit=1)
        if not slot:
            return self.env['mart369.delivery.slot'].browse(), 0.0
        if slot._mart369_is_full(fields.Datetime.now()):
            raise UserError(self.env._(
                'That delivery window has just filled up. Please pick another.'))
        return slot, slot.fee or 0.0

    @api.model
    def _mart369_slot_label(self, slot):
        """The wording the app puts on the confirmation, straight from the slot
        itself so the order repeats what the customer chose."""
        if not slot:
            return ''
        return slot._mart369_serialize(fields.Datetime.now()).get('label') or ''

    @api.model
    def _mart369_slot_day(self, slot):
        if not slot:
            return False
        return fields.Date.context_today(self) + timedelta(days=slot.day_offset or 0)

    @api.model
    def _mart369_due_at(self, slot, mode):
        """When this order is promised, which is what Late is measured against."""
        now = fields.Datetime.now()
        if slot and slot.kind != 'now' and slot.to_hour:
            day = self._mart369_slot_day(slot)
            start = fields.Datetime.to_datetime(day)
            return start + timedelta(hours=float(slot.to_hour))
        if mode == 'quick':
            return now + timedelta(minutes=20)
        return now + timedelta(days=3)

    # ------------------------------------------------------------------ misc

    @api.model
    def _mart369_items_from_pairs(self, pairs):
        """The app carries a basket as [[id, qty], ...] on a placed order and as
        {id: qty} in the cart. Accept either."""
        items = {}
        for pair in pairs or []:
            try:
                items[str(pair[0])] = int(pair[1])
            except (TypeError, ValueError, IndexError, KeyError):
                continue
        return items

    @api.model
    def _mart369_mode_of_bill(self, bill):
        """Which storefront this basket belongs to, the way the app decides it:
        any Quick item makes it a Quick order."""
        return 'quick' if (bill.get('sub') or {}).get('quick') else 'all'

    @api.model
    def _mart369_tax(self):
        """The tax to put on every line, price-included, or nothing.

        Configured per company rather than guessed, because getting this wrong
        means either an illegal invoice or a total that disagrees with the one
        the customer was shown.
        """
        tax = self.env.company.sudo().mart369_tax_id
        if tax and not tax.price_include:
            raise UserError(self.env._(
                'The 369 Mart tax must be set to "Included in price", because '
                'the app quotes prices with tax in them.'))
        return tax

    # --------------------------------------------------- once it is paid for

    def _mart369_spend_coupon(self):
        """Count the use, now that there is really an order behind it.

        Counted at payment rather than at placement so an abandoned basket does
        not burn a code the customer never got to use.
        """
        self.ensure_one()
        if self.mart369_coupon_id:
            coupon = self.mart369_coupon_id.sudo()
            coupon.write({'used_count': (coupon.used_count or 0) + 1})
        return True

    def _mart369_confirm(self):
        """Quotation -> order, so stock is reserved and it can be invoiced.

        Wrapped because a confirm can legitimately fail - nothing left in stock,
        a product gone unsellable - and the money has already been taken by the
        time we get here. Better a paid order sitting as a quotation for an
        operator to look at than an exception that loses the payment.
        """
        self.ensure_one()
        if self.state in ('sale', 'done', 'cancel'):
            return False
        try:
            self.with_context(mart369_placing=True).action_confirm()
        except Exception:  # noqa: BLE001 - see the docstring
            _logger.exception(
                'mart369: order %s was paid for but could not be confirmed',
                self.mart369_ref)
            return False
        self._mart369_invoice()
        return True

    def _mart369_invoice(self):
        """The bill, as a real document in the books.

        Until now nothing in the suite ever made an `account.move`, so the shop
        took money that never reached accounting: no revenue, no tax, no
        receivable, and both invoice routes answered 404 because there was
        genuinely nothing to render.

        `_create_invoices` rather than a move built by hand. It already knows
        the lines, the partner, the currency and - the part worth not
        re-deriving - the price-included tax this shop quotes in, which
        `_mart369_order_values` set on the lines when the order was placed.

        Swallowed like the confirm above it, and for the same reason: by the
        time this runs the customer has paid. An unbilled order an operator can
        see beats an exception that loses the payment.
        """
        self.ensure_one()
        # Both `_mart369_on_paid` and `_mart369_on_accepted` reach the confirm,
        # and `_post_process` can run more than once for one transaction, so
        # this has to be safe to call twice. A second invoice for one order is
        # worse than none: it doubles the day's revenue.
        if self.invoice_ids.filtered(lambda m: m.state != 'cancel'):
            return False
        if self.invoice_status == 'no':
            return False
        try:
            invoice = self.with_context(mart369_placing=True)._create_invoices()
            if not invoice:
                return False
            invoice.action_post()
        except Exception:  # noqa: BLE001 - see the docstring
            _logger.exception(
                'mart369: order %s was paid for but could not be invoiced',
                self.mart369_ref)
            return False
        # The payment was booked before this invoice existed; match them now
        # (order_accounting.py).
        self._mart369_settle_invoice()
        return True
