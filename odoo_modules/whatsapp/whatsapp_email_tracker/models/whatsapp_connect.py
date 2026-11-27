"""A number for the company itself: no employee (26 Nov 2026).

Opened from WhatsApp and Email settings ("Connect a new number for this
company"), the connect screen sends for_company=True. WA Tracker would insist
on an employee and link one; such a number belongs to the company, so WA
Tracker's own steps are skipped for it. Opened from WA Tracker, nothing changes.
"""
from odoo import api, models


class WhatsAppConnectCompany(models.AbstractModel):
    _inherit = 'whatsapp.connect'

    @api.model
    def _before(self, vals, number):
        if vals.get('for_company'):
            vals['employee'] = False
            return                      # no employee asked for, none refused
        return super()._before(vals, number)

    @api.model
    def _after(self, vals, session, number):
        if vals.get('for_company'):
            return                      # no employee link for a company number
        return super()._after(vals, session, number)

    @api.model
    def _label(self, vals, number):
        if vals.get('for_company') and vals.get('company'):
            return '%s %s' % (vals['company'].name, self._pretty(number))
        return super()._label(vals, number)
