import logging
import mimetypes

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class WhatsappCampaign(models.Model):
    """A bulk WhatsApp send (offers / festival wishes) to loyalty customers.

    Authoring only: the actual fan-out is one row per recipient in
    whatsapp.send.queue, drained by the throttled queue cron (~20/min) so 1,000+
    recipients send safely without banning the number or timing out a request.
    """
    _name = 'whatsapp.campaign'
    _description = 'WhatsApp Broadcast Campaign'
    _order = 'create_date desc'

    name = fields.Char(required=True, default=lambda s: _('Offer / Wishes'))
    message = fields.Text(
        required=True,
        help="Use {name} to personalise with each customer's name. Use *stars* for bold.")
    attachment = fields.Binary(string='Image / PDF (optional)', attachment=True)
    attachment_name = fields.Char(string='Attachment Filename')
    attachment_mimetype = fields.Char(compute='_compute_mimetype', store=True)

    recipient_mode = fields.Selection([
        ('all_active', 'All active loyalty customers'),
        ('selected', 'Selected customers only'),
    ], default='all_active', required=True)
    card_ids = fields.Many2many('pos.loyalty.card', string='Customers',
                                domain=[('is_deleted', '=', False), ('state', '=', 'active')])

    state = fields.Selection([
        ('draft', 'Draft'),
        ('queued', 'Queued / Sending'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled'),
    ], default='draft', required=True, index=True)

    queue_ids = fields.One2many('whatsapp.send.queue', 'campaign_id')
    total_count = fields.Integer(compute='_compute_counts')
    sent_count = fields.Integer(compute='_compute_counts')
    failed_count = fields.Integer(compute='_compute_counts')
    pending_count = fields.Integer(compute='_compute_counts')
    company_id = fields.Many2one('res.company', default=lambda s: s.env.company)

    @api.depends('attachment_name')
    def _compute_mimetype(self):
        for rec in self:
            mt = False
            if rec.attachment_name:
                mt = mimetypes.guess_type(rec.attachment_name)[0]
            rec.attachment_mimetype = mt or ('application/pdf' if rec.attachment else False)

    @api.depends('queue_ids.state')
    def _compute_counts(self):
        for rec in self:
            rows = rec.queue_ids
            rec.total_count = len(rows)
            rec.sent_count = len(rows.filtered(lambda r: r.state == 'sent'))
            rec.failed_count = len(rows.filtered(lambda r: r.state == 'failed'))
            rec.pending_count = len(rows.filtered(lambda r: r.state == 'pending'))

    # ------------------------------------------------------------------
    def _recipient_cards(self):
        self.ensure_one()
        if self.recipient_mode == 'selected':
            cards = self.card_ids
        else:
            cards = self.env['pos.loyalty.card'].sudo().search([
                ('state', '=', 'active'),
                ('is_deleted', '=', False),
                ('phone', '!=', False),
            ])
        # de-dup by normalised phone, keep only those with a phone
        seen, out = set(), self.env['pos.loyalty.card']
        for c in cards:
            digits = ''.join(filter(str.isdigit, c.phone or ''))
            if digits and digits not in seen:
                seen.add(digits)
                out |= c
        return out

    def render_message(self, name):
        """Render the campaign body for one recipient ({name} placeholder)."""
        self.ensure_one()
        body = self.message or ''
        try:
            body = body.replace('{name}', name or '')
        except Exception:
            pass
        return body

    def action_queue(self):
        self.ensure_one()
        if self.state == 'queued':
            raise UserError(_('This campaign is already queued.'))
        cards = self._recipient_cards()
        if not cards:
            raise UserError(_('No recipients found. Add customers or pick "All active".'))
        Queue = self.env['whatsapp.send.queue'].sudo()
        for card in cards:
            Queue._enqueue('broadcast', card, delay_seconds=0, campaign=self,
                           phone=card.phone, partner_name=card.name)
        self.state = 'queued'
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {
                'title': _('Broadcast queued'),
                'message': _('%d recipients queued. Messages send in the background (~20/min).') % len(cards),
                'type': 'success', 'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }

    def action_cancel(self):
        for rec in self:
            rec.queue_ids.filtered(lambda r: r.state == 'pending').write({'state': 'cancelled'})
            rec.state = 'cancelled'
        return True

    def _refresh_state(self):
        for rec in self:
            if rec.state == 'queued' and not rec.queue_ids.filtered(lambda r: r.state == 'pending'):
                rec.state = 'done'
