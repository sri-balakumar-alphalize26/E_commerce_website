"""Change the company of a WhatsApp number - confirmation pop-up (27 Nov 2026).

Shows, in plain words, what the move does to "Sending per company" before
anything changes; Confirm does it, Cancel does nothing.
"""
from markupsafe import Markup, escape

from odoo import _, api, fields, models


class WhatsAppSessionCompanyWizard(models.TransientModel):
    _name = 'whatsapp.session.company.wizard'
    _description = 'Change the company of a WhatsApp number'

    session_id = fields.Many2one('whatsapp.session', required=True, readonly=True, ondelete='cascade')
    current_company_id = fields.Many2one(related='session_id.company_id', string="Now belongs to")
    company_id = fields.Many2one('res.company', string="Move to", required=True,
                                 domain="[('id', 'in', allowed_company_ids)]")
    allowed_company_ids = fields.Many2many('res.company', compute='_compute_allowed')
    summary = fields.Html("What will change", compute='_compute_summary', sanitize=False)

    @api.depends('session_id')
    def _compute_allowed(self):
        for rec in self:
            rec.allowed_company_ids = self.env.user.company_ids

    @api.depends('session_id', 'company_id')
    def _compute_summary(self):
        for rec in self:
            if not rec.session_id or not rec.company_id:
                rec.summary = False
            elif rec.company_id == rec.session_id.company_id:
                rec.summary = Markup('<p>%s</p>') % _("It already belongs to this company.")
            else:
                lines = rec.session_id._wa_move_plan(rec.company_id)
                rec.summary = Markup('<ul class="mb-0">%s</ul>') % Markup('').join(
                    Markup('<li>%s</li>') % escape(line) for line in lines)

    def action_confirm(self):
        self.ensure_one()
        self.session_id._check_may_choose()
        if self.company_id != self.session_id.company_id:
            self.session_id._wa_move_to_company(self.company_id)
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {
                'title': _("Company changed"),
                'message': _("%(num)s now belongs to %(co)s. Sending per company is updated.",
                             num=self.session_id.name, co=self.company_id.name),
                'type': 'success', 'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }
