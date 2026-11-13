# -*- coding: utf-8 -*-
"""Delivery slots on the WhatsApp order page (13 Nov 2026, owner).

The order page (/my/orders/<id>, sales_automation) asks two hooks:
`_sa_portal_slots()` for the chips and `_sa_portal_set_slot(key)` to book one.
This module answers them with exactly what the storefront checkout offers -
the same backend slots (the WhatsApp Quick/Express ones when that module is
installed, else the website's), for the order's Quick or Express mode - and
books them with the checkout's own helpers.

Owner's rules: per company, slots can be switched off (res.company
.mart369_slots_on); picking is optional; there is NO slot fee on these orders,
so the total never changes; only while the order is still a quotation.
"""
import logging

from odoo import _, models
from odoo.exceptions import UserError, ValidationError

from .qe_link import OURS, QUICK, EXPRESS, qe_on

_logger = logging.getLogger(__name__)


class SaleOrderPortalSlots(models.Model):
    _inherit = 'sale.order'

    def _sa_slot_mode(self):
        """'quick' or 'all' (the website's names) for this order, or ''."""
        self.ensure_one()
        o = self.sudo()
        if qe_on(self.env) and 'qe_mode' in o._fields:
            if not o.qe_decided and o.state in ('draft', 'sent') and hasattr(o, '_qe_decide'):
                try:
                    o._qe_decide()
                except Exception as err:  # noqa: BLE001 - no slots rather than no page
                    _logger.info("Portal slots: could not decide %s: %s", o.name, err)
            return OURS.get(o.qe_mode or '', '')
        lines = o.order_line.filtered(lambda l: l.product_id and not l.display_type
                                      and o._sa_line_kind(l) == 'item')
        if not lines:
            return ''
        cart = self.env['mart369.cart'].sudo()
        address = o.partner_shipping_id or o.partner_id
        try:
            where = cart._mart369_where(address)
            modes = {cart._mart369_offer(l.product_id.product_tmpl_id, l.product_uom_qty or 1, where,
                                         variant=l.product_id).get('mode') for l in lines}
        except Exception as err:  # noqa: BLE001
            _logger.info("Portal slots: no mode for %s: %s", o.name, err)
            return ''
        return QUICK if modes == {QUICK} else EXPRESS

    def _sa_slot_open(self):
        """Can this order still pick a slot?"""
        self.ensure_one()
        o = self.sudo()
        Slot = self.env['mart369.delivery.slot'].sudo()
        return (o.state in ('draft', 'sent') and not o._sa_portal_status().get('paid')
                and Slot._mart369_slots_on(o.company_id))

    def _sa_portal_slots(self):
        self.ensure_one()
        out = {'chips': [], 'chosen': ''}
        o = self.sudo()
        if not o._sa_slot_open():
            return out
        mode = o._sa_slot_mode()
        if not mode:
            return out
        try:
            chips = self.env['mart369.delivery.slot'].with_company(o.company_id).sudo()._mart369_slots().get(mode) or []
        except Exception as err:  # noqa: BLE001
            _logger.info("Portal slots: no list for %s: %s", o.name, err)
            return out
        # No slot fee on these orders (owner): the chips carry none.
        out['chips'] = [{k: c.get(k) for k in ('key', 'top', 'sub', 'label')} for c in chips if c.get('key')]
        out['chosen'] = o.mart369_slot_key or '' if 'mart369_slot_key' in o._fields else ''
        return out

    def _sa_portal_set_slot(self, key):
        self.ensure_one()
        o = self.sudo()
        if not o._sa_slot_open():
            return _("This order can no longer change its delivery slot.")
        key = (key or '').strip()
        clear = {'mart369_slot_key': False, 'mart369_slot_label': False,
                 'mart369_slot_day': False, 'mart369_due_at': False}
        if qe_on(self.env) and 'qe_slot_id' in o._fields:
            clear['qe_slot_id'] = False
        if not key:
            o.write(clear)
            return ''
        if key not in {c['key'] for c in o._sa_portal_slots()['chips']}:
            return _("That delivery slot is not available any more. Please pick another.")
        Order = self.env['sale.order'].sudo().with_company(o.company_id)
        try:
            slot, _fee = Order._mart369_slot_for({'slot_key': key})      # raises when closed or full
            if not slot:
                return _("That delivery slot is not available any more. Please pick another.")
            mode = o._sa_slot_mode()
            vals = {
                'mart369_slot_key': Order._mart369_slot_key(slot),
                'mart369_slot_label': Order._mart369_slot_label(slot),
                'mart369_slot_day': Order._mart369_slot_day(slot),
                'mart369_due_at': Order._mart369_due_at(slot, mode or EXPRESS),
            }
            if Order._mart369_is_qe_slot(slot):
                vals['qe_slot_id'] = slot.id          # his constraint re-checks capacity
            o.write(vals)
        except (UserError, ValidationError) as err:
            return str(err.args[0] if err.args else err)
        return ''
