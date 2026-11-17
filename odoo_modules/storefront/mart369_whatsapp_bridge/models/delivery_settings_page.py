"""The WhatsApp side of the one-page Delivery settings (13 Nov 2026).

mart369_cart's page (models/delivery_settings.py) knows the website's records.
Here it learns the rest:

* each branch's **WhatsApp delivery shop** and **riders**, read-only on the
  page;
* a branch's **pin and Quick are written to its shop too** when they are
  saved, so the branch and its shop never point at two places again (with
  the senior's Quick / Express module, its shop Quick switch and reach as
  well, since that module decides Quick from the shop);
* the **fees** come from, and go to, the senior's fee rules when his module is
  installed - those are the ones the shop charges then - and the website's
  copy is kept the same;
* the **WhatsApp delivery** section: the promise for WhatsApp orders, calling a
  rider when packed, and asking for a review.
"""

from odoo import api, models

from odoo.addons.mart369_cart.models.branch import has_pin

from .qe_link import OURS, THEIRS, qe_on


class DeliverySettingsPageWhatsapp(models.AbstractModel):
    _inherit = 'mart369.delivery.settings.page'

    def _page_branch(self, branch):
        row = super()._page_branch(branch)
        shops = self.env['sa.delivery.shop'].sudo().with_context(active_test=False).search(
            [('warehouse_id', '=', branch.id)])
        live = shops.filtered('active')
        if live:
            row['shop'] = 'auto' if any(live.mapped('mart369_auto')) else 'yours'
        elif shops:
            row['shop'] = 'archived'
        riders = self.env['sa.delivery.partner'].sudo().search([]).filtered(
            lambda r: not r.shop_ids or (r.shop_ids & live))
        row['riders'] = len(riders) if live or not shops else None
        return row

    @api.model
    def _page_fees(self):
        fees = super()._page_fees()
        if not qe_on(self.env):
            return fees
        Rule = self.env['sa.qe.delivery.rule'].sudo().with_context(active_test=False)
        for mode in ('quick', 'all'):
            rule = Rule.search([('mode', '=', THEIRS[mode])], order='active desc, id', limit=1)
            if rule:
                fees[mode] = {
                    'label': rule.label or '', 'eta': rule.eta or '',
                    'fee': rule.fee or 0.0, 'freeAbove': rule.free_above or 0.0,
                    'minOrder': rule.min_order or 0.0, 'active': bool(rule.active),
                }
        return fees

    # With his module the checkout and the WhatsApp order page offer his slots,
    # not the website's: the page's slot table shows and edits those.

    @api.model
    def _page_slot_records(self):
        if not qe_on(self.env):
            return super()._page_slot_records()
        return self.env['sa.qe.delivery.slot'].sudo().with_context(active_test=False).search(
            [], order='mode, sequence, id')

    @api.model
    def _page_slot_row(self, slot):
        if slot._name != 'sa.qe.delivery.slot':
            return super()._page_slot_row(slot)
        return {
            'id': slot.id, 'mode': OURS.get(slot.mode, 'quick'), 'kind': slot.kind,
            'heading': slot.name or '', 'detail': '',
            'dayOffset': slot.day_offset or 0,
            'fromHour': round(slot.from_hour or 0.0, 2), 'toHour': round(slot.to_hour or 0.0, 2),
            'orderBefore': round(slot.order_before or 0.0, 2),
            'fee': round(slot.fee or 0.0, 2), 'capacity': slot.capacity or 0,
            'active': bool(slot.active),
        }

    @api.model
    def _page_slot_shown(self, slot):
        if slot._name != 'sa.qe.delivery.slot':
            return super()._page_slot_shown(slot)
        return slot.name or ''

    @api.model
    def _page_slot_write(self, slot, vals):
        if not qe_on(self.env):
            return super()._page_slot_write(slot, vals)
        out = {'name': vals['heading'], 'mode': THEIRS.get(vals['mode'], 'quick'), 'kind': vals['kind'],
               'day_offset': vals['dayOffset'], 'from_hour': vals['fromHour'], 'to_hour': vals['toHour'],
               'order_before': vals['orderBefore'], 'fee': vals['fee'],
               'capacity': vals['capacity'], 'active': vals['active']}
        if slot:
            slot.write(out)
        else:
            self.env['sa.qe.delivery.slot'].sudo().create(out)

    @api.model
    def _page_slots(self):
        slots = super()._page_slots()
        if qe_on(self.env):
            slots['detail'] = False        # his slot has one name, no detail line
        return slots

    @api.model
    def _page_fee_write(self, mode, vals):
        super()._page_fee_write(mode, vals)
        if qe_on(self.env):
            Rule = self.env['sa.qe.delivery.rule'].sudo().with_context(active_test=False)
            rule = Rule.search([('mode', '=', THEIRS[mode])], order='active desc, id', limit=1)
            if rule:
                rule.write({k: v for k, v in vals.items() if k in rule._fields})

    @api.model
    def _page_branch_saved(self, branch, vals):
        super()._page_branch_saved(branch, vals)
        Shop = self.env['sa.delivery.shop'].sudo().with_context(mart369_auto_setup=True)
        shops = Shop.search([('warehouse_id', '=', branch.id)])
        if not shops:
            return
        out = {}
        if 'pin' in vals and has_pin(branch.mart369_lat, branch.mart369_lng):
            out.update(latitude=branch.mart369_lat, longitude=branch.mart369_lng)
        if 'qe_quick' in Shop._fields and {'quick', 'quickKm'} & set(vals):
            out.update(qe_quick=branch.mart369_quick, qe_quick_km=branch.mart369_quick_km)
        if out:
            shops.write(out)

    # ------------------------------------------------------- WhatsApp section

    @api.model
    def _page_whatsapp(self):
        s = self.env['sa.delivery.settings'].sudo().get_settings()
        riders = self.env['sa.delivery.partner'].sudo().search([])
        return {
            'quickHours': s.quick_hours,
            'cutoffHour': s.cutoff_hour,
            'expressDays': s.express_days,
            'autoCallRider': bool(s.auto_call_rider_on_packed),
            'askReview': bool(s.ask_review) if 'ask_review' in s._fields else None,
            'riders': len(riders),
            'onDuty': len(riders.filtered('on_duty')),
        }

    @api.model
    def _page_whatsapp_check(self, data, errors):
        _ = self.env._
        out = {}
        where = {'section': 'whatsapp', 'row': ''}
        for key, field, what, low, high in (
                ('quickHours', 'quick_hours', _('Quick within (hours)'), 1, 72),
                ('cutoffHour', 'cutoff_hour', _('Cut-off hour'), 0, 23),
                ('expressDays', 'express_days', _('Express in (days)'), 1, 60)):
            if key in data:
                value = self._number(data[key], errors, dict(where, field=key), what,
                                     low=low, high=high, whole=True)
                if value is not None:
                    out[field] = value
        if 'autoCallRider' in data:
            out['auto_call_rider_on_packed'] = bool(data['autoCallRider'])
        if 'askReview' in data and data['askReview'] is not None:
            out['ask_review'] = bool(data['askReview'])
        return out

    @api.model
    def _page_whatsapp_write(self, vals):
        s = self.env['sa.delivery.settings'].sudo().get_settings()
        s.write({k: v for k, v in vals.items() if k in s._fields})
