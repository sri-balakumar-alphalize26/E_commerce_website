"""Wizard that lets the user pick which Email session and which WhatsApp
session to use for a manual send (when multiple are connected)."""

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.modules.registry import Registry
import logging
import threading

_logger = logging.getLogger(__name__)


def _send_in_background(dbname, uid, context, job):
    """The slow part of a manual send (PDF ~5 s, WhatsApp upload, e-mail) off
    the user's screen: Send closes at once, and a corner message says how it
    went when it is done (26 Nov 2026 - pressing Send waited ~17 s)."""
    def run():
        threading.current_thread().dbname = dbname
        try:
            with Registry(dbname).cursor() as cr:
                env = api.Environment(cr, uid, context)
                record = env[job['model']].browse(job['id']).exists()
                if not record:
                    return
                Session = env['whatsapp.session']
                res = record.with_context(wa_send_pdf=job['wa_pdf'], email_send_pdf=job['mail_pdf']) \
                    ._send_via_channels_with_sessions(
                        send_email=job['email'], send_whatsapp=job['whatsapp'],
                        email_session=Session.browse(job['email_session']) if job['email'] else None,
                        whatsapp_session=Session.browse(job['wa_session']) if job['whatsapp'] else None)
                params = (res or {}).get('params') or {}
                ok = params.get('type', 'success') == 'success'
                env.user._bus_send('simple_notification', {
                    'type': 'success' if ok else 'warning',
                    'title': (_("✓ Sent: %s") if ok else _("Not sent: %s")) % job['label'],
                    'message': params.get('message') or '',
                    'sticky': not ok,
                })
        except Exception as err:  # noqa: BLE001 - nobody waits on this thread: tell the user
            _logger.exception("background send of %s,%s failed", job['model'], job['id'])
            try:
                with Registry(dbname).cursor() as cr:
                    api.Environment(cr, uid, context).user._bus_send('simple_notification', {
                        'type': 'danger', 'title': _("Not sent: %s") % job['label'],
                        'message': str(err)[:300], 'sticky': True})
            except Exception:  # noqa: BLE001
                pass
    threading.Thread(target=run, name='whatsapp-email-send', daemon=True).start()


class SendChannelWizard(models.TransientModel):
    _name = 'whatsapp.send.channel.wizard'
    _description = 'Pick channel(s) for sending a document'

    res_model = fields.Char(required=True)
    res_id = fields.Integer(required=True)

    record_label = fields.Char(readonly=True)
    partner_id = fields.Many2one('res.partner', readonly=True)

    send_email = fields.Boolean(string='Send by Email', default=True)
    send_whatsapp = fields.Boolean(string='Send by WhatsApp', default=True)

    # The gateway session carries email as well as WhatsApp, on the vendor's
    # mail account. This used to point at email.session, which needed its own
    # SMTP login before it would appear here at all - and that login was never
    # used to deliver anything once gateway routing was on.
    email_session_id = fields.Many2one(
        'whatsapp.session', string='From Email Account',
        domain="[('use_email', '=', True), ('authorized_email', '!=', False)]",
    )
    whatsapp_session_id = fields.Many2one(
        'whatsapp.session', string='From WhatsApp Session',
        domain="[('status', '=', 'connected')]",
    )
    email_send_pdf = fields.Boolean(
        string='Attach the PDF to the e-mail', default=True,
        help="Ticked: details + PDF. Not ticked: the details only. Starts as the company's setting.")
    wa_send_pdf = fields.Boolean(
        string='Send the PDF on WhatsApp', default=True,
        help="Ticked: the PDF with the details as its caption. Not ticked: the details as a message. "
             "Starts as the company's setting.")

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        ctx = self.env.context
        if ctx.get('default_res_model') and ctx.get('default_res_id'):
            record = self.env[ctx['default_res_model']].browse(ctx['default_res_id'])
            if record.exists():
                partner = getattr(record, 'partner_id', False)
                vals.setdefault('partner_id', partner.id if partner else False)
                vals.setdefault('record_label', getattr(record, 'display_name', '') or getattr(record, 'name', ''))

        # Pre-pick the document's company's choices (any number can still be
        # picked by hand - a shared number is allowed).
        company = self.env.company
        if ctx.get('default_res_model') and ctx.get('default_res_id'):
            record = self.env[ctx['default_res_model']].browse(ctx['default_res_id']).exists()
            company = (getattr(record, 'company_id', False) if record else False) or company
        dispatch = self.env['whatsapp.email.dispatch'].with_company(company)
        e = dispatch.get_email_sender_session(company)
        w = dispatch.get_default_whatsapp_session(company)
        if 'email_session_id' in fields_list and e:
            vals.setdefault('email_session_id', e.id)
        if 'whatsapp_session_id' in fields_list and w:
            vals.setdefault('whatsapp_session_id', w.id)
        if 'wa_send_pdf' in fields_list:
            config = dispatch.get_config(company)
            vals['wa_send_pdf'] = config.wa_send_pdf if config else True
        if 'email_send_pdf' in fields_list:
            config = dispatch.get_config(company)
            vals['email_send_pdf'] = config.email_send_pdf if config else True
        return vals

    def action_show_steps(self):
        return self.env['whatsapp.session']._wa_help_action(
            '/whatsapp_email/static/src/help/send_documents.html?for=manual', _("Help - Send documents"))

    def action_send(self):
        self.ensure_one()
        if not (self.send_email or self.send_whatsapp):
            raise UserError(_("Select at least one channel (Email or WhatsApp)."))
        if self.send_email and not self.email_session_id:
            raise UserError(_("Pick an Email account, or uncheck Send by Email."))
        if self.send_whatsapp and not self.whatsapp_session_id:
            raise UserError(_("Pick a WhatsApp session, or uncheck Send by WhatsApp."))

        record = self.env[self.res_model].browse(self.res_id)
        if not record.exists():
            raise UserError(_("Record no longer exists."))

        if hasattr(record, '_send_via_channels_with_sessions'):
            # what can be told at once, is told at once (no waiting for it)
            partner = getattr(record, 'partner_id', False)
            if self.send_email and partner and not partner.email:
                raise UserError(_("%s has no e-mail address. Add it on the contact, or untick Send by Email.",
                                  partner.display_name))
            if self.send_whatsapp and partner and not (partner.phone or getattr(partner, 'mobile', False)):
                raise UserError(_("%s has no phone number. Add it on the contact, or untick Send by WhatsApp.",
                                  partner.display_name))
            job = {
                'model': self.res_model, 'id': self.res_id, 'label': record.display_name,
                'email': self.send_email, 'whatsapp': self.send_whatsapp,
                'email_session': self.email_session_id.id, 'wa_session': self.whatsapp_session_id.id,
                'wa_pdf': self.wa_send_pdf, 'mail_pdf': self.email_send_pdf,
            }
            context = {k: v for k, v in self.env.context.items() if k in ('lang', 'tz', 'allowed_company_ids')}
            dbname, uid = self.env.cr.dbname, self.env.uid
            # after this transaction is saved, so the background sees the document as it is now
            self.env.cr.postcommit.add(lambda: _send_in_background(dbname, uid, context, job))
            return {
                'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {
                    'title': _("Sending %s …", record.display_name),
                    'message': _("You can go on working. A message shows here when it is sent; the chatter shows each channel."),
                    'type': 'info', 'sticky': False,
                    'next': {'type': 'ir.actions.act_window_close'},
                },
            }
        raise UserError(_(
            "Model %s does not implement _send_via_channels_with_sessions yet."
        ) % self.res_model)
