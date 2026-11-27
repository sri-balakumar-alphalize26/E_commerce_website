import logging
from odoo import models, api

_logger = logging.getLogger(__name__)


class PosOrder(models.Model):
    _inherit = 'pos.order'

    @api.model
    def sync_from_ui(self, orders):
        """Add the POS *Email* mirror on order completion.

        The POS *WhatsApp* notification is sent by `whatsapp_gateway`'s own
        `sync_from_ui` override, which runs via `super()` below. We must NOT
        send WhatsApp again here, or every POS order would go out twice.
        """
        result = super().sync_from_ui(orders)

        try:
            order_ids = []
            if isinstance(result, dict) and result.get('pos.order'):
                for order_data in result['pos.order']:
                    if isinstance(order_data, dict) and order_data.get('id'):
                        order_ids.append(order_data['id'])
            elif isinstance(result, list):
                for item in result:
                    if isinstance(item, dict) and item.get('id'):
                        order_ids.append(item['id'])

            for order_id in order_ids:
                order = self.browse(order_id)
                if order.exists() and order.state in ('paid', 'done', 'invoiced'):
                    try:
                        self._send_pos_email_notification(order_id)
                    except Exception as e:
                        _logger.error(
                            "POS Email notification failed for %s: %s",
                            order.name, e,
                        )
        except Exception as e:
            _logger.error("Error triggering POS Email: %s", e)

        return result

    # ──────────────────────────────────────────────────────────────────────
    # EMAIL MIRROR
    # ──────────────────────────────────────────────────────────────────────

    def _send_pos_email_notification(self, order_id):
        """Email mirror of the WhatsApp POS notification — uses the same trigger.
        Resolves the SMTP server from the default Email Session so the mail.mail
        actually goes out."""
        order = self.browse(order_id)
        if not order.exists():
            return
        config = self.env['whatsapp.config'].sudo().get_config(order.company_id.id)
        if not config.pos_email_notify_enabled:
            _logger.info("POS Email: disabled for company %s", order.company_id.name)
            return

        session = self.env['whatsapp.email.dispatch'].with_company(order.company_id) \
            .get_email_sender_session(order.company_id)
        if not session:
            _logger.warning(
                "POS Email: company %s has no e-mail address chosen "
                "(WhatsApp and Email > Settings > Send email from).", order.company_id.name
            )
            return

        text_msg = config.format_pos_message(order)
        body_html = '<pre style="font-family:inherit;white-space:pre-wrap;">%s</pre>' % (text_msg or '')
        subject = 'POS Order %s - %s' % (order.name, order.company_id.name)

        recipients = []
        if config.pos_email_notify_owners:
            if not config.pos_owner_emails:
                _logger.warning(
                    "POS Email: 'Email POS Order to Owners' is ON but "
                    "'Owner Emails' is empty. Add at least one address (comma-separated) "
                    "in WhatsApp and Email Settings → POS Notifications."
                )
            else:
                for addr in config.pos_owner_emails.split(','):
                    addr = (addr or '').strip()
                    if addr:
                        recipients.append(addr)
        if config.pos_email_notify_customer:
            if not order.partner_id:
                _logger.info(
                    "POS Email: customer email skipped for order %s — no customer attached.",
                    order.name,
                )
            elif not order.partner_id.email:
                _logger.info(
                    "POS Email: customer '%s' has no email on file; skipped.",
                    order.partner_id.display_name,
                )
            else:
                recipients.append(order.partner_id.email)

        if not recipients:
            _logger.warning(
                "POS Email: no recipients resolved for order %s. "
                "Check the toggles + 'Owner Emails' field under "
                "WhatsApp and Email Settings → POS Notifications.",
                order.name,
            )
            return

        for to in recipients:
            try:
                # sudo() because _gateway_call reads gateway_api_key, which is
                # restricted to base.group_system - a cashier's own rights are
                # not enough to read it.
                sender = self.env['whatsapp.email.dispatch']._sender_name(order.company_id)
                sent = session.sudo().with_context(wa_from_name=sender).send_email(
                    to, subject, body_html=body_html, body_text=text_msg or '')
                if sent:
                    _logger.info("POS Email: SENT to %s for order %s via gateway "
                                 "session %s", to, order.name, session.display_name)
                else:
                    # A rule stopped it: unsubscribed, blocked word, over cap.
                    _logger.warning(
                        "POS Email: NOT SENT to %s for order %s - the gateway "
                        "refused it (opt-out, blocked word or daily cap).",
                        to, order.name)
            except Exception as e:
                _logger.error("POS Email: FAILED to %s: %s", to, e)
