"""Whose number it is, in the list of numbers (23 Nov 2026)."""
from odoo import _, api, fields, models


class WhatsAppSessionOwner(models.Model):
    _inherit = 'whatsapp.session'

    wa_employee_id = fields.Many2one('hr.employee', 'Employee', compute='_compute_wa_employee', compute_sudo=True)

    def _compute_wa_employee(self):
        links = self.env['wa.employee.session'].sudo().search([('session_id', 'in', self.ids)])
        by = {link.session_id.id: link.employee_id for link in links}
        for rec in self:
            rec.wa_employee_id = by.get(rec.id, False)

    @api.depends('name', 'authorized_number', 'status')
    @api.depends_context('wa_number_in_name')
    def _compute_display_name(self):
        super()._compute_display_name()
        if self.env.context.get('wa_number_in_name'):
            for rec in self:
                number = self.env['whatsapp.connect']._pretty(rec.authorized_number)
                state = dict(self._fields['status']._description_selection(self.env)).get(rec.status, '')
                rec.display_name = ', '.join(x for x in (rec.name, number, state) if x)

    def action_give_number(self):
        self.ensure_one()
        return {'type': 'ir.actions.client', 'tag': 'whatsapp_gateway.connect', 'name': _("Give to an employee"),
                'params': {'give_session_id': self.id}}
