import logging
from odoo import models, fields, api
from odoo.tools import html2plaintext

_logger = logging.getLogger(__name__)


class WhatsAppMessage(models.Model):
    _name = 'whatsapp.message'
    _description = 'WhatsApp Message'
    _order = 'create_date desc'
    _rec_name = 'phone'

    session_id = fields.Many2one(
        'whatsapp.session', string='Session',
        required=True, ondelete='cascade', index=True,
    )
    # which of OUR numbers it was on; a session can become another number
    own_number = fields.Char('Our Number', index=True, readonly=True, copy=False)
    channel = fields.Selection([
        ('whatsapp', 'WhatsApp'),
        ('email', 'Email'),
    ], string='Channel', default='whatsapp', required=True, index=True)
    phone = fields.Char('To', required=True, index=True,
                        help="Phone number for WhatsApp, email address for email.")
    message = fields.Text('Message')
    message_preview = fields.Char(
        'Preview', compute='_compute_message_preview',
        help="First line of the message, for the list view.",
    )
    direction = fields.Selection([
        ('incoming', 'Incoming'),
        ('outgoing', 'Outgoing'),
    ], string='Direction', required=True, index=True)
    status = fields.Selection([
        ('pending', 'Pending'),
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('read', 'Read'),
        ('received', 'Received'),
        ('failed', 'Failed'),
        # Never sent, on purpose: opted out, over the daily cap, or a
        # duplicate. Recorded so the reason is auditable afterwards.
        ('blocked', 'Blocked'),
    ], string='Status', default='pending', index=True)
    wa_message_id = fields.Char('WA Message ID', index=True)
    partner_id = fields.Many2one(
        'res.partner', string='Contact',
        compute='_compute_partner', store=True, index=True,
    )
    attachment_ids = fields.Many2many(
        'ir.attachment', string='Attachments',
    )
    # What a retry needs in order to send the document again.
    #
    # Without these a pending document can only be retried as text, because
    # `message` holds the log line and not the file - which is how
    # attachment-shaped text reached customers while the row read 'sent'. The
    # report is re-rendered at retry time rather than storing the bytes: a
    # message row is no place to keep megabytes, and a re-render cannot go stale.
    retry_count = fields.Integer(
        'Send Attempts', default=0, copy=False, readonly=True,
        help="How many times the outbox has tried to send this. Four test "
             "messages once sat pending for four days; every attempt tripped "
             "the gateway's rate limit and held live sends for a minute.")
    retry_report_xmlid = fields.Char('Retry: Report', copy=False)
    retry_res_model = fields.Char('Retry: Model', copy=False)
    retry_res_id = fields.Integer('Retry: Record', copy=False)
    retry_filename = fields.Char('Retry: File Name', copy=False)
    retry_caption = fields.Text('Retry: Caption', copy=False)
    company_id = fields.Many2one(
        related='session_id.company_id', store=True,
    )
    is_group = fields.Boolean(
        'Group Message', compute='_compute_is_group', store=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        numbers = {}
        for vals in vals_list:
            if 'own_number' in vals or vals.get('channel', 'whatsapp') != 'whatsapp' or not vals.get('session_id'):
                continue
            number = self.env.context.get('wa_own_number') if vals.get('direction') == 'incoming' else ''
            if not number:
                sid = vals['session_id']
                if sid not in numbers:
                    session = self.env['whatsapp.session'].sudo().browse(sid)
                    numbers[sid] = ''.join(c for c in (session.authorized_number or '') if c.isdigit())
                number = numbers[sid]
            vals['own_number'] = number or False
        return super().create(vals_list)

    # ----------------------------------------------------------
    # Computed Fields
    # ----------------------------------------------------------
    @api.depends('message')
    def _compute_message_preview(self):
        """One readable line, whatever the channel put in the body.

        Email arrives as HTML, so the tags are stripped rather than shown; the
        alternative was a list where one invoice mail is taller than the screen.
        Not stored: it is display only, and storing it would double the body of
        every message row for no gain.
        """
        for rec in self:
            body = rec.message or ''
            if '<' in body and '>' in body:
                body = html2plaintext(body)
            line = ' '.join(body.split())
            rec.message_preview = (line[:120] + '...') if len(line) > 120 else line

    @api.depends('phone')
    def _compute_partner(self):
        """Auto-match phone number to res.partner."""
        for rec in self:
            if rec.phone:
                phone_suffix = (
                    rec.phone[-10:]
                    if len(rec.phone) >= 10
                    else rec.phone
                )
                partner = self.env['res.partner'].search([
                    ('phone', 'like', f'%{phone_suffix}'),
                ], limit=1)
                rec.partner_id = partner.id if partner else False
            else:
                rec.partner_id = False

    @api.depends('phone')
    def _compute_is_group(self):
        for rec in self:
            rec.is_group = '@g.us' in (rec.phone or '')

    # ----------------------------------------------------------
    # Actions
    # ----------------------------------------------------------
    def action_reply(self):
        """Open send message wizard pre-filled with this phone."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Reply via WhatsApp',
            'res_model': 'whatsapp.send.message.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_session_id': self.session_id.id,
                'default_phone': self.phone,
            },
        }

    def action_open_partner(self):
        """Open the linked partner."""
        self.ensure_one()
        if self.partner_id:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'res.partner',
                'res_id': self.partner_id.id,
                'view_mode': 'form',
            }
