import logging
from odoo import _, models, fields, api

_logger = logging.getLogger(__name__)


class WhatsAppConfig(models.Model):
    """Extends the shared `whatsapp.config` (owned by `whatsapp_gateway`) with the
    Email + cross-channel auto-send settings.

    The base WhatsApp/POS fields (`company_id`, `pos_notify_*`, `pos_session_id`,
    `pos_message_template`, `owner_number_ids`), the `whatsapp.owner.number`
    model, `get_config()` and `format_pos_message()` all live in
    `whatsapp_gateway` and are reused as-is — they are NOT redefined here.
    """
    _inherit = 'whatsapp.config'

    # ──────────────────────────────────────────────────────────────────────
    # DEFAULT SESSIONS
    # ──────────────────────────────────────────────────────────────────────
    default_email_session_id = fields.Many2one(
        'email.session', string='Default Email Session',
        domain="[('active', '=', True), ('status', '=', 'connected')]",
        help='DEPRECATED - no longer used for sending. Email now goes out on '
             'the gateway session, which holds the mail account, so there is '
             'nothing to pick here. Kept only for the IMAP reply polling that '
             'still reads these records.',
    )
    default_whatsapp_session_id = fields.Many2one(
        'whatsapp.session', string='Send WhatsApp from',
        domain="[('active', '=', True)]",
        help="The number this company's quotations, orders, invoices and receipts go out on. "
             "Any number of the database may be chosen: pick the same one for every company to "
             "share it. Empty: the company's own connected number, otherwise nothing is sent.",
    )
    email_session_id = fields.Many2one(
        'whatsapp.session', string='Send email from',
        domain="[('active', '=', True), ('use_email', '=', True), ('authorized_email', '!=', False)]",
        help="The e-mail address this company's documents are mailed from (the account lives on "
             "the WhatsApp panel next to that number). Empty: a number of this company that has an "
             "e-mail, otherwise nothing is mailed. Give a number its address with Add email.",
    )
    sender_name = fields.Char(
        "Sender name",
        help="Shown as the e-mail's sender name, in 'Regards, ...' and at the end of WhatsApp messages "
             "of this company's documents. Empty: the database name.")
    wa_send_pdf = fields.Boolean(
        "Send the PDF on WhatsApp", default=True,
        help="Ticked: the document's PDF, with its details as the caption. "
             "Not ticked: no PDF - the details (lines, quantities, prices, tax, total) as a message. "
             "E-mail always carries the PDF.")
    email_send_pdf = fields.Boolean(
        "Attach the PDF to e-mails", default=True,
        help="Ticked: the e-mail shows the details and has the PDF attached. "
             "Not ticked: the details in the e-mail only, no attachment.")
    wa_status_text = fields.Char(string="WhatsApp status", compute='_compute_channel_status')
    email_status_text = fields.Char(string="Email status", compute='_compute_channel_status')
    parent_company_id = fields.Many2one(related='company_id.parent_id', string="Branch of", readonly=True)
    company_session_ids = fields.Many2many(
        'whatsapp.session', string="Numbers of this company", compute='_compute_company_sessions',
        help="Every number connected for this company (here, in WA Tracker or in Sales Automation).")
    number_count = fields.Integer("Numbers", compute='_compute_company_sessions')
    email_count = fields.Integer("E-mails", compute='_compute_company_sessions')

    @api.depends('company_id')
    def _compute_company_sessions(self):
        Session = self.env['whatsapp.session'].sudo()
        for rec in self:
            sessions = Session.search([('company_id', '=', rec.company_id.id), ('active', '=', True)]) \
                if rec.company_id else Session.browse()
            rec.company_session_ids = sessions
            rec.number_count = len(sessions)
            rec.email_count = len(sessions.filtered('authorized_email'))

    @api.depends('default_whatsapp_session_id', 'default_whatsapp_session_id.status',
                 'email_session_id', 'email_session_id.authorized_email', 'company_id')
    def _compute_channel_status(self):
        dispatch = self.env['whatsapp.email.dispatch']
        for rec in self:
            company = rec.company_id or self.env.company
            wa = dispatch.with_company(company).get_default_whatsapp_session(company) if company else False
            mail = dispatch.with_company(company).get_email_sender_session(company) if company else False
            def how(chosen, session):
                if chosen:
                    return ''
                if session.company_id and session.company_id != company:
                    return ' (from %s)' % session.company_id.name     # a branch using its parent's
                return ' (own number, no Main ticked)'
            if wa:
                rec.wa_status_text = '%s - %s%s' % (
                    wa.name, dict(wa._fields['status'].selection).get(wa.status, wa.status or ''),
                    how(rec.default_whatsapp_session_id, wa))
            else:
                rec.wa_status_text = 'Not set - nothing is sent on WhatsApp for %s' % (company.name if company else '')
            if mail:
                rec.email_status_text = '%s (%s)%s' % (
                    mail.authorized_email, mail.name, how(rec.email_session_id, mail))
            else:
                rec.email_status_text = 'Not set - nothing is e-mailed for %s' % (company.name if company else '')

    # ── Choosing another company's number here = moving it (27 Nov 2026) ─────
    def _wa_foreign(self, session):
        """The number belongs to an unrelated company (not this one, its parent or branch)."""
        return bool(session and session.company_id and self.company_id
                    and not session._wa_related(session.company_id, self.company_id))

    @api.onchange('default_whatsapp_session_id', 'email_session_id')
    def _onchange_wa_foreign_number(self):
        for field in ('default_whatsapp_session_id', 'email_session_id'):
            session = self[field]
            if self._wa_foreign(session):
                lines = session._wa_move_plan(self.company_id)
                return {'warning': {
                    'title': _("This number belongs to %s", session.company_id.name),
                    'message': _("Save moves %(num)s to %(co)s:\n%(what)s\n\nDiscard to keep it as it is.",
                                 num=session.name, co=self.company_id.name,
                                 what='\n'.join('• ' + line for line in lines)),
                }}
        return None

    def write(self, vals):
        moves = []
        if not self.env.context.get('wa_share'):
            for field in ('default_whatsapp_session_id', 'email_session_id'):
                if vals.get(field):
                    session = self.env['whatsapp.session'].sudo().browse(vals[field])
                    moves += [(session, rec.company_id) for rec in self if rec._wa_foreign(session)]
        res = super().write(vals)
        for session, company in moves:        # confirmed by Save after the pop-up
            session._wa_move_to_company(company)
        return res

    def action_use_for_all_companies(self):
        """Copy this company's two choices (and its auto-send switches) to
        every other company: one WhatsApp + one e-mail for all."""
        self.ensure_one()
        toggles = [name for name in self._fields if name.startswith('auto_send_')]
        vals = {name: self[name] for name in toggles}
        vals.update({
            'default_whatsapp_session_id': self.default_whatsapp_session_id.id,
            'wa_send_pdf': self.wa_send_pdf,
            'email_send_pdf': self.email_send_pdf,
            'email_session_id': self.email_session_id.id,
        })
        done = []
        for company in self.env['res.company'].sudo().search([('id', '!=', self.company_id.id)]):
            # sharing on purpose: the number is NOT moved to each company
            self.sudo().get_config(company.id).with_context(wa_share=True).write(vals)
            done.append(company.name)
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {
                'title': 'Copied to all companies',
                'message': ('%s now send like %s.' % (', '.join(done), self.company_id.name))
                           if done else 'There is no other company.',
                'type': 'success', 'sticky': False,
            },
        }

    def action_connect_number(self):
        """The connect screen, for a new number of this company."""
        self.ensure_one()
        # company_mode: a number for the company itself - WA Tracker (when it is
        # installed) does not ask for an employee then.
        return {'type': 'ir.actions.client', 'tag': 'whatsapp_gateway.connect',
                'name': 'Connect a number',
                'params': {'company_id': self.company_id.id, 'company_mode': True}}

    panel_linked = fields.Boolean(compute='_compute_panel_link')
    panel_link_text = fields.Char("WhatsApp panel", compute='_compute_panel_link')

    def _compute_panel_link(self):
        info = self.env['whatsapp.session'].sudo()._panel_link_info()
        for rec in self:
            rec.panel_linked = info['linked']
            rec.panel_link_text = info['text']

    def action_send_steps(self):
        return self.env['whatsapp.session']._wa_help_action(
            '/whatsapp_email/static/src/help/send_documents.html', _("Help - Send documents"))

    def action_send_video(self):
        return self.env['whatsapp.session']._wa_help_action(
            '/whatsapp_email/static/src/help/send_documents.webm', _("Video - Send documents"))

    def action_link_panel(self):
        return self.env['whatsapp.session'].action_link_panel()

    def action_open_numbers(self):
        return self.env['ir.actions.actions']._for_xml_id('whatsapp_gateway.action_whatsapp_session')

    # Backward-compat: admin_email + from_email now read from the default email session.
    admin_email = fields.Char(
        string='Default Admin Email',
        compute='_compute_admin_email', store=False,
        help='Default email address. Comes from the Default Email Session.',
    )
    from_email = fields.Char(
        string='Default Send From',
        compute='_compute_admin_email', store=False,
    )

    @api.depends('default_email_session_id',
                 'default_email_session_id.email_address',
                 'default_email_session_id.from_email')
    def _compute_admin_email(self):
        for rec in self:
            sess = rec.default_email_session_id
            rec.admin_email = sess.email_address if sess else False
            rec.from_email = (sess.from_email or sess.email_address) if sess else False

    # ──────────────────────────────────────────────────────────────────────
    # AUTO-SEND TOGGLES (Email + WhatsApp, per event)
    # ──────────────────────────────────────────────────────────────────────

    # Sales — Quotation/SO
    auto_send_so_quotation_email = fields.Boolean(
        string='Auto Email Quotation',
        help="Email the quotation PDF when state changes to 'sent' (Send by Email pressed).",
    )
    auto_send_so_quotation_wa = fields.Boolean(
        string='Auto WhatsApp Quotation',
        help="WhatsApp the quotation PDF when state changes to 'sent'.",
    )
    auto_send_so_confirm_email = fields.Boolean(
        string='Auto Email on SO Confirm',
        help='Email the sale order PDF to the customer when the order is confirmed.',
    )
    auto_send_so_confirm_wa = fields.Boolean(
        string='Auto WhatsApp on SO Confirm',
        help='WhatsApp the sale order PDF to the customer when the order is confirmed.',
    )

    # Purchase
    auto_send_po_confirm_email = fields.Boolean(
        string='Auto Email PO on Confirm',
        help='Email the purchase order PDF to the vendor when the PO is confirmed.',
    )
    auto_send_po_confirm_wa = fields.Boolean(
        string='Auto WhatsApp PO on Confirm',
        help='WhatsApp the purchase order PDF to the vendor when the PO is confirmed.',
    )

    # Vendor bills
    auto_send_bill_email = fields.Boolean(
        string='Auto Email Vendor Bill on Post',
        help='Email the vendor bill PDF when posted.',
    )
    auto_send_bill_wa = fields.Boolean(
        string='Auto WhatsApp Vendor Bill on Post',
        help='WhatsApp the vendor bill PDF when posted.',
    )

    # Customer invoices
    auto_send_invoice_email = fields.Boolean(
        string='Auto Email Customer Invoice on Post',
        help='Email the customer invoice PDF to the customer when posted.',
    )
    auto_send_invoice_wa = fields.Boolean(
        string='Auto WhatsApp Customer Invoice on Post',
        help='WhatsApp the customer invoice PDF to the customer when posted.',
    )

    # Payment receipts (account.payment.action_post)
    auto_send_payment_receipt_email = fields.Boolean(
        string='Auto Email Payment Receipt',
        help='Email a receipt to the customer when an inbound payment is '
             'posted, OR a remittance to the vendor when an outbound payment '
             'is posted.',
    )
    auto_send_payment_receipt_wa = fields.Boolean(
        string='Auto WhatsApp Payment Receipt',
        help='WhatsApp a receipt to the customer/vendor when a payment is '
             'posted.',
    )

    # ──────────────────────────────────────────────────────────────────────
    # POS EMAIL — mirrors the WhatsApp POS auto-send owned by whatsapp_gateway
    # ──────────────────────────────────────────────────────────────────────
    pos_email_notify_enabled = fields.Boolean(
        string='Enable POS Email Notifications', default=False,
    )
    pos_email_notify_owners = fields.Boolean(
        string='Email POS Order to Owners',
        help='Email the POS order summary to the addresses listed in Owner Emails '
             'when a POS order is paid/done/invoiced.',
    )
    pos_email_notify_customer = fields.Boolean(
        string='Email POS Receipt to Customer',
        help='Email the POS order summary to the customer (partner_id.email) when '
             'a POS order is paid/done/invoiced.',
    )
    pos_owner_emails = fields.Char(
        string='Owner Emails (comma-separated)',
        help='One or more email addresses (comma-separated) that receive POS '
             'order summaries.',
    )

    # ──────────────────────────────────────────────────────────────────────
    # EMAIL HELPERS
    # ──────────────────────────────────────────────────────────────────────
    def _get_from_email(self):
        """The address this database actually sends from.

        The gateway decides the sender, so ask it first - reporting a
        different address in the UI than the one recipients see is worse than
        reporting nothing. mail_from() is cached in ir.config_parameter, so
        this costs no network call.
        """
        self.ensure_one()
        gateway_from = self.env['whatsapp.session'].sudo().mail_from()
        if gateway_from:
            return gateway_from
        sess = self.default_email_session_id
        if sess:
            return sess.get_from_email()
        return self.env.company.email or 'noreply@example.com'
