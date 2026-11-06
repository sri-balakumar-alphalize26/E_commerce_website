"""Offering a replacement for an item that ran out - and letting the customer
choose, the way JioMart and BigBasket do.

Staff pick up to three other products; the customer sees them on their order
page and in their notifications, and picks one - or none:

* **Pick one** - that replacement goes in the bag. It never costs them more: if it
  is dearer the shop pays the difference; if it is cheaper the difference goes
  to their 369 Wallet (cash on delivery: they owe less at the door).
* **No, refund me** - the item is taken out and refunded, exactly as
  "Remove" does (order_items.py).
* **No answer** by the deadline (Settings > Orders: 10 minutes for Quick, two
  hours for Express by default) - treated as "refund me", so an order is never
  stuck waiting on somebody who is not looking at their phone.

While an offer is open the order is not packed: the bag is not closed on an
item the customer has not chosen yet.
"""

import logging
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .order_items import REMOVABLE_STATES

_logger = logging.getLogger(__name__)

# How many replacements staff may offer for one item.
MAX_OPTIONS = 3

STATES = [
    ('offered', 'Waiting for the customer'),
    ('accepted', 'Accepted'),
    ('declined', 'Declined'),
    ('expired', 'No answer'),
    ('withdrawn', 'Withdrawn'),
]


class Mart369OrderSubstitute(models.Model):
    _name = 'mart369.order.substitute'
    _description = '369 Mart replacement offer'
    _order = 'id desc'

    order_id = fields.Many2one('sale.order', required=True, index=True, ondelete='cascade')
    line_id = fields.Many2one('sale.order.line', string='Out of stock', required=True, ondelete='cascade')
    option_ids = fields.Many2many(
        'product.product', 'mart369_substitute_option_rel', 'offer_id', 'product_id',
        string='Offered instead', help='Up to three; the customer picks one.')
    product_id = fields.Many2one('product.product', string='Chosen',
                                 help='The replacement the customer picked.')
    qty = fields.Float(required=True)
    currency_id = fields.Many2one(related='order_id.currency_id')
    original_price = fields.Monetary(string='Was, each', currency_field='currency_id')
    offered_price = fields.Monetary(string='Replacement costs, each', currency_field='currency_id')
    unit_price = fields.Monetary(
        string='Customer pays, each', currency_field='currency_id',
        help='Never more than the item they ordered: the shop pays any difference.')
    state = fields.Selection(STATES, default='offered', required=True, index=True)
    deadline = fields.Datetime(required=True)
    answered_at = fields.Datetime()
    new_line_id = fields.Many2one('sale.order.line', string='Added line', ondelete='set null')
    refund = fields.Monetary(string='To wallet', currency_field='currency_id')

    def _mart369_options(self):
        """What was offered. An offer made before there could be several
        carries its one product in `product_id` only."""
        self.ensure_one()
        return self.option_ids or self.product_id

    def _mart369_option_row(self, product):
        currency = self.currency_id
        each = product.lst_price
        pays = min(each, self.original_price)
        return {
            'id': product.id,
            'name': product.display_name,
            'image': (self.env['mart369.serializable']._image_url('image_256', '256x256', product)
                      if product.image_256 else ''),
            'price': currency.round(each),
            'youPay': currency.round(pays),
            'shopPays': currency.round(max(0.0, each - self.original_price) * self.qty),
            'difference': currency.round(max(0.0, self.original_price - pays) * self.qty),
        }

    def _mart369_serialize(self):
        self.ensure_one()
        currency = self.currency_id
        shown = self.product_id or self._mart369_options()[:1]
        image = (self.env['mart369.serializable']._image_url('image_256', '256x256', shown)
                 if shown.image_256 else '')
        return {
            'id': self.id,
            'state': self.state,
            'lineId': self.line_id.id,
            'was': self.line_id.name or self.line_id.product_id.display_name,
            'qty': int(self.qty),
            'wasPrice': currency.round(self.original_price),
            # The choices; the one picked, once it is picked.
            'options': [self._mart369_option_row(p) for p in self._mart369_options()],
            'chosen': self.product_id.id or False,
            'offered': shown.display_name if len(self._mart369_options()) == 1 or self.product_id
            else ', '.join(self._mart369_options().mapped('display_name')),
            'offeredImage': image,
            'offeredPrice': currency.round(self.offered_price),
            'youPay': currency.round(self.unit_price),
            # Per piece: positive, the shop pays it; negative, it comes back.
            'shopPays': currency.round(max(0.0, self.offered_price - self.original_price) * self.qty),
            'difference': currency.round(max(0.0, self.original_price - self.unit_price) * self.qty),
            'deadline': int(self.deadline.timestamp() * 1000) if self.deadline else None,
            'refund': currency.round(self.refund or 0.0),
        }


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    mart369_substitute_ids = fields.One2many('mart369.order.substitute', 'order_id', string='Replacement offers')

    # ----------------------------------------------------------- the offer

    def _mart369_substitute_minutes(self):
        """How long the customer gets to answer: Settings > Orders."""
        self.ensure_one()
        config = self.env['mart369.config'].sudo()._get()
        if (self.mart369_mode or 'quick') == 'quick':
            return config.substitute_quick_minutes or 10
        return config.substitute_express_minutes or 120

    def _mart369_open_substitutes(self):
        self.ensure_one()
        return self.mart369_substitute_ids.filtered(lambda s: s.state == 'offered')

    @api.model
    def _mart369_can_send(self, product):
        """Published, for sale, and - for a stocked product - some left."""
        tmpl = product.product_tmpl_id
        if not product or not product.sale_ok or not tmpl.is_published:
            return False
        if 'is_storable' in product._fields and product.is_storable:
            return product.free_qty > 0
        return True

    @api.model
    def _mart369_substitute_candidates(self, line, q=None, limit=10):
        """Products the shop could send instead: not the same product,
        matching `q`, the missing item's own category first."""
        domain = [('sale_ok', '=', True), ('product_tmpl_id.is_published', '=', True),
                  ('id', '!=', line.product_id.id)]
        if q:
            domain += ['|', ('name', 'ilike', q), ('default_code', 'ilike', q)]
        found = self.env['product.product'].sudo().search(domain, limit=300)
        found = found.filtered(self._mart369_can_send)
        categ = line.product_id.product_tmpl_id.public_categ_ids
        found = found.sorted(lambda p: (not (p.product_tmpl_id.public_categ_ids & categ),
                                        p.display_name.lower()))
        return found[:limit]

    def _mart369_offer_substitute(self, line, products):
        """Offer `products` (one to three) instead of `line`."""
        self.ensure_one()
        if self.mart369_state not in REMOVABLE_STATES:
            raise UserError(_('The order has left the store - it is too late to offer a replacement.'))
        if line.order_id != self or line not in self._mart369_item_lines():
            raise UserError(_('That item is not in this order any more.'))
        if not products:
            raise UserError(_('Pick at least one product to offer.'))
        if len(products) > MAX_OPTIONS:
            raise UserError(_('Offer at most %s replacements.', MAX_OPTIONS))
        for product in products:
            if product == line.product_id:
                raise UserError(_('Pick a different product to offer.'))
            if not self._mart369_can_send(product):
                raise UserError(_('%s is not something the shop can send right now.', product.display_name))
        if self._mart369_open_substitutes().filtered(lambda s: s.line_id == line):
            raise UserError(_('A replacement for that item is already waiting for the customer.'))
        original = line.price_unit
        offer = self.env['mart369.order.substitute'].sudo().create({
            'order_id': self.id,
            'line_id': line.id,
            'option_ids': [(6, 0, products.ids)],
            'qty': line.product_uom_qty,
            'original_price': original,
            'offered_price': products[:1].lst_price,
            'unit_price': min(original, products[:1].lst_price),
            'deadline': fields.Datetime.now() + timedelta(minutes=self._mart369_substitute_minutes()),
        })
        self.sudo().message_post(body=_(
            '%(was)s is out of stock. Offered %(new)s instead - waiting for the customer.',
            was=line.product_id.display_name, new=', '.join(products.mapped('display_name'))))
        return offer

    # ------------------------------------------------------------ the answer

    def _mart369_answer_substitute(self, offer, accept, how=None, product=None):
        """The customer's answer - or the deadline's. `product` is the one
        they picked; with a single option it may be left out. Returns the
        offer."""
        self.ensure_one()
        offer = offer.sudo()
        if offer.order_id != self or offer.state != 'offered':
            raise UserError(_('That replacement has already been answered.'))
        now = fields.Datetime.now()
        if accept and offer.deadline and offer.deadline < now:
            accept, how = False, 'expired'
        if not accept:
            offer.write({'state': how or 'declined', 'answered_at': now})
            reason = (_('Out of stock - no answer about a replacement') if how == 'expired'
                      else _('Out of stock - replacement declined'))
            if offer.line_id in self._mart369_item_lines() and len(self._mart369_item_lines()) > 1:
                offer.refund = self._mart369_remove_line(offer.line_id, reason)
            else:
                # The last item: nothing else would go out, so it is a cancel's
                # business, not ours - the order stays for staff to decide.
                self.sudo().message_post(body=reason)
            return offer
        options = offer._mart369_options()
        if not product:
            if len(options) != 1:
                raise UserError(_('Pick one of the replacements.'))
            product = options
        if product not in options:
            raise UserError(_('That is not one of the replacements offered.'))
        offer.write({
            'product_id': product.id,
            'offered_price': product.lst_price,
            'unit_price': min(offer.original_price, product.lst_price),
        })
        return self._mart369_accept_substitute(offer)

    def _mart369_accept_substitute(self, offer):
        order = self.sudo()
        line = offer.line_id
        currency = order.currency_id
        was_total = currency.round(line.price_total)
        cash = (order.mart369_method or '') == 'cod'
        new_line = self.env['sale.order.line'].sudo().create({
            'order_id': order.id,
            'product_id': offer.product_id.id,
            'product_uom_qty': offer.qty,
            'price_unit': offer.unit_price,
            # The product's name, not its whole sales description.
            'name': offer.product_id.display_name,
        })
        # Written after the create: the product's own price and taxes would
        # otherwise be put back by the compute. It is taxed exactly as the item
        # it replaces, so the bill the customer agreed to does not move.
        new_line.write({'price_unit': offer.unit_price, 'tax_ids': [(6, 0, line.tax_ids.ids)]})
        difference = currency.round(max(0.0, was_total - new_line.price_total))
        refund = 0.0 if cash else difference
        line.write({
            'product_uom_qty': 0,
            'mart369_removed_qty': offer.qty,
            'mart369_removed_reason': _('Replaced by %s', offer.product_id.display_name),
            'mart369_removed_refund': refund,
        })
        if refund:
            card = self.env['loyalty.card'].sudo()._mart369_wallet(order.partner_id)
            card._mart369_move(refund, 'refund', _('Cheaper replacement - %s', offer.product_id.display_name),
                               sub=_('Order #%s', order.mart369_ref), order=order)
        elif cash:
            pending = self.env['payment.transaction'].sudo().search([
                ('mart369_order_ref', '=', order.mart369_ref), ('state', '=', 'pending')])
            if pending:
                pending.write({'amount': order.amount_total})
        offer.write({'state': 'accepted', 'answered_at': fields.Datetime.now(),
                     'new_line_id': new_line.id, 'refund': refund})
        order._mart369_credit_removed()
        order.message_post(body=_('The customer accepted %(new)s instead of %(was)s.',
                                  new=offer.product_id.display_name, was=line.product_id.display_name))
        return offer

    def _mart369_withdraw_substitute(self, offer):
        self.ensure_one()
        offer = offer.sudo()
        if offer.order_id != self or offer.state != 'offered':
            raise UserError(_('That replacement has already been answered.'))
        offer.write({'state': 'withdrawn', 'answered_at': fields.Datetime.now()})
        return offer

    # ------------------------------------------------------------- the clock

    @api.model
    def _mart369_expire_substitutes(self, orders=None):
        """Every offer past its deadline: no answer, so refund the item."""
        domain = [('state', '=', 'offered'), ('deadline', '<', fields.Datetime.now())]
        if orders is not None:
            domain.append(('order_id', 'in', orders.ids))
        for offer in self.env['mart369.order.substitute'].sudo().search(domain):
            try:
                with self.env.cr.savepoint():
                    offer.order_id._mart369_answer_substitute(offer, False, how='expired')
            except Exception:  # noqa: BLE001 - one bad order must not stop the rest
                _logger.exception('369 Mart: could not expire replacement offer %s', offer.id)

    @api.model
    def _cron_mart369_expire_substitutes(self):
        self._mart369_expire_substitutes()

    def mart369_action_advance(self):
        """Not packed while the customer is still choosing a replacement."""
        for order in self:
            order._mart369_expire_substitutes(order)
            if order._mart369_open_substitutes() and order.mart369_state == 'placed':
                raise UserError(_(
                    'Order %s is waiting for the customer to answer about a replacement.',
                    order.mart369_ref or ''))
        return super().mart369_action_advance()

    # ------------------------------------------------------ the staff screens

    @api.model
    def mart369_admin_substitutes(self, ref, line_id, q=None):
        order = self._mart369_admin_find(ref)
        if not order:
            raise UserError(_('There is no such order.'))
        line = order.order_line.filtered(lambda l: l.id == int(line_id or 0))
        if not line:
            raise UserError(_('That item is not in this order any more.'))
        currency = order.currency_id
        return [{
            'id': p.id,
            'name': p.display_name,
            'price': currency.round(p.lst_price),
            'image': '/web/image/product.product/%d/image_128' % p.id if p.image_128 else '',
            'stock': p.free_qty if 'free_qty' in p._fields else None,
            # What choosing it would mean, per the order's quantity.
            'shopPays': currency.round(max(0.0, p.lst_price - line.price_unit) * line.product_uom_qty),
            'toWallet': currency.round(max(0.0, line.price_unit - p.lst_price) * line.product_uom_qty),
        } for p in self._mart369_substitute_candidates(line, q=q)]

    @api.model
    def mart369_admin_offer_substitute(self, ref, line_id, product_ids):
        """`product_ids`: one id, or a list of up to three."""
        order = self._mart369_admin_find(ref)
        if not order:
            raise UserError(_('There is no such order.'))
        line = order.order_line.filtered(lambda l: l.id == int(line_id or 0))
        ids = product_ids if isinstance(product_ids, (list, tuple)) else [product_ids]
        products = self.env['product.product'].sudo().browse(
            [int(i) for i in ids if i]).exists()
        order._mart369_offer_substitute(line, products)
        return order._mart369_admin_detail()

    @api.model
    def mart369_admin_withdraw_substitute(self, ref, offer_id):
        order = self._mart369_admin_find(ref)
        if not order:
            raise UserError(_('There is no such order.'))
        offer = order.mart369_substitute_ids.filtered(lambda s: s.id == int(offer_id or 0))
        order._mart369_withdraw_substitute(offer)
        return order._mart369_admin_detail()
