"""Whose number it is, in the list of numbers (23 Nov 2026)."""
from odoo import _, api, fields, models


class WhatsAppSessionOwner(models.Model):
    _inherit = 'whatsapp.session'

    wa_employee_id = fields.Many2one('hr.employee', 'Employee', compute='_compute_wa_employee', compute_sudo=True)

    def _compute_wa_employee(self):
        links = self.env['wa.employee.session'].sudo().search([('session_id', 'in', self.ids), ('active', '=', True)])
        by = {link.session_id.id: link.employee_id for link in links}
        for rec in self:
            rec.wa_employee_id = by.get(rec.id, False)

    wa_chats = fields.Integer('Chats', compute='_compute_wa_figures')
    wa_today_sent = fields.Integer('Sent today', compute='_compute_wa_figures')
    wa_today_received = fields.Integer('Received today', compute='_compute_wa_figures')
    wa_last_activity = fields.Datetime('Last activity', compute='_compute_wa_figures')

    def _wa_link(self):
        self.ensure_one()
        return self.env['wa.employee.session'].sudo().search([('session_id', '=', self.id), ('active', '=', True)], limit=1) \
            if isinstance(self.id, int) else self.env['wa.employee.session'].sudo()

    @api.depends_context('tz', 'uid')
    def _compute_wa_figures(self):
        """The figures of its card on the dashboard."""
        for rec in self:
            link = rec._wa_link()
            rec.wa_chats = link._totals()[link.id]['unique_contacts'] if link else 0
            rec.wa_today_sent = link.today_sent
            rec.wa_today_received = link.today_received
            rec.wa_last_activity = link.last_activity

    def action_wa_chats(self):
        self.ensure_one()
        link = self._wa_link()
        return link.sudo(False).action_open_chats() if link else False

    def _other_numbers(self):
        link = self._wa_link()
        card = [(_("Employee %s", link.employee_id.name), link.own_number or '')] if link else []
        return super()._other_numbers() + card

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
