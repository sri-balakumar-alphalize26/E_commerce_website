# -*- coding: utf-8 -*-
"""A group is turned on only with somebody to answer it (23 Nov 2026)."""
from odoo import _, api, models
from odoo.exceptions import RedirectWarning, ValidationError


class SalesGroupEmployee(models.Model):
    _inherit = 'sa.sales.group'

    def web_save(self, vals, specification, next_id=None):
        # On the screen the refusal brings a button. By code it is the plain
        # refusal of _check_enabled_has_employee_session, as before.
        if vals.get('enabled') and not vals.get('employee_session_id') and self.env.user.has_group('base.group_system'):
            for rec in self:
                session = rec.session_id
                if vals.get('group_type', rec.group_type) == 'customer' and not rec.employee_session_id \
                        and session.active and not rec._sa_employee_session_for(session.id):
                    raise RedirectWarning(
                        rec._sa_no_employee_text(), self.env.ref('whatsapp_gateway.action_whatsapp_connect').id,
                        _("Choose the employee"), {'give_session_id': session.id})
        return super().web_save(vals, specification, next_id=next_id)

    @api.constrains('enabled', 'employee_session_id', 'session_id')
    def _check_employee_can_answer(self):
        """Leads may go to another employee's number, but not to one that is
        off: the answers would go nowhere."""
        for rec in self:
            link = rec.employee_session_id
            if rec.enabled and rec.group_type == 'customer' and link \
                    and link.session_id != rec.session_id and not link.session_id.active:
                raise ValidationError(_(
                    "%(who)s is on the WhatsApp session \"%(session)s\", which is off, so nobody would answer "
                    "\"%(group)s\". Choose an employee whose number is on.",
                    who=link.employee_id.name, session=link.session_id.name, group=rec.name))


class WhatsAppSessionGroups(models.Model):
    _inherit = 'whatsapp.session'

    def _setup_steps(self):
        steps = super()._setup_steps()
        n = self._sa_groups_on() if isinstance(self.id, int) else 0
        steps.append(('groups', bool(n), _("%s group(s) on", n) if n else _("Groups"),
                      _("Press Sync Groups and turn on the groups this number answers.")))
        return steps
