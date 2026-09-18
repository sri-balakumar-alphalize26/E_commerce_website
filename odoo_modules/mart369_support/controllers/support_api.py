"""The support routes.

Three endpoints, and the shapes are not negotiable:

* `/chat` returns **`{text, actions?, chips?, agent?}`** and nothing else -
  `SupportBot.jsx:169` rebuilds the message from exactly those four fields and
  drops anything more.
* `/agent/say` returns a **bare string** under `reply` - `SupportBot.jsx:167`
  pushes it straight into the transcript without unwrapping.
* `/greeting` is called inside a 650 ms timer, so it has to be quick.

Everything is scoped to the signed-in customer. The bot only ever reads that
customer's own orders and wallet, and a ticket is found within their own
tickets - so there is no id here anyone could guess their way into.
"""

import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

_GET = {'type': 'http', 'auth': 'user', 'methods': ['GET'], 'csrf': False, 'sitemap': False}
_POST = {'type': 'http', 'auth': 'user', 'methods': ['POST'], 'csrf': False, 'sitemap': False}

MAX_INPUT = 500


class Mart369SupportApi(http.Controller):

    # --------------------------------------------------------------- helpers

    def _json(self, payload, status=200):
        return request.make_json_response(payload, status=status)

    def _body(self):
        try:
            data = request.get_json_data()
        except Exception:
            data = None
        return data if isinstance(data, dict) else {}

    def _fail(self, error, field=None, status=400):
        payload = {'ok': False, 'error': error}
        if field:
            payload['field'] = field
        return self._json(payload, status=status)

    def _me(self):
        return request.env.user.partner_id

    def _said(self):
        return (self._body().get('text') or '').strip()[:MAX_INPUT]

    def _ticket(self):
        """This customer's open ticket, if they have one."""
        return request.env['mart369.ticket'].sudo().search([
            ('partner_id', '=', self._me().id),
            ('state', 'in', ('new', 'open', 'waiting')),
        ], limit=1)

    # ---------------------------------------------------------------- routes

    @http.route('/369mart/support/greeting', **_GET)
    def greeting(self, **kwargs):
        """What the panel opens with. Called inside a short timer, so it stays
        cheap - no order lookups here."""
        payload = request.env['mart369.bot']._mart369_greeting(self._me())
        payload['ok'] = True
        ticket = self._ticket()
        if ticket:
            # They already asked for a person, so pick the conversation up
            # rather than greeting them as if nothing had happened.
            payload['agent'] = True
            payload['ticket'] = ticket._mart369_serialize()
        return self._json(payload)

    @http.route('/369mart/support/chat', **_POST)
    def chat(self, **kwargs):
        """One question, one answer.

        The reply is returned exactly as the panel expects it; `ok` is added
        alongside and ignored by the component, which only copies four fields.
        """
        said = self._said()
        if not said:
            return self._fail('Say something and I will help.')
        reply = request.env['mart369.bot']._mart369_reply(self._me(), said)
        reply['ok'] = True
        return self._json(reply)

    @http.route('/369mart/support/agent', **_POST)
    def agent(self, **kwargs):
        """Ask for a person. This is where a real ticket is opened.

        The app used to say "I've noted this against your order" and note
        nothing. Now there is something to note it against.
        """
        said = self._said() or 'Asked for a support agent'
        ticket = request.env['mart369.ticket']._mart369_open(self._me(), said)
        ticket._mart369_say(said, from_customer=True)
        return self._json({
            'ok': True,
            'ticket': ticket._mart369_serialize(),
            # The greeting a person gives, as a bare string.
            'reply': "Hi, I'm Anjali from 369 Mart support. I can see your recent "
                     'orders - tell me what went wrong.',
        }, status=201)

    @http.route('/369mart/support/agent/say', **_POST)
    def agent_say(self, **kwargs):
        """A message to the person handling it.

        Kept on the ticket rather than in the tab, which is the whole point:
        an operator picking this up sees what has already been said instead of
        making the customer type it twice.
        """
        said = self._said()
        if not said:
            return self._fail('Say something and I will pass it on.')
        ticket = self._ticket()
        if not ticket:
            ticket = request.env['mart369.ticket']._mart369_open(self._me(), said)
        ticket._mart369_say(said, from_customer=True)
        return self._json({
            'ok': True,
            'reply': request.env['mart369.bot']._mart369_agent_reply(
                self._me(), ticket, said),
        })

    @http.route('/369mart/support/ticket', **_GET)
    def ticket(self, **kwargs):
        """The open conversation, so it survives the tab closing."""
        ticket = self._ticket()
        if not ticket:
            return self._json({'ok': True, 'ticket': None})
        return self._json({'ok': True, 'ticket': ticket._mart369_serialize()})
