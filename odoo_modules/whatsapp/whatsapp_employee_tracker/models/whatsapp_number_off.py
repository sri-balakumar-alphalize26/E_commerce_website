"""A removed number's employee is free for another one (23 Nov 2026).
Its chats in WA Tracker can be cleared: a tick in Remove, or Clear chats (27 Nov 2026)."""
from odoo import _, api, fields, models
from odoo.exceptions import AccessError

# WA Tracker's own records of a number, children first. Orders, invoices and the
# WhatsApp send log (whatsapp.message) are never touched.
CHAT_MODELS = ('wa.keyword.alert.log', 'wa.message.tone', 'wa.quality.score', 'wa.auto.reply',
               'wa.communication.log', 'wa.conversation')


class WhatsAppSessionOffEmployee(models.Model):
    _inherit = 'whatsapp.session'

    def _number_off(self, removed=False):
        super()._number_off(removed=removed)
        if removed:
            self.env['wa.employee.session'].sudo().search([
                ('session_id', 'in', self.ids), ('active', '=', True)]).write({'active': False})

    # ------------------------------------------------------------ clear chats
    def _tracker_cards(self):
        return self.env['wa.employee.session'].sudo().with_context(active_test=False).search(
            [('session_id', 'in', self.ids)])

    def _tracker_chat_counts(self):
        cards = self._tracker_cards()
        if not cards:
            return 0, 0
        chats = self.env['wa.conversation'].sudo().with_context(active_test=False).search_count(
            [('employee_session_id', 'in', cards.ids)])
        lines = self.env['wa.communication.log'].sudo().search_count([('employee_session_id', 'in', cards.ids)])
        return chats, lines

    def _clear_tracker_chats(self):
        """Every chat and message of these numbers in WA Tracker, gone."""
        if not (self.env.user.has_group('base.group_system')
                or self.env.user.has_group('whatsapp_employee_tracker.group_wa_tracker_manager')):
            raise AccessError(_("Only an administrator or a WA Tracker manager can clear chats."))
        cards = self._tracker_cards()
        if not cards:
            return 0
        chats, lines = self._tracker_chat_counts()
        for name in CHAT_MODELS:
            self.env[name].sudo().with_context(active_test=False).search(
                [('employee_session_id', 'in', cards.ids)]).unlink()
        cards.sudo()._refresh_totals()
        import logging
        logging.getLogger(__name__).info("WA Tracker: chats of %s cleared by %s (%s chats, %s messages)",
                                         ', '.join(self.mapped('name')), self.env.user.login, chats, lines)
        return chats

    def action_clear_chats(self):
        self.ensure_one()
        chats, lines = self._tracker_chat_counts()
        self._clear_tracker_chats()
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
            'type': 'success', 'message': _("%(chats)s chats and %(lines)s messages cleared in WA Tracker.",
                                            chats=chats, lines=lines),
            'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'}}}

    def _has_history(self):
        return super()._has_history() or bool(self.env['wa.employee.session'].sudo().with_context(
            active_test=False).search_count([('session_id', '=', self.id)], limit=1))


class WhatsAppNumberOffClear(models.TransientModel):
    _inherit = 'whatsapp.number.off'

    clear_chats = fields.Boolean('Also clear its chats in WA Tracker', default=False)
    chats_text = fields.Char(compute='_compute_chats_text')

    @api.depends('session_id')
    def _compute_chats_text(self):
        for rec in self:
            chats, lines = rec.session_id._tracker_chat_counts() if rec.session_id else (0, 0)
            rec.chats_text = _("%(chats)s chats, %(lines)s messages", chats=chats, lines=lines) if chats or lines else ''

    def action_do(self):
        session, clear = self.session_id, self.do == 'remove' and self.clear_chats
        result = super().action_do()
        if clear:
            session._clear_tracker_chats()
        return result
