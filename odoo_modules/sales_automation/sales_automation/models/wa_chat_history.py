"""Groups and enquiries follow when an employee's number changes (23 Nov 2026)."""
from odoo import api, models


class EmployeeNumberSales(models.Model):
    _inherit = 'wa.employee.session'

    def _took_over(self, old):
        super()._took_over(old)
        self.env['sa.sales.group'].sudo().with_context(active_test=False).search([
            ('employee_session_id', '=', old.id), ('session_id', '=', self.session_id.id),
        ]).write({'employee_session_id': self.id})

    @api.model
    def _chats_split(self, rec, target, messages):
        """An enquiry of the old number keeps its private chat: the one that moved."""
        super()._chats_split(rec, target, messages)
        Conversation = self.env['wa.conversation'].sudo()
        for request in messages.sa_request_id.filtered(lambda r: r.conversation_id.employee_session_id == rec):
            mine = self.env['whatsapp.message'].sudo().search([('sa_request_id', '=', request.id)])
            if mine <= messages:
                moved = Conversation.search([('employee_session_id', '=', target.id),
                                             ('phone', '=', request.conversation_id.phone)], limit=1)
                if moved:
                    request.conversation_id = moved.id


class ConversationSales(models.Model):
    _inherit = 'wa.conversation'

    def _unused(self):
        return super()._unused() and not self.env['sa.group.request'].sudo().search_count(
            [('conversation_id', '=', self.id)], limit=1)
