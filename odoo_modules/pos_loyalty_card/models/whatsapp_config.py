import logging
from odoo import models, fields, api

_logger = logging.getLogger(__name__)


def _render_status_html(rows):
    """Build a simple, friendly green/red status card from (ok, label, detail) rows."""
    core_ok = all(r[0] for r in rows[:3])  # engine + service + linked
    banner_bg = '#28a745' if core_ok else '#f0ad4e'
    banner_txt = ('✅ WhatsApp is ready to send'
                  if core_ok else '⚙️ Setting up — this finishes on its own')
    parts = ['<div style="border:1px solid #e6e6e6;border-radius:10px;'
             'max-width:560px;overflow:hidden;font-family:Arial,sans-serif;">']
    parts.append('<div style="padding:10px 14px;color:#fff;font-weight:700;'
                 'background:%s;">%s</div>' % (banner_bg, banner_txt))
    for ok, label, detail in rows:
        icon = '✅' if ok else '❌'
        dcolor = '#2e7d32' if ok else '#c62828'
        parts.append(
            '<div style="display:flex;align-items:center;gap:12px;padding:10px 14px;'
            'border-top:1px solid #f0f0f0;">'
            '<span style="font-size:18px;line-height:1;">%s</span>'
            '<div><div style="font-weight:600;color:#222;">%s</div>'
            '<div style="font-size:12px;color:%s;">%s</div></div></div>'
            % (icon, label, dcolor, detail))
    parts.append('</div>')
    return ''.join(parts)


class WhatsAppOwnerNumber(models.Model):
    _name = 'whatsapp.owner.number'
    _description = 'WhatsApp Owner Notification Number'
    _order = 'sequence, id'

    sequence = fields.Integer(default=10)
    name = fields.Char('Label', required=True, help='e.g. Owner, Manager, Accountant')
    phone = fields.Char(
        'Phone Number', required=True,
        help='Phone number with country code, no + sign. e.g. 919944080209',
    )
    active = fields.Boolean(default=True)
    config_id = fields.Many2one(
        'whatsapp.config', string='Configuration',
        ondelete='cascade',
    )
    company_id = fields.Many2one(
        'res.company', string='Company',
        default=lambda self: self.env.company,
    )


class WhatsAppConfig(models.Model):
    _name = 'whatsapp.config'
    _description = 'WhatsApp Configuration'
    _rec_name = 'company_id'

    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company,
        ondelete='cascade',
    )

    # --- POS Settings ---
    pos_notify_enabled = fields.Boolean(
        'Enable POS WhatsApp Notifications', default=False,
    )
    pos_notify_owners = fields.Boolean(
        'Send POS Orders to Owners', default=True,
        help='Send order summary to owner numbers when POS order is completed.',
    )
    pos_notify_customer = fields.Boolean(
        'Send POS Receipt to Customer', default=False,
        help='Send order summary to the customer selected in POS order.',
    )
    pos_session_id = fields.Many2one(
        'whatsapp.session', string='WhatsApp Session for POS',
        help='Which WhatsApp session to use for POS notifications. '
             'Leave empty to use the first connected session.',
    )
    pos_message_template = fields.Text(
        'POS Message Template',
        default="""🧾 *POS Order: {order_name}*
📅 Date: {date}
🏪 POS: {pos_name}

{order_lines}

💰 *Subtotal:* {amount_untaxed}
📊 *Tax:* {amount_tax}
✅ *Total:* {amount_total}
💳 *Paid:* {amount_paid}

{customer_info}

Thank you for your purchase! 🙏""",
        help='Template for POS order messages. Available placeholders: '
             '{order_name}, {date}, {pos_name}, {order_lines}, '
             '{amount_untaxed}, {amount_tax}, {amount_total}, '
             '{amount_paid}, {customer_name}, {customer_info}',
    )

    # --- Simple (fill-in-the-blanks) message builder ---
    pos_message_mode = fields.Selection([
        ('simple', 'Simple (fill-in-the-blanks)'),
        ('advanced', 'Advanced template'),
    ], string='Message Style', default='simple',
        help='Simple: just tick what to include, no codes. '
             'Advanced: edit the raw template with {placeholders}.')
    pos_msg_header = fields.Char(
        'Header', default='🧾 New POS Order',
        help='First line of the message. The order number is added automatically '
             'if "Show Order Number" is on.')
    pos_msg_footer = fields.Text(
        'Footer', default='Thank you for your purchase! 🙏')
    pos_show_order_number = fields.Boolean('Show Order Number', default=True)
    pos_show_date = fields.Boolean('Show Date', default=True)
    pos_show_pos_name = fields.Boolean('Show POS Name', default=True)
    pos_show_items = fields.Boolean('Show Items', default=True)
    pos_show_subtotal = fields.Boolean('Show Subtotal', default=True)
    pos_show_tax = fields.Boolean('Show Tax', default=True)
    pos_show_total = fields.Boolean('Show Total', default=True)
    pos_show_paid = fields.Boolean('Show Amount Paid', default=False)
    pos_show_customer = fields.Boolean('Show Customer', default=True)
    pos_message_preview = fields.Text(
        'Live Preview', compute='_compute_pos_message_preview', readonly=True)

    owner_number_ids = fields.One2many(
        'whatsapp.owner.number', 'config_id', string='Owner Numbers',
    )

    # --- Setup status (friendly health panel shown on the settings page) ---
    setup_status_html = fields.Html(
        'Setup Status', compute='_compute_setup_status',
        sanitize=False, readonly=True)

    def _compute_setup_status(self):
        from . import baileys_provision
        # Node.js engine
        try:
            node_ok = bool(baileys_provision._find_node())
        except Exception:
            node_ok = False
        # Baileys helper service on 127.0.0.1:8788
        try:
            service_ok = baileys_provision._status_ok()
        except Exception:
            service_ok = False
        # WhatsApp linked?
        sess = self.env['whatsapp.session'].sudo().search(
            [('status', '=', 'connected')], limit=1)
        wa_ok = bool(sess)
        wa_phone = sess.phone_number if sess else ''
        # Card image + PDF (Pillow)
        try:
            import PIL  # noqa: F401
            img_ok = True
        except Exception:
            img_ok = False
        # Email (optional)
        try:
            email_ok = bool(self.env['pos.loyalty.card.settings'].sudo()
                            .get_settings().mail_configured)
        except Exception:
            email_ok = False

        rows = [
            (node_ok, 'WhatsApp engine (Node.js)',
             'Installed' if node_ok else 'Installing automatically…'),
            (service_ok, 'WhatsApp service',
             'Running' if service_ok else 'Starting automatically…'),
            (wa_ok, 'WhatsApp account linked',
             ('Connected: %s' % wa_phone) if wa_ok
             else 'Not linked yet — go to Sessions and scan the QR'),
            (img_ok, 'Card image &amp; PDF',
             'Ready' if img_ok else 'Image library missing'),
            (email_ok, 'Email sending',
             'Configured' if email_ok else 'Optional — set up in Email Settings'),
        ]
        html = _render_status_html(rows)
        for rec in self:
            rec.setup_status_html = html

    @api.model
    def get_config(self, company_id=None):
        """Get or create config for current company."""
        company_id = company_id or self.env.company.id
        config = self.search([('company_id', '=', company_id)], limit=1)
        if not config:
            config = self.create({'company_id': company_id})
        return config

    def format_pos_message(self, order):
        """Format a POS order into a WhatsApp message."""
        self.ensure_one()

        # Build order lines
        lines = []
        for line in order.lines:
            qty_str = f"{line.qty:g}"
            line_total = line.price_subtotal_incl
            line_text = f"  • {line.full_product_name or line.product_id.name}"
            line_text += f"  ×{qty_str}"
            if line.discount:
                line_text += f"  (-{line.discount:g}%)"
            line_text += f"  = {line_total:,.2f}"
            lines.append(line_text)
        order_lines = "\n".join(lines) if lines else "  (no items)"

        # Customer
        customer_name = order.partner_id.name if order.partner_id else 'Walk-in Customer'
        customer_phone = order.partner_id.phone if order.partner_id else ''
        customer_info = ""
        if order.partner_id:
            customer_info = f"👤 Customer: {order.partner_id.name}"
            if order.partner_id.phone:
                customer_info += f"\n📱 Phone: {order.partner_id.phone}"

        # POS name
        pos_name = 'N/A'
        if order.session_id and order.session_id.config_id:
            pos_name = order.session_id.config_id.name

        amount_untaxed = order.amount_total - order.amount_tax
        date_str = order.date_order.strftime('%d/%m/%Y %I:%M %p') if order.date_order else ''

        ctx = {
            'order_name': order.name or '',
            'date': date_str,
            'pos_name': pos_name,
            'order_lines': order_lines,
            'amount_untaxed': f"{amount_untaxed:,.2f}",
            'amount_tax': f"{order.amount_tax:,.2f}",
            'amount_total': f"{order.amount_total:,.2f}",
            'amount_paid': f"{order.amount_paid:,.2f}",
            'customer_name': customer_name,
            'customer_phone': customer_phone,
            'customer_info': customer_info,
        }

        if self.pos_message_mode == 'advanced':
            template = self.pos_message_template or self._fields['pos_message_template'].default
            return template.format(**ctx)
        return self._render_simple(ctx)

    def _render_simple(self, ctx):
        """Assemble the POS message from the fill-in-the-blanks settings."""
        self.ensure_one()
        parts = []

        header = (self.pos_msg_header or '').strip()
        if self.pos_show_order_number and ctx.get('order_name'):
            header = f"{header} {ctx['order_name']}".strip() if header else ctx['order_name']
        if header:
            parts.append(f"*{header}*")

        meta = []
        if self.pos_show_date and ctx.get('date'):
            meta.append(f"📅 {ctx['date']}")
        if self.pos_show_pos_name and ctx.get('pos_name'):
            meta.append(f"🏪 {ctx['pos_name']}")
        if meta:
            parts.append("\n".join(meta))

        if self.pos_show_items and ctx.get('order_lines'):
            parts.append(ctx['order_lines'])

        money = []
        if self.pos_show_subtotal:
            money.append(f"💰 Subtotal: {ctx.get('amount_untaxed', '')}")
        if self.pos_show_tax:
            money.append(f"📊 Tax: {ctx.get('amount_tax', '')}")
        if self.pos_show_total:
            money.append(f"✅ *Total: {ctx.get('amount_total', '')}*")
        if self.pos_show_paid:
            money.append(f"💳 Paid: {ctx.get('amount_paid', '')}")
        if money:
            parts.append("\n".join(money))

        if self.pos_show_customer and ctx.get('customer_name'):
            cust = f"👤 {ctx['customer_name']}"
            if ctx.get('customer_phone'):
                cust += f"\n📱 {ctx['customer_phone']}"
            parts.append(cust)

        footer = (self.pos_msg_footer or '').strip()
        if footer:
            parts.append(footer)

        return "\n\n".join(p for p in parts if p)

    @api.model
    def _sample_ctx(self):
        """Sample data used for the live preview in the settings form."""
        return {
            'order_name': 'Order 00042',
            'date': '08/07/2026 10:48 AM',
            'pos_name': 'Main Counter',
            'order_lines': "  • Milk  ×2  = 90.00\n  • Bread  ×1  = 25.00",
            'amount_untaxed': '110.00',
            'amount_tax': '5.00',
            'amount_total': '115.00',
            'amount_paid': '115.00',
            'customer_name': 'Ramesh',
            'customer_phone': '919944080209',
            'customer_info': "👤 Customer: Ramesh\n📱 Phone: 919944080209",
        }

    @api.depends('pos_message_mode', 'pos_msg_header', 'pos_msg_footer',
                 'pos_show_order_number', 'pos_show_date', 'pos_show_pos_name',
                 'pos_show_items', 'pos_show_subtotal', 'pos_show_tax',
                 'pos_show_total', 'pos_show_paid', 'pos_show_customer',
                 'pos_message_template')
    def _compute_pos_message_preview(self):
        for rec in self:
            ctx = rec._sample_ctx()
            if rec.pos_message_mode == 'advanced':
                try:
                    tmpl = rec.pos_message_template or rec._fields['pos_message_template'].default
                    rec.pos_message_preview = tmpl.format(**ctx)
                except Exception as e:
                    rec.pos_message_preview = f"⚠ Template error: {e}"
            else:
                rec.pos_message_preview = rec._render_simple(ctx)
