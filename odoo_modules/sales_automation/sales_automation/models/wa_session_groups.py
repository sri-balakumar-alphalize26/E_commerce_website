"""The group list behind the tick boxes.

whatsapp_broadcast already asks Evolution for this, in
`get_joined_groups_data()`. That method is deliberately *not* reused or
redefined here: both modules are installed on res-test1 and wa-test2, and a
second definition of the same name would silently replace the Lead Finder's
copy. This asks the same endpoint under its own name and returns only what the
tick list needs - no participant expansion, which is the slow half.
"""

import logging

from odoo import _, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Listing groups is slower than an ordinary send even without participants.
SA_GROUPS_TIMEOUT = (5, 120)


class WhatsAppSession(models.Model):
    _inherit = 'whatsapp.session'

    def _sa_fetch_groups(self):
        """Every group this number has joined, as [{'jid', 'name', 'size'}]."""
        self.ensure_one()
        try:
            body = self._gateway_call(
                'GET',
                '/group/fetchAllGroups/%s?getParticipants=false' % self.instance_name,
                timeout=SA_GROUPS_TIMEOUT,
            )
        except UserError as err:
            _logger.exception("fetchAllGroups failed for session %s", self.id)
            raise UserError(_(
                "Could not fetch WhatsApp groups for '%(name)s'.\n%(err)s",
                name=self.name, err=str(err)[:300],
            )) from err

        # Evolution answers with a bare list on some versions and a wrapper on
        # others; whatsapp_broadcast handles both and so must this.
        groups = body if isinstance(body, list) else (body or {}).get('groups') or []
        result = []
        for group in groups:
            if not isinstance(group, dict):
                continue
            jid = str(group.get('id') or '')
            if not jid:
                continue
            result.append({
                'jid': jid,
                'name': group.get('subject') or _('Unnamed Group'),
                'size': int(group.get('size') or 0)
                        or len(group.get('participants') or []),
            })
        return result

    def action_sa_sync_groups(self):
        """Refresh sa.sales.group from WhatsApp and open the tick list.

        Groups are never deleted here. A group the number has left keeps its
        row - and its markup, its margin and its tick - so rejoining does not
        mean configuring it again.
        """
        self.ensure_one()
        SalesGroup = self.env['sa.sales.group']
        fetched = self._sa_fetch_groups()

        existing = {
            rec.group_jid: rec
            for rec in SalesGroup.search([('session_id', '=', self.id)])
        }
        created = 0
        for group in fetched:
            record = existing.get(group['jid'])
            if record:
                record.write({'name': group['name'], 'member_count': group['size']})
            else:
                SalesGroup.create({
                    'session_id': self.id,
                    'group_jid': group['jid'],
                    'name': group['name'],
                    'member_count': group['size'],
                })
                created += 1

        _logger.info("Sales Automation: synced %d group(s) for session '%s' (%d new).",
                     len(fetched), self.name, created)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Groups - %s', self.name),
            'res_model': 'sa.sales.group',
            'view_mode': 'list,form',
            'domain': [('session_id', '=', self.id)],
            'context': {'default_session_id': self.id},
        }
