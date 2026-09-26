from odoo import models, fields, api
from datetime import timedelta
import logging

_logger = logging.getLogger(__name__)


class PosLoyaltyCardImage(models.Model):
    _name = 'pos.loyalty.card.image'
    _description = 'Loyalty Card Image Snapshot'
    _order = 'create_date desc'
    _rec_name = 'card_number'

    card_id = fields.Many2one(
        'pos.loyalty.card', string='Loyalty Card',
        required=True, ondelete='cascade', index=True)
    card_number = fields.Char(related='card_id.card_number', store=True, string='Card Number')
    customer_name = fields.Char(related='card_id.name', store=True, string='Customer')
    phone = fields.Char(related='card_id.phone', store=True, string='Phone')
    image = fields.Image(string='Card Image')
    points = fields.Float(string='Points', digits=(16, 2))
    event_type = fields.Selection([
        ('creation', 'Card Created'),
        ('order', 'Order'),
    ], string='Event', default='order')
    snapshot_day = fields.Date(string='Date', compute='_compute_snapshot_day', store=True)

    @api.depends('create_date')
    def _compute_snapshot_day(self):
        for rec in self:
            rec.snapshot_day = rec.create_date.date() if rec.create_date else False

    @api.model
    def _cron_delete_old_images(self):
        """Delete saved card-image snapshots older than the configured retention."""
        settings = self.env['pos.loyalty.card.settings'].get_settings()
        months = settings.card_image_retention_months if settings else 6
        if not months or months <= 0:
            return
        cutoff = fields.Datetime.now() - timedelta(days=30 * months)
        old = self.search([('create_date', '<', cutoff)])
        if old:
            _logger.info('LOYALTY: deleting %s card images older than %s months', len(old), months)
            old.unlink()
