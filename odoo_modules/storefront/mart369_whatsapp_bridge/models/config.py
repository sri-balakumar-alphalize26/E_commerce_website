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
        Session = self.env['whatsapp.session'].sudo()
        sessions = Session.search([('active', '=', True)])
        labels = dict(Session._fields['status']._description_selection(self.env))
        groups['whatsapp'] = {
            'sessions': [{
                'id': s.id,
                'name': s.name or '',
                'status': s.status or 'unknown',
                'label': labels.get(s.status) or s.status or _('Unknown'),
                # The one number the panel lets this database pair, and the
                # one actually paired - they differ after a wrong-phone scan.
                'authorized': s.authorized_number or '',
                'phone': s.phone_number or '',
                'detail': s.error_message or '',
                'checked': (int(s.state_checked.timestamp() * 1000)
                            if s.state_checked else None),
            } for s in sessions],
            'sessionId': config.mart369_wa_session_id.id or False,
            'invoice': bool(config.mart369_wa_send_invoice),
            'on': {state: config._mart369_wa_on(state) for state in WA_STATES},
            'texts': {state: config._mart369_wa_text(state)
                      for state in WA_STATES},
            # Customer Links (21 Nov 2026): where each WhatsApp group-order
            # link goes - the same settings as Odoo's Sales Automation >
            # Configuration > Customer Links.
            'links': self._mart369_wa_links(),
        }
        return groups

    @api.model
    def _mart369_wa_links(self):
        """{'rows': [{key, label, to}], 'note', 'replyHours'} or {} without
        the WhatsApp group-order module."""
        if 'sa.ai.settings' not in self.env:
            return {}
        settings = self.env['sa.ai.settings'].sudo().get_settings()
        try:
            from odoo.addons.sales_automation.models.sa_ai_settings import LINK_KINDS
        except ImportError:
            return {}
        return {
            'rows': [{'key': key, 'label': label, 'to': settings._sa_link_route(key)}
                     for key, label in LINK_KINDS if 'link_%s' % key in settings._fields],
            'note': bool(settings.link_group_note),
            'replyHours': settings.link_reply_hours or 0,
        }

    @api.model
    def _mart369_wa_links_save(self, links):
        if not isinstance(links, dict) or 'sa.ai.settings' not in self.env:
            return
        settings = self.env['sa.ai.settings'].sudo().get_settings()
        vals = {}
        for key, to in (links.get('to') or {}).items():
            field = 'link_%s' % key
            if field not in settings._fields:
                continue
            if to not in ('private', 'group'):
                raise UserError(_('Choose Private chat or Group for every link.'))
            vals[field] = to
        if 'note' in links:
            vals['link_group_note'] = bool(links['note'])
        if 'replyHours' in links:
            try:
                hours = int(links['replyHours'] or 0)
            except (TypeError, ValueError):
                raise UserError(_('The reply window is a number of hours.'))
            if not 0 <= hours <= 72:
                raise UserError(_('The reply window is 0 to 72 hours.'))
            vals['link_reply_hours'] = hours
        if vals:
            settings.write(vals)

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
        if 'links' in values:
            self._mart369_wa_links_save(values['links'])
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
