"""Settings > WhatsApp: the shop's own words, one switch per step.

The journey map had this card marked "To add - after WhatsApp is connected".
It is connected now, so the tab exists: which session speaks, whether each
step of an order says anything, what it says, and whether a delivered order
carries its invoice. Same pattern as every other group - the fields live on
`mart369.config`, the console reads and writes them through
`_mart369_admin_settings_groups` / `_mart369_admin_save_group`.

The wording is validated at save. A text with a broken placeholder would
otherwise fail quietly at send time (the notifier logs and moves on), which
is a message nobody ever finds out was never sent.
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.mart369_support.models.whatsapp import MESSAGES

# console key -> (switch field, text field, mart369 state)
WA_STATES = ('placed', 'packed', 'shipped', 'out', 'delivered', 'cancelled')


class Mart369Config(models.Model):
    _inherit = 'mart369.config'

    mart369_wa_session_id = fields.Many2one(
        'whatsapp.session', string='WhatsApp session',
        help='Which connected number the shop sends order updates from. '
             'Empty: whichever session is connected.')
    mart369_wa_send_invoice = fields.Boolean(
        string='Send the invoice when delivered', default=True)

    mart369_wa_on_placed = fields.Boolean(string='Tell: placed', default=True)
    mart369_wa_on_packed = fields.Boolean(string='Tell: packed', default=True)
    mart369_wa_on_shipped = fields.Boolean(string='Tell: shipped', default=True)
    mart369_wa_on_out = fields.Boolean(string='Tell: out for delivery', default=True)
    mart369_wa_on_delivered = fields.Boolean(string='Tell: delivered', default=True)
    mart369_wa_on_cancelled = fields.Boolean(string='Tell: cancelled', default=True)

    mart369_wa_text_placed = fields.Text(string='Wording: placed')
    mart369_wa_text_packed = fields.Text(string='Wording: packed')
    mart369_wa_text_shipped = fields.Text(string='Wording: shipped')
    mart369_wa_text_out = fields.Text(string='Wording: out for delivery')
    mart369_wa_text_delivered = fields.Text(string='Wording: delivered')
    mart369_wa_text_cancelled = fields.Text(string='Wording: cancelled')

    # ------------------------------------------------------------- reading

    def _mart369_wa_on(self, state):
        field = 'mart369_wa_on_%s' % state
        return bool(self[field]) if field in self._fields else False

    def _mart369_wa_text(self, state):
        field = 'mart369_wa_text_%s' % state
        custom = self[field] if field in self._fields else ''
        return (custom or '').strip() or MESSAGES.get(state, '')

    @api.model
    def _mart369_admin_settings_groups(self):
        groups = super()._mart369_admin_settings_groups()
        config = self._get()
        sessions = self.env['whatsapp.session'].sudo().search(
            [('active', '=', True)])
        groups['whatsapp'] = {
            'sessions': [{
                'id': s.id,
                'name': s.name or '',
                'status': s.status or 'unknown',
                'checked': (int(s.state_checked.timestamp() * 1000)
                            if s.state_checked else None),
            } for s in sessions],
            'sessionId': config.mart369_wa_session_id.id or False,
            'invoice': bool(config.mart369_wa_send_invoice),
            'on': {state: config._mart369_wa_on(state) for state in WA_STATES},
            'texts': {state: config._mart369_wa_text(state)
                      for state in WA_STATES},
        }
        return groups

    # ------------------------------------------------------------- writing

    @api.model
    def _mart369_admin_save_group(self, group, values):
        if group != 'whatsapp':
            return super()._mart369_admin_save_group(group, values)
        config = self._get()
        vals = {}
        if 'sessionId' in values:
            session_id = values['sessionId'] or False
            if session_id:
                session = self.env['whatsapp.session'].sudo().browse(
                    int(session_id)).exists()
                if not session:
                    raise UserError(_('There is no such WhatsApp session.'))
                session_id = session.id
            vals['mart369_wa_session_id'] = session_id
        if 'invoice' in values:
            vals['mart369_wa_send_invoice'] = bool(values['invoice'])
        for state in WA_STATES:
            on = (values.get('on') or {})
            if state in on:
                vals['mart369_wa_on_%s' % state] = bool(on[state])
            texts = (values.get('texts') or {})
            if state in texts:
                text = (texts[state] or '').strip()
                if text:
                    try:
                        text % {'ref': 'X', 'eta': '', 'link': ''}
                    except (KeyError, TypeError, ValueError):
                        raise UserError(_(
                            'The %s wording has a broken placeholder. Use '
                            '%%(ref)s, %%(eta)s and %%(link)s.', state))
                # Empty, or the shipped default, stores as empty - the
                # default keeps working and keeps translating.
                vals['mart369_wa_text_%s' % state] = (
                    text if text != MESSAGES.get(state, '') else False)
        if vals:
            config.write(vals)
        return True

    # ----------------------------------------------------------- check now

    @api.model
    def mart369_admin_wa_check(self):
        """The Settings tab's Check now button: ask the gateway, not the
        cache."""
        sessions = self.env['whatsapp.session'].sudo().search(
            [('active', '=', True)])
        for session in sessions:
            try:
                session._refresh_state(force=True)
            except Exception:  # noqa: BLE001 - an offline gateway is an answer
                pass
        return self._mart369_admin_settings_groups().get('whatsapp', {})
