# -*- coding: utf-8 -*-
"""Human takeover: when the shopkeeper writes in a chat, the assistant goes
quiet there, and comes back by itself once the shopkeeper has been silent
for the configured time.

Two ways a human is recognised:
  * a message from one of the listed shopkeeper numbers;
  * a message from the shop's own number that the assistant did not send -
    it comes back through the webhook marked `fromMe`, like the assistant's
    own replies do, but its WhatsApp id is in none of our outgoing records.

A hold is per chat: the group, or the private conversation. While it lasts,
a customer's message is recorded and left alone; the moment it expires, the
next message is handled as usual.
"""
import logging
from datetime import timedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


def _digits(value):
    return ''.join(ch for ch in str(value or '') if ch.isdigit())


def _tail(value):
    d = _digits(value)
    return d[-9:] if len(d) >= 9 else d


class SaAiSettingsTakeover(models.Model):
    _inherit = 'sa.ai.settings'

    takeover_enabled = fields.Boolean(
        'Shopkeeper takes over', default=True,
        help="When a shopkeeper writes in a chat, the assistant stops "
             "answering there until the shopkeeper has been quiet for the "
             "minutes below.")
    takeover_numbers = fields.Text(
        'Shopkeeper numbers',
        help="One WhatsApp number per line, with country code. The shop's own "
             "number is always recognised: anything typed on the shop phone "
             "that the assistant did not send counts as the shopkeeper.")
    takeover_minutes = fields.Float(
        'Resume after (minutes)', default=1.0,
        help="How long the shopkeeper must be silent before the assistant "
             "answers again. Each shopkeeper message restarts the clock. "
             "0.5 is thirty seconds.")
    takeover_status = fields.Text('Active holds', compute='_compute_takeover_status')

    def _compute_takeover_status(self):
        Hold = self.env['sa.human.hold'].sudo()
        for rec in self:
            live = Hold.search([('until', '>', fields.Datetime.now())], order='until desc')
            rec.takeover_status = '\n'.join(
                '%s - until %s (%s)' % (h.chat_label or h.chat_key,
                                        fields.Datetime.context_timestamp(rec, h.until).strftime('%H:%M:%S'),
                                        h.set_by or '') for h in live) or 'none right now'

    def _takeover_tails(self):
        self.ensure_one()
        return {_tail(l) for l in (self.takeover_numbers or '').splitlines()
                if _tail(l) and not l.strip().startswith('#')}


class SaHumanHold(models.Model):
    _name = 'sa.human.hold'
    _description = 'Assistant paused because a shopkeeper is in the chat'
    _order = 'until desc'
    _rec_name = 'chat_label'

    chat_key = fields.Char('Chat', required=True, index=True,
                           help="Group JID, or the private chat's digits.")
    chat_label = fields.Char('Chat Name')
    session_id = fields.Many2one('whatsapp.session', ondelete='set null')
    until = fields.Datetime('Held Until', required=True, index=True)
    set_by = fields.Char('Set By', help="The shopkeeper number, or 'shop phone'.")
    last_text = fields.Char('Last Shopkeeper Message')
    held_count = fields.Integer('Customer Messages Held', default=0)
    # What the customer said while the shopkeeper was in the chat. Once the
    # hold runs out unanswered, the last of these is handed to the assistant
    # by the minute job - the customer is not left waiting for their own
    # next message.
    pending_message_ids = fields.Many2many(
        'whatsapp.message', 'sa_human_hold_pending_rel', 'hold_id', 'message_id',
        string='Held Customer Messages')

    # ------------------------------------------------------------------
    @api.model
    def _settings(self):
        return self.env['sa.ai.settings'].sudo().get_settings()

    @api.model
    def chat_key_for(self, remote_jid):
        jid = str(remote_jid or '')
        return jid if jid.endswith('@g.us') else _digits(jid.split('@')[0])

    @api.model
    def is_shopkeeper(self, digits, settings=None):
        settings = settings or self._settings()
        t = _tail(digits)
        return bool(t) and t in settings._takeover_tails()

    @api.model
    def is_ours_unsent(self, session, wa_id, text, chat_key):
        """True for a `fromMe` message the assistant did not send: nothing in
        our outgoing log carries its id, and nothing sent to that chat in the
        last three minutes has the same text (a queued send may have no id)."""
        Msg = self.env['whatsapp.message'].sudo()
        if wa_id and Msg.search_count([('direction', '=', 'outgoing'),
                                       ('wa_message_id', '=', wa_id)]):
            return False
        text = (text or '').strip()
        if text:
            since = fields.Datetime.now() - timedelta(minutes=3)
            recent = Msg.search([('direction', '=', 'outgoing'),
                                 ('create_date', '>=', since),
                                 ('session_id', '=', session.id)], limit=60)
            for m in recent:
                if (m.message or '').strip() == text:
                    return False
        return True

    @api.model
    def _hold_impl(self, session, remote_jid, set_by, text='', settings=None):
        settings = settings or self._settings()
        minutes = max(0.25, float(settings.takeover_minutes or 1.0))
        key = self.chat_key_for(remote_jid)
        until = fields.Datetime.now() + timedelta(minutes=minutes)
        label = key
        if key.endswith('@g.us'):
            g = self.env['sa.sales.group'].sudo().search([('group_jid', '=', key)], limit=1)
            label = g.name if g else key.split('@')[0]
        row = self.sudo().search([('chat_key', '=', key)], limit=1)
        vals = {'until': until, 'set_by': set_by, 'last_text': (text or '')[:120],
                'session_id': session.id, 'chat_label': label}
        if row:
            row.write(vals)
        else:
            row = self.sudo().create(dict(vals, chat_key=key))
        _logger.info("Takeover: %s held for %.1f min by %s", label, minutes, set_by)
        return row

    @api.model
    def is_held(self, remote_jid):
        key = self.chat_key_for(remote_jid)
        row = self.sudo().search([('chat_key', '=', key),
                                  ('until', '>', fields.Datetime.now())], limit=1)
        if row:
            row.held_count += 1
        return bool(row)

    @api.model
    def attach_pending(self, remote_jid, message):
        key = self.chat_key_for(remote_jid)
        row = self.sudo().search([('chat_key', '=', key)], limit=1)
        if row and message:
            row.write({'pending_message_ids': [(4, message.id)]})
        return row

    @api.model
    def hold(self, session, remote_jid, set_by, text='', settings=None):
        """(see below) - wrapped so a fresh shopkeeper message also drops the
        customer messages the shopkeeper has now, by writing, answered."""
        row = self._hold_impl(session, remote_jid, set_by, text, settings)
        if row.pending_message_ids:
            row.write({'pending_message_ids': [(5, 0, 0)]})
        return row

    @api.model
    def _cron_answer_held(self):
        """Every minute: a hold that ran out with customer messages still
        unanswered hands the last one to the assistant. Group chats only -
        a private chat's next message restarts the tracker by itself."""
        now = fields.Datetime.now()
        Req = self.env['sa.group.request'].sudo()
        for row in self.sudo().search([('until', '<=', now),
                                       ('pending_message_ids', '!=', False)]):
            msgs = row.pending_message_ids.sorted(lambda m: (m.create_date, m.id))
            last = msgs[-1]
            row.write({'pending_message_ids': [(5, 0, 0)]})
            if not last.group_jid or not last.exists():
                continue
            try:
                with self.env.cr.savepoint():
                    Req._on_group_message(last)
                _logger.info("Takeover: hold on %s over - answered the held "
                             "message from %s: %r", row.chat_label,
                             last.participant_phone or '?', (last.message or '')[:50])
            except Exception as err:  # noqa: BLE001 - next minute, next message
                _logger.warning("Takeover: held message %s not answered: %s", last.id, err)
        return True

    @api.model
    def _cron_purge(self):
        old = self.sudo().search([('until', '<', fields.Datetime.now() - timedelta(days=2))])
        old.unlink()
        return True
