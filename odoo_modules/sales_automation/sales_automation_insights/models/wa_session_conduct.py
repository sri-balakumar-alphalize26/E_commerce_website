# -*- coding: utf-8 -*-
"""Delete a message for everyone, through the gateway.

Evolution's `DELETE /chat/deleteMessageForEveryone/<instance>` takes the four
fields Baileys needs. WhatsApp itself only honours deleting somebody else's
group message when our number is a group admin; when it is not, the call
succeeds and nothing happens, and nothing here can tell the difference.
"""
import logging

from odoo import models

_logger = logging.getLogger(__name__)


class WaSessionConduct(models.Model):
    _inherit = 'whatsapp.session'

    def sa_delete_message(self, remote_jid, wa_id, participant='', from_me=False):
        self.ensure_one()
        payload = {'id': wa_id, 'fromMe': bool(from_me), 'remoteJid': remote_jid}
        if participant and str(remote_jid).endswith('@g.us'):
            p = str(participant)
            if '@' not in p:
                p = '%s@s.whatsapp.net' % ''.join(ch for ch in p if ch.isdigit())
            payload['participant'] = p
        _logger.info("WhatsApp: DELETE /chat/deleteMessageForEveryone %s in %s",
                     wa_id, remote_jid)
        return self._gateway_call(
            'DELETE', '/chat/deleteMessageForEveryone/%s' % (self.instance_name or 'x'),
            payload)

    def sa_group_admin_status(self, group_jid):
        """(we_are_admin, our_number) for a group. WhatsApp ignores a
        delete-for-everyone from a non-admin without saying so; this is how
        the remark can say so instead. Raises UserError like any gateway call."""
        self.ensure_one()
        inst = self.instance_name or 'x'
        info = self._gateway_call('GET', '/instance/fetchInstances?instanceName=%s' % inst)
        if isinstance(info, list):
            info = info[0] if info else {}
        owner = str((info or {}).get('ownerJid') or '')
        ours = ''.join(ch for ch in owner.split('@')[0] if ch.isdigit())
        data = self._gateway_call('GET', '/group/participants/%s?groupJid=%s' % (inst, group_jid))
        parts = data.get('participants') if isinstance(data, dict) else data
        for p in parts or []:
            pn = str(p.get('phoneNumber') or p.get('jid') or p.get('id') or '')
            digits = ''.join(ch for ch in pn.split('@')[0] if ch.isdigit())
            if ours and digits == ours:
                return bool(p.get('admin')), ours
        return False, ours
