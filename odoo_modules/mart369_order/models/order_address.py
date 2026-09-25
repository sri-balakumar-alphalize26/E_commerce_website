"""An order's delivery address: kept as it was, changeable only before it ships.

Two rules, the way Flipkart and Amazon keep them:

- **An order keeps the address it was placed with.** mart369_address copies an
  address rather than rewriting it once `_mart369_in_use` says an order points
  at it; this is where that question is answered, because only this module
  knows what an order is.
- **Support can move an order to another of the customer's addresses until it
  leaves the store** - placed or packed. After that the parcel is on its way.
"""

from markupsafe import Markup, escape

from odoo import api, models
from odoo.exceptions import UserError

# Before these, the parcel has not left: the address may still change.
ADDRESS_CHANGEABLE = ('placed', 'packed')


class ResPartner(models.Model):
    _inherit = 'res.partner'

    def _mart369_in_use(self):
        """True once any order - placed, delivered or cancelled - ships here."""
        self.ensure_one()
        return bool(self.env['sale.order'].sudo().search_count(
            [('partner_shipping_id', '=', self.id)], limit=1))


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _mart369_address_changeable(self):
        self.ensure_one()
        return self.mart369_state in ADDRESS_CHANGEABLE

    @api.model
    def mart369_admin_set_address(self, ref, address_id):
        """Send an order that has not left yet to another of the customer's
        saved addresses, and say so in the order's history.

        Public because the backend desk reaches it over `orm.call`.
        """
        order = self._mart369_admin_find(ref)
        if not order:
            raise UserError(self.env._('There is no such order.'))
        if not order._mart369_address_changeable():
            raise UserError(self.env._(
                'This order has already left the store, so its address can no longer change.'))
        address = self._mart369_address_for(order.partner_id, address_id)
        if not address or not address.active:
            raise UserError(self.env._('That delivery address was not found.'))
        before = order.partner_shipping_id
        if address != before:
            order.partner_shipping_id = address
            # A delivery already made from the order carries its own copy of
            # the address; one still to go follows the order.
            if 'picking_ids' in order._fields:
                order.picking_ids.filtered(
                    lambda p: p.state not in ('done', 'cancel')).write({'partner_id': address.id})
            note = self.env._(
                'Delivery address changed from %(old)s to %(new)s by %(who)s.',
                old=before.mart369_label or before.display_name or '-',
                new=address.mart369_label or address.display_name,
                who=self.env.user.name)
            order.message_post(body=Markup('<p>%s</p>') % escape(note), subtype_xmlid='mail.mt_note')
        return order._mart369_admin_detail()

    def _mart369_admin_detail(self):
        """The drawer, plus what it needs to offer a change of address."""
        row = super()._mart369_admin_detail()
        changeable = self._mart369_address_changeable()
        row['addressChangeable'] = changeable
        row['addresses'] = ([a._mart369_serialize() for a in self.partner_id.sudo()._mart369_book()]
                            if changeable else [])
        return row
