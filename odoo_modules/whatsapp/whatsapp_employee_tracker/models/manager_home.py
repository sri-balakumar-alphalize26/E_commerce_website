"""The manager's screen: who has replied and who has not, private chats and
groups (25 Nov 2026).

Replied: the newest message of a chat is ours. It is read from the phone's own
list, so what is typed on the phone counts at once."""
from datetime import timedelta

from odoo import fields, models

from .phone_digits import digits
from .phone_name import is_name

HOURS = 48
# The word alerts that are about how an employee speaks.
WORDS = ('profanity', 'hard_language', 'custom')


class EmployeeSessionHome(models.Model):
    _inherit = 'wa.employee.session'

    def _home_chats(self, own):
        """Every chat as the phone has it, nothing left out; own: digits of all
        our numbers. One older than two days is "old": not counted as waiting."""
        self.ensure_one()
        since = str(fields.Datetime.now() - timedelta(hours=HOURS))[:19]
        wrong = {}
        for alert in self.env['wa.keyword.alert.log'].sudo().search([
                ('employee_session_id', '=', self.id), ('message_direction', '=', 'outgoing'), ('category', 'in', WORDS),
                ('message_date', '>=', since)], order='message_date'):
            found = wrong.setdefault(digits(alert.phone)[-9:], {'words': [], 'texts': []})
            found['words'] += [w for w in (alert.matched_keywords or '').split(', ') if w and w not in found['words']]
            found['texts'].append(alert.message_text or '')
        rows = []
        for chat in self._phone_chats():
            ours = chat['from_me'] or (chat['group'] and chat.get('who') and chat['who'][-9:] in own)
            rows.append({'card': self.id, 'id': chat['id'], 'name': chat['name'], 'group': chat['group'],
                         'preview': chat['preview'] or self.env._("Message"), 'sender': chat['push'] if chat['group'] and not chat['from_me'] and is_name(chat['push']) and chat['push'] != chat['name'] else '',
                         'phone': chat['phone'], 'mine': chat['from_me'], 'unread': 0 if chat['from_me'] else chat['unread'],
                         'pic': chat['pic'] if chat['pic'].startswith('https://') else '', 'last': chat['last_id'],
                         # the list is not told later what became of it: no clock that never ends
                         'tick': '' if chat['tick'] == 'pending' else chat['tick'],
                         'date': chat['date'][:19], 'state': 'old' if chat['date'][:19] < since else 'yes' if ours else 'no',
                         'wrong': False if chat['group'] else wrong.get(digits(chat['phone'])[-9:], False)})
        return rows
