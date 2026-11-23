# -*- coding: utf-8 -*-
"""The delivery address on the sign page (owner, 23 Nov 2026).

The order already carries the customer's default address; until they sign they
can pick another of their own, edit one, or add one. After the signature the
address is fixed. Only for WhatsApp group orders whose sign link went out:
website and private-chat orders keep their own address screens."""
import logging
from datetime import timedelta

from odoo import _, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class SaleOrderPortalAddress(models.Model):
    _inherit = 'sale.order'

    def _sa_addr_open(self):
        """Can the customer still change where this order goes?"""
        self.ensure_one()
        o = self.sudo()
        if o.state not in ('draft', 'sent') or o.signed_on or not o._has_to_be_signed():
            return False
        req = o._sa_group_enquiry()
        if not (req and req.state == 'order_created' and req.order_id == o
                and req.sa_sign_link_sent_on and not req.sa_details_pending):
            return False
        return not o.amount_paid and not req._sa_order_is_paid(o)

    def _sa_portal_book(self):
        """The customer's own saved addresses, the only ones ever offered."""
        self.ensure_one()
        o = self.sudo()
        return o._sa_group_enquiry()._sa_address_book(o.partner_id.sudo())

    def _sa_portal_addresses(self):
        """What the card draws: {'open', 'rows': [{id, label, icon, text,
        default, chosen}]}."""
        self.ensure_one()
        o = self.sudo()
        if not o._sa_addr_open():
            return {'open': False, 'rows': []}
        customer = o.partner_id
        shop = customer._sa_shop_book()
        return {'open': True, 'rows': [{
            'id': a.id, 'label': a._sa_label(), 'icon': a._sa_icon(), 'text': a._sa_addr_text(),
            'default': bool(shop and a != customer and a.mart369_default),
            'chosen': a == o.partner_shipping_id,
        } for a in o._sa_portal_book()]}

    def _sa_addr_redecide(self):
        """Another place can mean Express instead of Quick (and another fee);
        worked out again when that module decides it for this order."""
        for o in self.sudo():
            if 'qe_decided' not in o._fields or not o.qe_decided:
                continue
            had_fee = bool(o.order_line.filtered(lambda l: l.qe_kind == 'fee'))
            o._qe_decide()
            if had_fee:
                o._qe_apply_fee()

    def _sa_portal_use_address(self, addr):
        """Send this order to `addr`. Returns an error text, or ''."""
        self.ensure_one()
        o = self.sudo()
        addr = addr.sudo().exists()
        if not o._sa_addr_open():
            return _("This order can no longer change its delivery address.")
        if not addr or addr not in o._sa_portal_book():
            return _("That address is not available. Please pick another.")
        if addr == o.partner_shipping_id:
            return ''
        try:
            with self.env.cr.savepoint():
                o._sa_group_enquiry()._sa_use_address(o, addr)
                o._sa_addr_redecide()
                o.message_post(body=_("Delivery address changed by the customer on the sign page: %s",
                                      addr._sa_addr_text()))
        except Exception:  # noqa: BLE001 - the order keeps the address it had
            _logger.exception("Sign page: address of %s not changed", o.name)
            return _("Could not change the address. Please try again.")
        return ''

    def _sa_portal_addr_link(self, mode, addr=None):
        """The address form for this order, opened from the sign page."""
        self.ensure_one()
        o = self.sudo()
        Link = self.env['sa.address.link'].sudo()
        if not o._sa_addr_open():
            raise UserError(_("This order can no longer change its delivery address."))
        addr = (addr or self.env['res.partner']).sudo().exists()
        if mode == 'edit' and (not addr or addr not in o._sa_portal_book()):
            raise UserError(_("That address is not available. Please pick another."))
        if mode != 'edit':
            mode, addr = 'add', self.env['res.partner']
        req = o._sa_group_enquiry()
        live = Link.search([('request_id', '=', req.id), ('back', '=', 'page'), ('mode', '=', mode),
                            ('target_id', '=', addr.id or False), ('used_on', '=', False)]
                           ).filtered(lambda l: l._alive())[:1]
        if live:
            return live
        minutes = max(5, req._settings().address_link_minutes or 30)
        return Link.create({
            'request_id': req.id, 'mode': mode, 'back': 'page', 'target_id': addr.id or False,
            'expires_on': fields.Datetime.now() + timedelta(minutes=minutes)})
