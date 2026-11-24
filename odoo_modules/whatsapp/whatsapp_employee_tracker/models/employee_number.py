"""One employee on one number (23 Nov 2026).

A chat belongs to the employee session it was held on. When the number, the
session or the employee changes, the present employee session is archived with
its chats and another one goes on: the one this employee had on that number
before, or a new one. So the chats of two numbers, or of two people, are never
one chat - and nothing of an old one is lost.
"""
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .phone_digits import digits, same_number

_logger = logging.getLogger(__name__)


class EmployeeNumber(models.Model):
    _inherit = 'wa.employee.session'

    @api.depends('phone_number')
    def _compute_own_number(self):
        for rec in self:
            rec.own_number = digits(rec.phone_number) or False

    def _compute_has_chats(self):
        for rec in self:
            rec.has_chats = rec._has_chats()

    @api.depends('employee_id', 'phone_number')
    def _compute_display_name(self):
        for rec in self:
            number = self.env['whatsapp.connect']._pretty(rec.own_number) if rec.own_number else ''
            rec.display_name = ', '.join(x for x in (rec.employee_id.name, number) if x)

    def _has_chats(self):
        self.ensure_one()
        if not self.id or not isinstance(self.id, int):
            return False
        return bool(self.env['wa.communication.log'].sudo().search_count([('employee_session_id', '=', self.id)], limit=1)
                    or self.env['whatsapp.message'].sudo().search_count([('employee_session_id', '=', self.id)], limit=1))

    def _number_now(self):
        """The number this one is on: the session's while it is the session's."""
        self.ensure_one()
        return (digits(self.sudo().session_id.authorized_number) if self.active else '') or self.own_number or ''

    # ------------------------------------------------------------ whose is it
    @api.model
    def _of_message(self, session, number):
        """The employee session of a message on this session and number."""
        Session = self.sudo().with_context(active_test=False)
        now = Session.search([('session_id', '=', session.id), ('active', '=', True)], limit=1)
        if now and (not digits(number) or same_number(now._number_now(), number)):
            return now
        if digits(number):
            old = Session.search([('session_id', '=', session.id), ('active', '=', False)], order='until desc, id desc')
            return old.filtered(lambda r: same_number(r.own_number, number))[:1]
        return now

    # ------------------------------------------------------------ what may change
    def write(self, vals):
        if not self.env.context.get('wa_switch'):
            for rec in self:
                changed = (('employee_id' in vals and vals['employee_id'] != rec.employee_id.id)
                           or ('session_id' in vals and vals['session_id'] != rec.session_id.id)
                           or ('phone_number' in vals and digits(vals['phone_number']) != digits(rec.phone_number)
                               and not same_number(vals['phone_number'], rec.phone_number)))
                if changed and rec._has_chats():
                    raise UserError(_(
                        "%s has chats on this number; they stay with it. For another person use 'Other employee', for "
                        "another number use WhatsApp Numbers > + Connect a number.", rec.employee_id.name))
        if 'active' in vals and 'until' not in vals:
            vals = dict(vals, until=False if vals['active'] else fields.Datetime.now())
        return super().write(vals)

    def unlink(self):
        for rec in self:
            if rec._has_chats():
                raise UserError(_("%s has chats, which would be deleted with it. Archive it instead.", rec.display_name))
        return super().unlink()

    # ------------------------------------------------------------ going on
    def _go_on_with(self, employee=None, number=None, session=None):
        """Another employee, number or session from now on. Returns the
        employee session that is the present one afterwards."""
        self.ensure_one()
        Session = self.sudo().with_context(active_test=False, wa_switch=True)
        rec = Session.browse(self.id)
        employee = employee or rec.employee_id
        session = session or rec.session_id
        number = digits(number) or digits(session.authorized_number) or rec.own_number or ''
        if employee == rec.employee_id and session == rec.session_id and same_number(number, rec.own_number):
            return rec
        other = Session.search([('active', '=', True), ('id', '!=', rec.id), '|', ('employee_id', '=', employee.id),
                                ('session_id', '=', session.id)], limit=1)
        if other:
            raise UserError(_("%(who)s has a number already: %(number)s.", who=other.employee_id.name,
                              number=self.env['whatsapp.connect']._pretty(other.own_number) or other.phone_number))
        phone = ('+' + number) if number else rec.phone_number
        vals = {'employee_id': employee.id, 'session_id': session.id, 'phone_number': phone}
        before = Session._before_on(employee, number)
        if not before and not rec._has_chats():
            rec.write(vals)
            return rec
        if rec.active:
            self.env['wa.communication.log'].sudo()._sync_for(rec)
        rec.write({'active': False})
        self.env.flush_all()
        if before:
            before.write(dict(vals, active=True))
            target = before
        else:
            target = rec.copy(dict(vals, active=True))
        target._took_over(rec)
        _logger.info("WA Tracker: %s goes on as %s", rec.display_name, target.display_name)
        return target

    @api.model
    def _before_on(self, employee, number):
        """The archived one of this employee on this number."""
        if not digits(number):
            return self.browse()
        old = self.sudo().with_context(active_test=False, wa_switch=True).search(
            [('employee_id', '=', employee.id), ('active', '=', False)], order='until desc, id desc')
        return old.filtered(lambda r: same_number(r.own_number, number))[:1]

    def _took_over(self, old):
        """Hook: what pointed to `old` goes on with this one."""

    def action_other_employee(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'wa.employee.handover', 'view_mode': 'form', 'target': 'new',
                'name': _("Other employee"), 'context': {'default_session_id': self.id}}

    # ------------------------------------------------------------ old mixed chats
    @api.model
    def _split_by_number(self):
        """Chats that were kept as one although our number changed: each number
        gets its own (archived) employee session. Run again, nothing happens.
        Returns {employee session: {number: messages}}."""
        Message = self.env['whatsapp.message'].sudo()
        Log = self.env['wa.communication.log'].sudo()
        done = {}
        for rec in self.sudo().search([]):
            logs = Log.search([('employee_session_id', '=', rec.id)])
            mine = (logs.message_id | Message.search([
                ('session_id', '=', rec.session_id.id), ('employee_session_id', '=', False)])
                    | Message.search([('employee_session_id', '=', rec.id)]))
            by = {}
            for message in mine:
                number = message.own_number or ''
                key = '' if not number or same_number(number, rec._number_now()) else number
                by[key] = by.get(key, Message) | message
            days, touched = set(), self.env['wa.conversation'].sudo()
            for number, messages in by.items():
                target = rec
                if number:
                    target = self._before_on(rec.employee_id, number)
                    if not target:
                        target = rec.with_context(wa_switch=True).copy({
                            'phone_number': '+' + number, 'active': False,
                            'since': min(messages.mapped('create_date')), 'until': max(messages.mapped('create_date'))})
                messages.filtered(lambda m, t=target: m.employee_session_id != t).write({'employee_session_id': target.id})
                done.setdefault(rec.id, {})[number or rec._number_now()] = len(messages)
                if target == rec:
                    continue
                for log in logs.filtered(lambda x, ms=messages: x.message_id in ms):
                    old = log.conversation_id
                    new = old and self.env['wa.conversation'].sudo()._get_or_create(target, old.phone, old.partner_id)
                    log.write({'employee_session_id': target.id, 'conversation_id': new.id if new else False})
                    touched |= (old | new) if new else old
                    if log.message_date:
                        days.add((target, log.message_date.date()))
                        days.add((rec, log.message_date.date()))
                    self.env['wa.keyword.alert.log'].sudo().search([('log_entry_id', '=', log.id)]).write(
                        {'employee_session_id': target.id})
                    self.env['wa.auto.reply'].sudo().search([('trigger_message_id', '=', log.id)]).write(
                        {'employee_session_id': target.id, 'conversation_id': new.id if new else False})
                self._chats_split(rec, target, messages)
            self.env.flush_all()
            for conv in touched.exists():
                if conv.log_ids:
                    conv._update_stats()
                elif conv._unused():
                    conv.unlink()
                else:
                    conv.write({'total_messages': 0, 'sent_count': 0, 'received_count': 0, 'first_message_date': False,
                                'last_message_date': False, 'avg_response_minutes': 0})
            Score = self.env['wa.quality.score'].sudo()
            for target, day in sorted(days, key=lambda d: (d[0].id, d[1])):
                Score.search([('employee_session_id', '=', target.id), ('score_date', '=', day)]).unlink()
                Score._compute_score_for(target, day)
            first = Message.search([('employee_session_id', '=', rec.id)], order='create_date', limit=1)
            if first and (not rec.since or rec.since > first.create_date):
                rec.since = first.create_date
            (rec | self.with_context(active_test=False).search([('employee_id', '=', rec.employee_id.id)]))._compute_stats()
        return done

    @api.model
    def _chats_split(self, rec, target, messages):
        """Hook: what else belonged to these messages."""


class ConversationUnused(models.Model):
    _inherit = 'wa.conversation'

    def _unused(self):
        self.ensure_one()
        return not self.env['wa.auto.reply'].sudo().search_count([('conversation_id', '=', self.id)], limit=1)


class WhatsAppSessionNumber(models.Model):
    _inherit = 'whatsapp.session'

    def _number_changed(self, old, new):
        super()._number_changed(old, new)
        link = self.env['wa.employee.session'].sudo().search([('session_id', '=', self.id), ('active', '=', True)], limit=1)
        if link:
            link._go_on_with(number=new)


class EmployeeHandover(models.TransientModel):
    _name = 'wa.employee.handover'
    _description = 'Another employee on this number'

    session_id = fields.Many2one('wa.employee.session', required=True, readonly=True, ondelete='cascade')
    employee_id = fields.Many2one('hr.employee', 'New employee', required=True)

    def action_do(self):
        self.ensure_one()
        if not self.env.user.has_group('base.group_system'):
            raise UserError(_("Only an administrator can do this."))
        target = self.session_id._go_on_with(employee=self.employee_id)
        return {'type': 'ir.actions.act_window', 'res_model': 'wa.employee.session', 'res_id': target.id, 'view_mode': 'form',
                'target': 'current'}
