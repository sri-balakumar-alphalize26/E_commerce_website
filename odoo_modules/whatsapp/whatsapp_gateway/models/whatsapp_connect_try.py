"""Tries to connect a number that failed (25 Nov 2026). Never a key."""
import re
from datetime import timedelta

from odoo import api, fields, models

KEEP_DAYS = 90
SAME_MINUTES = 10


class WhatsAppConnectTry(models.Model):
    _name = 'whatsapp.connect.try'
    _description = 'Failed WhatsApp connection'
    _order = 'id desc'
    _rec_name = 'number'

    number = fields.Char('Number', readonly=True)
    step = fields.Selection([('open', 'Opening'), ('number', 'Number'), ('scan', 'Scan')], 'Step', readonly=True)
    error = fields.Text('Error', readonly=True)

    @api.model
    def _keep(self, step, number, error):
        error = re.sub(r'wa1_\S+', '***', (error or '').strip())[:500]
        number = ''.join(c for c in str(number or '') if c.isdigit())
        # the screen asks every few seconds: once is enough
        since = fields.Datetime.now() - timedelta(minutes=SAME_MINUTES)
        if not self.search_count([('step', '=', step), ('number', '=', number or False), ('error', '=', error),
                                  ('create_date', '>=', since)], limit=1):
            self.create({'step': step, 'number': number or False, 'error': error})

    @api.autovacuum
    def _gc_tries(self):
        self.search([('create_date', '<', fields.Datetime.now() - timedelta(days=KEEP_DAYS))]).unlink()
