# -*- coding: utf-8 -*-
"""Connect a number: which groups it answers; and the alert when a number that
answers groups goes offline (23 Nov 2026)."""
import logging
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

OFFLINE_MINUTES = 5


class WhatsAppConnectGroups(models.AbstractModel):
    _inherit = 'whatsapp.connect'

    @api.model
    def groups(self, session_id):
        self._check_admin()
        session = self.env['whatsapp.session'].sudo().browse(int(session_id or 0)).exists()
        if not session:
            raise UserError(_("That WhatsApp session is no longer there."))
        Group = self.env['sa.sales.group'].sudo()
        error = ''
        try:
            session.action_sa_sync_groups()
        except UserError as err:            # what was read before is still listed
            error = self._last_line(err)
        taken = {g.group_jid: g.session_id.name for g in Group.search(
            [('enabled', '=', True), ('session_id', '!=', session.id), ('session_id.active', '=', True)])}
        rows = [{'id': g.id, 'name': g.name or g.group_jid, 'members': g.member_count,
                 'enabled': g.enabled, 'taken': taken.get(g.group_jid, '') if not g.enabled else ''}
                for g in Group.search([('session_id', '=', session.id), ('group_type', '=', 'customer')], order='name')]
        return {'available': True, 'groups': rows, 'error': error if not rows or error else ''}

    @api.model
    def finish(self, session_id, group_ids=None):
        out = super().finish(session_id, group_ids)
        session = self.env['whatsapp.session'].sudo().browse(int(session_id))
        Group = self.env['sa.sales.group'].sudo()
        chosen = Group.search([('id', 'in', [int(i) for i in group_ids or []]), ('session_id', '=', session.id),
                               ('group_type', '=', 'customer')])
        employee = self.env['wa.employee.session'].sudo().search([('session_id', '=', session.id)], limit=1)
        # only those not on yet get the company: one set by hand stays
        for group in chosen.filtered(lambda g: not g.enabled):
            values = {'enabled': True, 'company_id': session.company_id.id}
            if employee:
                values['employee_session_id'] = employee.id
            group.write(values)
        lines = out['lines']
        lines.append({'ok': bool(chosen), 'text': _("%s group(s) on", len(chosen)) if chosen else _("No group is on yet")})
        if session.company_id:
            lines.append({'ok': True, 'text': _("Company: %(company)s, %(currency)s", company=session.company_id.name,
                                                currency=session.company_id.currency_id.name)})
        for group in chosen:
            if (group.invite_url or '').strip():
                continue
            try:
                url, _why = group._sa_invite_from_gateway()
            except Exception as err:  # noqa: BLE001 - the groups are on either way
                _logger.info("Connect a number: invite link of %s: %s", group.id, err)
                url = ''
            if url:
                group.write({'invite_url': url, 'invite_error': False})
            else:
                lines.append({'ok': False, 'text': _("%s: no invite link (make this number an admin of the group)",
                                                     group.name)})
        return out


class WhatsAppSessionGroupList(models.Model):
    _inherit = 'whatsapp.session'

    sa_group_ids = fields.One2many('sa.sales.group', 'session_id', string='WhatsApp Groups')


class SalesGroupOnce(models.Model):
    _inherit = 'sa.sales.group'

    sa_paused = fields.Boolean('On again with its number', readonly=True, copy=False,
                               help="Its WhatsApp number was turned off while this group was on.")

    @api.constrains('enabled', 'group_jid', 'session_id', 'active')
    def _check_one_number_per_group(self):
        """One group, one number: with two on, which one answers is chance."""
        for rec in self:
            if not (rec.enabled and rec.active):
                continue
            other = self.sudo().search([
                ('id', '!=', rec.id), ('group_jid', '=', rec.group_jid), ('enabled', '=', True),
                ('session_id', '!=', rec.session_id.id), ('session_id.active', '=', True)], limit=1)
            if other:
                raise ValidationError(_("'%(group)s' is already on in session '%(session)s'. Switch it off there first.",
                                        group=rec.name, session=other.session_id.name))


class WhatsAppSessionGroups(models.Model):
    _inherit = 'whatsapp.session'

    sa_group_count = fields.Integer('Groups on', compute='_compute_sa_group_count')
    sa_offline_since = fields.Datetime('Offline since', readonly=True, copy=False)
    sa_offline_told = fields.Boolean('Offline alert given', readonly=True, copy=False)

    def _compute_sa_group_count(self):
        counts = dict(self.env['sa.sales.group'].sudo()._read_group(
            [('session_id', 'in', self.ids), ('enabled', '=', True)], ['session_id'], ['__count']))
        for rec in self:
            rec.sa_group_count = counts.get(rec, 0)

    # ------------------------------------------------------------ off / on
    def _off_summary(self):
        self.ensure_one()
        out = super()._off_summary()
        n = self._sa_groups_on()
        if n:
            out.append(_("%s group(s) on", n))
        Request = self.env['sa.group.request'].sudo()
        mine = [('group_id.session_id', '=', self.id)]
        n = Request.search_count(mine + [('state', 'in', (
            'awaiting_confirm', 'finding', 'sourcing', 'awaiting_vendor_pick', 'quoted', 'negotiating', 'awaiting_order_confirm'))])
        if n:
            out.append(_("%s open enquiry(ies)", n))
        orders = Request.search(mine + [('order_id.state', 'in', ('draft', 'sent', 'sale')),
                                        ('sa_paid_told_on', '=', False)]).order_id
        if orders:
            out.append(_("%s order(s) not finished", len(orders)))
        return out

    def _number_off(self, removed=False):
        super()._number_off(removed=removed)
        for session in self:
            session._sa_offline_activities().unlink()
            groups = self.env['sa.sales.group'].sudo().search([('session_id', '=', session.id)])
            groups.filtered('enabled').write({'enabled': False, 'sa_paused': True})
            if removed:
                groups.write({'sa_paused': False})
        self.sudo().write({'sa_offline_since': False, 'sa_offline_told': False})

    def _number_on(self):
        notes = super()._number_on() or []
        for group in self.env['sa.sales.group'].sudo().search([('session_id', 'in', self.ids), ('sa_paused', '=', True)]):
            other = self.env['sa.sales.group'].sudo().search([
                ('group_jid', '=', group.group_jid), ('enabled', '=', True),
                ('session_id', '!=', group.session_id.id), ('session_id.active', '=', True)], limit=1)
            if other:
                notes.append(_("%(group)s stays off: it is on in %(session)s now.", group=group.name,
                               session=other.session_id.name))
            else:
                group.with_context(sa_no_invite_fetch=True).write({'enabled': True})
            group.sa_paused = False
        return notes

    def _has_history(self):
        return super()._has_history() or bool(self.env['sa.sales.group'].sudo().with_context(
            active_test=False).search_count([('session_id', '=', self.id)], limit=1))

    def _sa_groups_on(self):
        """Counted now: the field on the screen may be a moment old."""
        self.ensure_one()
        return self.env['sa.sales.group'].sudo().search_count(
            [('session_id', '=', self.id), ('enabled', '=', True)])

    def _check_number_change(self, instance):
        super()._check_number_change(instance)
        known = self.authorized_number and not (self.instance_name or '').startswith('pending-')
        n = self._sa_groups_on() if known else 0
        if n:
            raise UserError(_("Session '%(session)s' has %(n)s group(s) on and would become another number. Switch its "
                              "groups off first.", session=self.name, n=n))

    # ------------------------------------------------------------ offline
    @api.model
    def _cron_sync_status(self):
        res = super()._cron_sync_status()
        try:
            with self.env.cr.savepoint():
                self._sa_offline_check()
        except Exception as err:  # noqa: BLE001 - the status job goes on
            _logger.warning("WhatsApp: offline check skipped: %s", err)
        return res

    @api.model
    def _sa_offline_check(self):
        now = fields.Datetime.now()
        for session in self.sudo().search([('active', '=', True)]):
            off = session.status != 'connected' and session._sa_groups_on()
            if not off:
                if session.sa_offline_since or session.sa_offline_told:
                    session._sa_offline_activities().unlink()
                    session.write({'sa_offline_since': False, 'sa_offline_told': False})
                continue
            if not session.sa_offline_since:
                session.sa_offline_since = now
            elif not session.sa_offline_told and session.sa_offline_since <= now - timedelta(minutes=OFFLINE_MINUTES):
                session._sa_offline_tell()
                session.sa_offline_told = True

    def _sa_offline_summary(self):
        return _("WhatsApp number %s is offline", ('+' + self.authorized_number) if self.authorized_number else self.name)

    def _sa_offline_activities(self):
        self.ensure_one()
        link = self.env['wa.employee.session'].sudo().search([('session_id', '=', self.id)], limit=1)
        if not link:
            return self.env['mail.activity'].sudo()
        return self.env['mail.activity'].sudo().search([
            ('res_model', '=', 'hr.employee'), ('res_id', '=', link.employee_id.id),
            ('summary', '=', self._sa_offline_summary())])

    def _sa_offline_tell(self):
        """A to-do for its employee and the managers, and a notice on their
        screens. Never by WhatsApp or e-mail: either may be what is down."""
        self.ensure_one()
        link = self.env['wa.employee.session'].sudo().search([('session_id', '=', self.id)], limit=1)
        managers = self.env.ref('sales_automation.group_sa_manager', raise_if_not_found=False)
        users = link.employee_id.user_id
        if managers:
            users |= self.env['res.users'].sudo().search(
                [('all_group_ids', 'in', managers.id), ('share', '=', False), ('active', '=', True)], limit=10)
        text = _("%(summary)s: %(n)s group(s) get no answer. WA Tracker > Configuration > WhatsApp Numbers > Scan again.",
                 summary=self._sa_offline_summary(), n=self._sa_groups_on())
        for user in users:
            if link:
                link.employee_id.sudo().with_context(mail_activity_quick_update=True).activity_schedule(
                    'mail.mail_activity_data_todo', summary=self._sa_offline_summary(), note=text, user_id=user.id)
            user.partner_id._bus_send('simple_notification', {
                'type': 'danger', 'sticky': True, 'title': self._sa_offline_summary(), 'message': text})
        _logger.warning("WhatsApp: session %s offline since %s with %s group(s) on - %s user(s) told",
                        self.name, self.sa_offline_since, self._sa_groups_on(), len(users))
