import logging
from odoo import models, fields, api

_logger = logging.getLogger(__name__)


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

    owner_number_ids = fields.One2many(
        'whatsapp.owner.number', 'config_id', string='Owner Numbers',
    )

    @api.model
    def get_config(self, company_id=None):
        """Get or create config for current company."""
        company_id = company_id or self.env.company.id
        config = self.search([('company_id', '=', company_id)], limit=1)
        if not config:
            config = self.create({'company_id': company_id})
        return config
