"""Connect a number: whose number it is (23 Nov 2026)."""
from odoo import _, api, models
from odoo.exceptions import UserError


class WhatsAppConnectEmployee(models.AbstractModel):
    _inherit = 'whatsapp.connect'

    @api.model
    def start(self, session_id=None):
        data = super().start(session_id)
        taken = {}
        for es in self.env['wa.employee.session'].sudo().search([]):
            taken[es.employee_id.id] = self._pretty(es.session_id.authorized_number) or es.phone_number or ''
        data['employees'] = [{'id': e.id, 'name': e.name, 'taken': taken.get(e.id, '')}
                             for e in self.env['hr.employee'].sudo().search(
                                 [('company_id', 'in', [False] + self.env.companies.ids)], order='name')]
        return data

    @api.model
    def _without_owner(self):
        return self.env['whatsapp.session'].sudo().search([
            ('active', '=', True), ('id', 'not in', self._given_sessions().ids)])

    @api.model
    def _given_sessions(self):
        return self.env['wa.employee.session'].sudo().search([]).session_id

    @api.model
    def _before(self, vals, number):
        super()._before(vals, number)
        Employee = self.env['hr.employee'].sudo()
        name = (vals.get('employee_name') or '').strip()[:80]
        employee = Employee.browse(int(vals.get('employee_id') or 0)).exists()
        if not employee and not name:
            raise UserError(_("Choose the employee."))
        if employee:
            has = self.env['wa.employee.session'].sudo().search([('employee_id', '=', employee.id)], limit=1)
            if has:
                raise UserError(_("%(who)s has a number already: %(number)s.", who=employee.name,
                                  number=self._pretty(has.session_id.authorized_number) or has.phone_number))
        vals['employee'] = employee

    @api.model
    def _label(self, vals, number):
        who = vals['employee'].name if vals.get('employee') else (vals.get('employee_name') or '').strip()
        return who or super()._label(vals, number)

    @api.model
    def _after(self, vals, session, number):
        super()._after(vals, session, number)
        employee = vals.get('employee')
        if not employee:
            employee = self.env['hr.employee'].sudo().create(
                {'name': vals['employee_name'].strip()[:80], 'company_id': vals['company'].id})
        # each number its own chats: only the one of this very number goes on
        Link = self.env['wa.employee.session'].sudo().with_context(active_test=False, wa_switch=True)
        old = Link._before_on(employee, number)
        values = {'session_id': session.id, 'phone_number': '+' + number if number else session.name,
                  'auto_reply_company_id': vals['company'].id, 'active': True}
        if old:
            old.with_context(wa_switch=True).write(values)      # the same employee on it again
        else:
            Link.create(dict(values, employee_id=employee.id))

    @api.model
    def _state_extra(self, session):
        link = self.env['wa.employee.session'].sudo().search([('session_id', '=', session.id)], limit=1)
        return dict(super()._state_extra(session), employee=link.employee_id.name or '')
