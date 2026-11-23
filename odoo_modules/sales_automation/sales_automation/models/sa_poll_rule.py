# -*- coding: utf-8 -*-
"""A tap on an old poll does nothing (owner, 23 Nov 2026).

WhatsApp keeps every poll tappable for ever. An old quantity "1" was read as
YES to "confirm the order?", an old CANCEL reached the newest deal. Now:

* only the newest poll of each enquiry answers;
* a customer who starts something new (hi, a new search) closes their older ones;
* an enquiry that is dropped, cancelled, ordered or paid closes its own - except
  what goes out in that same turn;
* a tap on a closed poll: no reply, and nothing changes.

What is typed is never looked at here."""
import json
import logging
from datetime import timedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

LOOK_BACK_DAYS = 30


class SaPoll(models.Model):
    _name = 'sa.poll'
    _description = 'Poll sent to a customer'
    _order = 'id desc'

    wa_id = fields.Char(index=True, help="Empty when WhatsApp gave no id for it.")
    request_id = fields.Many2one('sa.group.request', required=True, ondelete='cascade', index=True)
    group_id = fields.Many2one('sa.sales.group', ondelete='cascade', index=True)
    options = fields.Text()
    turn = fields.Char(help="The customer's message it was sent for.")
    closed = fields.Boolean(index=True)

    def _has_option(self, label):
        self.ensure_one()
        try:
            known = json.loads(self.options or '[]')
        except ValueError:
            return False
        return (label or '').strip() in [(o or '').strip() for o in known]

    def _earlier(self):
        """Without those that went out in this very turn."""
        turn = self.env.context.get('sa_trigger_msg')
        if turn:
            return self.filtered(lambda p: p.turn != turn)
        now = self.env.cr.now()
        return self.filtered(lambda p: p.create_date < now)

    def _close(self):
        if self:
            self.sudo().write({'closed': True})
        return True


class SaGroupRequestPoll(models.Model):
    _inherit = 'sa.group.request'

    # ------------------------------------------------------------ sent
    def _ask(self, body, buttons):
        self.ensure_one()
        before = self.poll_wa_id
        res = super()._ask(body, buttons)
        if res:
            wa_id = self.poll_wa_id if self.poll_wa_id != before else ''
            self._sa_poll_sent(wa_id, [b['title'] for b in buttons], as_text=res == 'text')
        return res

    def _sa_poll_sent(self, wa_id, options, as_text=False):
        """This enquiry's newest question; its older polls are closed. A
        question that went out as text has no poll to tap."""
        self.ensure_one()
        Poll = self.env['sa.poll'].sudo()
        turn = self.env.context.get('sa_trigger_msg') or ''
        text = json.dumps(options, ensure_ascii=False)
        mine = Poll.search([('request_id', '=', self.id), ('closed', '=', False)])
        if not wa_id and not as_text and turn:
            again = mine.filtered(lambda p: p.turn == turn and p.options == text)[:1]
            if again:                   # the same question, not sent a second time
                (mine - again)._close()
                return again
        mine._close()
        if as_text:
            return Poll
        return Poll.create({'wa_id': wa_id or False, 'request_id': self.id, 'group_id': self.group_id.id,
                            'options': text, 'turn': turn})

    # ------------------------------------------------------------ closed
    def _sa_poll_close(self):
        self.env['sa.poll'].search([('request_id', 'in', self.ids), ('closed', '=', False)])._earlier()._close()

    @api.model
    def _sa_poll_open_in(self, group):
        return self.env['sa.poll'].sudo().search([
            ('group_id', '=', group.id), ('closed', '=', False),
            ('create_date', '>=', fields.Datetime.now() - timedelta(days=LOOK_BACK_DAYS))], limit=500)

    def _sa_poll_close_customer(self):
        """They started something new: their other questions in this group."""
        self.ensure_one()
        tail, lid = self._sa_id_tail(self.requester_phone), self.requester_lid

        def same(other):
            theirs = self._sa_id_tail(other.requester_phone)
            if tail and theirs:
                return tail == theirs
            return bool(lid and lid == other.requester_lid)
        polls = self._sa_poll_open_in(self.group_id).filtered(
            lambda p: p.request_id != self and same(p.request_id))
        polls.with_context(self.env.context)._earlier()._close()

    @api.model_create_multi
    def create(self, vals_list):
        requests = super().create(vals_list)
        if self.env.context.get('sa_trigger_msg'):
            for request in requests.filtered('group_id'):
                request._sa_poll_close_customer()
        return requests

    def _drop(self, reason):
        self._sa_poll_close()
        return super()._drop(reason)

    def _sa_cancel_deal(self):
        self._sa_poll_close()
        return super()._sa_cancel_deal()

    def _place_order(self):
        self._sa_poll_close()
        return super()._place_order()

    def _on_confirmed(self):
        self._sa_poll_close()
        return super()._on_confirmed()

    def _sa_group_confirmed(self, order):
        if not self.sa_paid_told_on:        # a task tried again keeps what it sent
            self._sa_poll_close()
        return super()._sa_group_confirmed(order)

    # ------------------------------------------------------------ tapped
    @api.model
    def _sa_poll_is_old(self, poll_ref):
        """This poll is one of ours and its time is over."""
        poll_ref = (poll_ref or '').strip()
        if not poll_ref:
            return False
        poll = self.env['sa.poll'].sudo().search([('wa_id', '=', poll_ref)], limit=1)
        if poll:
            return poll.closed or poll.request_id._sa_poll_answered(poll_ref)
        asked = self._sa_by_poll(poll_ref)      # sent before this rule
        return bool(asked) and (asked.poll_wa_id != poll_ref or asked._sa_poll_answered(poll_ref))

    @api.model
    def _sa_poll_known(self, poll_ref):
        poll_ref = (poll_ref or '').strip()
        return bool(poll_ref) and bool(
            self.env['sa.poll'].sudo().search_count([('wa_id', '=', poll_ref)], limit=1) or self._sa_by_poll(poll_ref))

    @api.model
    def _sa_poll_stale(self, group, message, poll_ref, label):
        if self._sa_poll_known(poll_ref):
            return self._sa_poll_is_old(poll_ref)
        # No id, or one we do not know: taken only as the answer to an open
        # question of theirs - with an unknown id, one whose own id was lost.
        mine = self._sa_poll_open_in(group).filtered(lambda p: p.request_id._sa_asked_of(message))
        if poll_ref:
            mine = mine.filtered(lambda p: not p.wa_id)
        return not any(p._has_option(label) for p in mine)

    @api.model
    def _on_group_message(self, message):
        poll_ref = (self.env.context.get('sa_poll_ref') or '').strip()
        vote = bool(poll_ref or self.env.context.get('sa_is_poll_vote'))
        text = (message.message or '').strip()
        group = self.env['sa.sales.group'].sudo().search([
            ('session_id', '=', message.session_id.id), ('group_jid', '=', message.group_jid),
            ('enabled', '=', True)], limit=1) if text else self.env['sa.sales.group']
        if group and group.group_type != 'vendor':
            if vote:
                if self._sa_poll_stale(group, message, poll_ref, text):
                    _logger.info("Sales Automation: a tap on an old poll (%s) - nothing done", poll_ref or 'no id')
                    return True
            elif self._sa_is_greeting(text):
                self._sa_poll_open_in(group).filtered(lambda p: p.request_id._sa_asked_of(message))._close()
        return super()._on_group_message(message)
