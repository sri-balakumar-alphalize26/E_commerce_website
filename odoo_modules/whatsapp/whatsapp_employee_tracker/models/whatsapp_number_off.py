"""A removed number's employee is free for another one (23 Nov 2026)."""
from odoo import models


class WhatsAppSessionOffEmployee(models.Model):
    _inherit = 'whatsapp.session'

    def _number_off(self, removed=False):
        super()._number_off(removed=removed)
        if removed:
            self.env['wa.employee.session'].sudo().search([('session_id', 'in', self.ids)]).write({'active': False})

    def _has_history(self):
        return super()._has_history() or bool(self.env['wa.employee.session'].sudo().with_context(
            active_test=False).search_count([('session_id', '=', self.id)], limit=1))
