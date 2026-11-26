from odoo import models

MANUAL_URL = '/whatsapp_employee_tracker/static/help/manual.pdf'


class WaTrackerHelp(models.TransientModel):
    """26 Nov 2026: Help opens a small window; manual.pdf opens the user manual."""
    _name = 'wa.tracker.help'
    _description = 'WA Tracker Help'

    def action_open_manual(self):
        return {'type': 'ir.actions.act_url', 'url': MANUAL_URL, 'target': 'new'}
