"""Three things both sides keep, kept in step (the senior's "Mirror" list).

Each one is written where *this* side writes its own value - never in the
WhatsApp flow - so the stack's STOP / START, its address book and its rider
app go on exactly as they are:

* **Updates switch.** The website's WhatsApp switch is
  `res.partner.mart369_notify_whatsapp`; the stack's STOP / START UPDATES is
  `res.partner.sa_wa_updates_off` (it writes ours too). Flipping ours on the
  website writes theirs.
* **The note for one delivery.** The checkout note is
  `sale.order.mart369_instructions`; the stack's is `sale.order.sa_delivery_note`,
  which its job hands to the rider. Writing ours writes theirs; a note given
  on WhatsApp shows on the website's order page.
* **Rider role -> rider record.** The console's riders are users with the
  Rider role; the stack's are `sa.delivery.partner` rows, which the rider app,
  live position and pay run on. Getting the role links or makes one; losing
  it switches it off.

Each mirror checks the stack's field exists first, so an older stack (this
machine's copy) simply has nothing to mirror into.
"""

import logging

from odoo import api, models

_logger = logging.getLogger(__name__)

RIDER_GROUP = 'mart369_roles.group_rider'
# res.users keys that can change who holds a role.
_ROLE_KEYS = ('group_ids', 'active', 'mart369_rider', 'mart369_role', 'share')


class ResPartner(models.Model):
    _inherit = 'res.partner'

    def _mart369_write_prefs(self, values):
        prefs = super()._mart369_write_prefs(values)
        if 'whatsapp' in (values or {}) and 'sa_wa_updates_off' in self._fields:
            self.sudo().write({'sa_wa_updates_off': not bool(values['whatsapp'])})
        return prefs


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _mart369_with_note(self, vals):
        """The checkout note, also as the stack's note for this delivery."""
        if ('mart369_instructions' in vals and 'sa_delivery_note' not in vals
                and 'sa_delivery_note' in self._fields):
            vals = dict(vals, sa_delivery_note=(vals['mart369_instructions'] or '')[:120] or False)
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        return super().create([self._mart369_with_note(v) for v in vals_list])

    def write(self, vals):
        return super().write(self._mart369_with_note(vals))

    def _mart369_serialize(self):
        """A note given on WhatsApp is this order's note on the website too."""
        data = super()._mart369_serialize()
        if not data.get('instructions') and 'sa_delivery_note' in self._fields:
            data['instructions'] = self.sudo().sa_delivery_note or ''
        return data


class ResUsers(models.Model):
    _inherit = 'res.users'

    def _mart369_is_rider(self):
        self.ensure_one()
        return bool(self.active and not self.share and self.has_group(RIDER_GROUP))

    @api.model_create_multi
    def create(self, vals_list):
        users = super().create(vals_list)
        users._mart369_sync_rider({})
        return users

    def write(self, vals):
        touches = any(k in vals for k in _ROLE_KEYS) or any(
            k.startswith(('in_group_', 'sel_groups_')) for k in vals)
        before = {u.id: u._mart369_is_rider() for u in self} if touches else None
        result = super().write(vals)
        if before is not None:
            self._mart369_sync_rider(before)
        return result

    def _mart369_sync_rider(self, before):
        """Link or make the stack's rider for a new Rider; switch it off for
        one who lost the role. Never raises - a role change always saves."""
        Rider = self.env['sa.delivery.partner'].sudo().with_context(active_test=False)
        for user in self:
            try:
                now = user._mart369_is_rider()
                if now == before.get(user.id, False):
                    continue
                mine = Rider.search([('user_id', '=', user.id)])
                if not now:
                    mine.filtered('active').write({'active': False})
                    continue
                if mine.filtered('active'):
                    continue
                if mine:
                    # Back on the team: the same record, history and all.
                    mine[:1].active = True
                    continue
                phone = (user.partner_id.phone or '').strip()
                if not phone:
                    # The stack's rider needs a WhatsApp number; the console's
                    # assignment still works without one (sale_order_sync.py).
                    _logger.info('bridge: rider %s has no phone - no rider record yet', user.login)
                    continue
                rider = Rider.with_context(active_test=True)._sa_by_phone(phone)
                if rider:
                    rider.user_id = user
                else:
                    # Off duty until they clock on in the app: a role is not
                    # a shift, and on duty means jobs start arriving.
                    Rider.create({'name': user.name, 'phone': phone, 'user_id': user.id,
                                  'partner_id': user.partner_id.id, 'kind': 'own',
                                  'on_duty': False})
            except Exception:  # noqa: BLE001
                _logger.exception('bridge: rider record for %s not kept in step', user.login)
