"""The website's order updates, actually sent.

`mart369.whatsapp` (mart369_support) decided *whether* to speak - two
consents, a number to reach - and then had no gateway to speak through. Now
there is one. This override keeps every one of its decisions and replaces
only the mouth: the message goes out through a real `whatsapp.session`, the
wording and the per-state switches live on the console's Settings, and a
delivered order can carry its invoice as a PDF.

Two silences, on purpose:

* a **WhatsApp-channel order** gets nothing from here - the selling flow
  already talks to that customer in their own chat, step by step;
* a session that is offline **queues** rather than fails: the gateway stores
  the message as pending and its outbox cron sends it when the number comes
  back, so "queued" counts as told.
"""

import logging

from odoo import api, models

from odoo.addons.mart369_support.models.whatsapp import MESSAGES, LINK_PARAM, DEFAULT_LINK
from odoo.addons.whatsapp_gateway.models.whatsapp_session import WhatsAppQueued

_logger = logging.getLogger(__name__)


class Mart369Whatsapp(models.AbstractModel):
    _inherit = 'mart369.whatsapp'

    @api.model
    def _mart369_available(self):
        """There is a gateway module; whether a session is connected is the
        send's problem, because an offline session still queues."""
        return 'whatsapp.session' in self.env

    @api.model
    def _mart369_session(self):
        """Which number the shop speaks from: the one picked on Settings,
        else whichever session is connected, else any active one."""
        Session = self.env['whatsapp.session'].sudo()
        config = self.env['mart369.config'].sudo()._get()
        session = config.mart369_wa_session_id
        if session and session.active:
            return session
        return (Session.get_connected_session()
                or Session.search([('active', '=', True)], limit=1))

    @api.model
    def _mart369_notify(self, order, state):
        """Send one update, if everything lines up. Never raises."""
        if order.mart369_channel == 'whatsapp':
            return False
        config = self.env['mart369.config'].sudo()._get()
        if not config._mart369_wa_on(state):
            return False
        template = config._mart369_wa_text(state)
        if not template or not self._mart369_wants(order):
            return False
        if not self._mart369_available():
            _logger.info(
                'mart369: no WhatsApp gateway installed, not telling %s about %s',
                order.partner_id.display_name, order.mart369_ref)
            return False
        link = (self.env['ir.config_parameter'].sudo().get_param(LINK_PARAM)
                or DEFAULT_LINK)
        try:
            body = template % {
                'ref': order.mart369_ref or '',
                'eta': order.mart369_eta or '',
                'link': link % (order.mart369_ref or '') if '%s' in link else link,
            }
        except (KeyError, TypeError, ValueError):
            _logger.warning('mart369: bad WhatsApp wording for %s', state)
            return False
        sent = self._mart369_send(order, body)
        if sent and state == 'delivered' and config.mart369_wa_send_invoice:
            self._mart369_send_invoice(order)
        return sent

    @api.model
    def _mart369_send(self, order, body):
        """Through the session, and queued counts as sent."""
        number = self._mart369_number(order)
        session = self._mart369_session()
        if not session or not number:
            _logger.info('mart369: no WhatsApp session to tell %s about %s',
                         order.partner_id.display_name, order.mart369_ref)
            return False
        try:
            session.send_message(number, body)
            return True
        except WhatsAppQueued:
            return True
        except Exception:  # noqa: BLE001 - an update is never worth an order
            _logger.exception('mart369: could not send a WhatsApp update for %s',
                              order.mart369_ref)
        return False

    @api.model
    def _mart369_send_invoice(self, order):
        invoice = order.sudo().invoice_ids.filtered(
            lambda m: m.state == 'posted')[:1]
        if not invoice:
            return False
        number = self._mart369_number(order)
        session = self._mart369_session()
        if not session or not number:
            return False
        try:
            session.send_odoo_report(
                number, 'mart369_order.action_report_mart369_invoice',
                invoice, caption=self.env._('Your 369 Mart invoice'))
            return True
        except WhatsAppQueued:
            return True
        except Exception:  # noqa: BLE001
            _logger.exception('mart369: could not send the invoice for %s',
                              order.mart369_ref)
        return False
