"""An employee session that says in words what is wrong (23 Nov 2026).

Before the database does with the name of an index: who has the number, or the
employee, already; that the WhatsApp session is off. Only for what a person
saves: the handover and "Connect a number" (wa_switch) check by themselves."""
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .phone_digits import digits


class EmployeeSessionEasy(models.Model):
    _inherit = 'wa.employee.session'

    session_active = fields.Boolean(related='session_id.active', string='Session on')
    link_text = fields.Char(compute='_compute_link_text', compute_sudo=True)

    @api.depends('session_id', 'session_id.active', 'session_id.status', 'active')
    def _compute_link_text(self):
        for rec in self:
            session = rec.session_id
            if not rec.active or not session:
                rec.link_text = ''
            elif not session.active:
                rec.link_text = _("The WhatsApp session \"%s\" is off: nothing is sent or answered for this employee. Turn it "
                                  "on in WhatsApp Numbers, or give the employee another number.", session.name)
            elif session.status == 'wrong_number':
                rec.link_text = _("Another phone was scanned for \"%s\". Scan again with the right one.", session.name)
            elif session.status != 'connected':
                rec.link_text = _("\"%s\" is not connected now. Press Scan again in WhatsApp Numbers.", session.name)
            else:
                rec.link_text = ''

    # ------------------------------------------------------------ one and one
    def _refuse_taken(self, employee_id, session_id):
        if self.env.context.get('wa_switch'):
            return
        Session = self.env['wa.employee.session'].sudo()
        pretty = self.env['whatsapp.connect']._pretty
        for field, value in (('employee_id', employee_id), ('session_id', session_id)):
            other = Session.search([(field, '=', value), ('id', 'not in', self.ids)], limit=1) if value else Session
            if not other:
                continue
            number = pretty(other.session_id.authorized_number) or other.phone_number or ''
            if field == 'employee_id':
                raise ValidationError(_(
                    "%(who)s already has the number %(number)s (%(session)s). One employee has one number: open that entry "
                    "instead of making another.", who=other.employee_id.name, number=number, session=other.session_id.name))
            raise ValidationError(_(
                "\"%(session)s\" (%(number)s) already belongs to %(who)s. To give it to somebody else, open %(who)s and "
                "press Other employee.", session=other.session_id.name, number=number, who=other.employee_id.name))
        session = self.env['whatsapp.session'].sudo().browse(session_id).exists() if session_id else False
        if session and not session.active:
            raise ValidationError(_(
                "The WhatsApp session \"%s\" is off. Turn it on in WhatsApp Numbers first, or choose another one.", session.name))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('active', True):
                self.browse()._refuse_taken(vals.get('employee_id'), vals.get('session_id'))
        return super().create(vals_list)

    def write(self, vals):
        if {'employee_id', 'session_id', 'active'} & set(vals):
            for rec in self:
                if not vals.get('active', rec.active):
                    continue
                on_again = 'active' in vals and not rec.active
                if not on_again and rec._has_chats():
                    continue                # refused for its chats, which is the reason to tell
                employee, session = vals.get('employee_id', rec.employee_id.id), vals.get('session_id', rec.session_id.id)
                rec._refuse_taken(employee if on_again or employee != rec.employee_id.id else False,
                                  session if on_again or session != rec.session_id.id else False)
        return super().write(vals)

    def web_save(self, vals, specification, next_id=None):
        result = super().web_save(vals, specification, next_id=next_id)
        if 'phone_number' in vals or 'session_id' in vals:
            for rec in self or self.browse(result[0]['id']):
                # the session's own number is compared by _check_phone_is_the_sessions
                number = digits(rec.phone_number)
                if not digits(rec.sudo().session_id.authorized_number) and not self.env['whatsapp.connect']._split('+' + number):
                    raise UserError(_(
                        "\"%s\" is not a whole phone number. Type it with the country code, for example +971 50 123 4567.",
                        rec.phone_number or ''))
        return result


class WhatsAppSessionEmployee(models.Model):
    _inherit = 'whatsapp.session'

    def _setup_steps(self):
        steps = super()._setup_steps()
        link = self.env['wa.employee.session'].sudo().search([('session_id', '=', self.id), ('active', '=', True)], limit=1) \
            if isinstance(self.id, int) else False
        steps.append(('employee', bool(link), link.employee_id.name if link else _("Employee"),
                      _("Choose the employee who answers on this number.")))
        return steps
