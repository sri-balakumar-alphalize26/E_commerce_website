"""Keep group traffic out of the tracker's one-to-one bookkeeping.

whatsapp_employee_tracker was written when nothing group-shaped could reach it
- the gateway dropped that traffic at the webhook. Now that this module lets it
through, two of the tracker's assumptions break:

* `wa.conversation._get_or_create` cleans a phone down to its digits. A group
  JID cleans down to an 18-digit number, so every group would become a
  "conversation" with a contact nobody can call.
* `wa.communication.log` would then count group chatter as the employee's own
  messages, feeding their volume score, their response time and their tone
  analysis with traffic they never sent.

Both are headed off here rather than by editing the tracker, so a database that
does not install this module keeps the tracker exactly as it is.
"""

import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class WaConversation(models.Model):
    _inherit = 'wa.conversation'

    @api.model
    def _get_or_create(self, emp_session, phone, partner=None):
        if phone and '@g.us' in str(phone):
            return False
        return super()._get_or_create(emp_session, phone, partner=partner)


class WaCommunicationLog(models.Model):
    _inherit = 'wa.communication.log'

    # The gateway marks a message it refused to send (opt-out, daily cap,
    # duplicate) 'blocked'; the tracker copies msg.status into its log and
    # its own list did not have the value, so the sync cron died on every
    # run (6 Oct 2026). The value is added here, and any other value the
    # gateway may grow is mapped to 'failed' rather than aborting the sync.
    status = fields.Selection(selection_add=[('blocked', 'Blocked')])

    def _sa_safe_status(self, vals):
        if 'status' in vals and vals['status']:
            allowed = {k for k, _ in self._fields['status'].get_description(self.env)['selection']}
            if vals['status'] not in allowed:
                vals['status'] = 'failed'
        return vals

    def write(self, vals):
        return super().write(self._sa_safe_status(dict(vals)))

    @api.model_create_multi
    def create(self, vals_list):
        """Drop log rows for group messages.

        The tracker's catch-up cron searches whatsapp.message by session and
        has no way to exclude groups, so the filter has to sit here. Callers
        cope with getting fewer records back than they asked for: the cron's
        `_check_message` and `create_or_update_for_message` both no-op on an
        empty recordset.
        """
        Message = self.env['whatsapp.message']
        keep = []
        for vals in vals_list:
            message_id = vals.get('message_id')
            if message_id and Message.browse(message_id)._sa_is_group():
                continue
            keep.append(self._sa_safe_status(vals))
        return super().create(keep)


class WhatsAppMessageTrackerGuard(models.Model):
    _inherit = 'whatsapp.message'

    def _instant_sync_to_tracker(self, messages):
        messages = messages.filtered(lambda m: not m._sa_is_group())
        if not messages:
            return
        return super()._instant_sync_to_tracker(messages)
