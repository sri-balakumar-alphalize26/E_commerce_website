"""Which number and which e-mail is a company's Main (26 Nov 2026).

A company (or an Odoo branch) may have many numbers, each with or without its
own e-mail - connected here, or already connected in WA Tracker. One number is
ticked Main for its documents and one Main for e-mail. The tick is the same
thing as the company's "Send WhatsApp from" / "Send email from" in WhatsApp and
Email settings: one choice, shown in both places.
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class WhatsAppSessionMain(models.Model):
    _inherit = 'whatsapp.session'

    is_main_whatsapp = fields.Boolean(
        "Main for documents", compute='_compute_is_main',
        help="Its company's quotations, orders, invoices and receipts go out on this number.")
    is_main_email = fields.Boolean(
        "Main for e-mail", compute='_compute_is_main',
        help="Its company's documents are e-mailed from this number's address.")
    main_for = fields.Char("Main for", compute='_compute_is_main',
                           help="The companies (and branches) that send from this number or address.")

    @api.depends('company_id')
    def _compute_is_main(self):
        configs = self.env['whatsapp.config'].sudo().search([])
        for rec in self:
            wa = configs.filtered(lambda c: c.default_whatsapp_session_id.id == rec.id)
            mail = configs.filtered(lambda c: c.email_session_id.id == rec.id)
            mine = rec.company_id
            rec.is_main_whatsapp = bool(wa.filtered(lambda c: c.company_id == mine)) if mine else bool(wa)
            rec.is_main_email = bool(mail.filtered(lambda c: c.company_id == mine)) if mine else bool(mail)
            parts = []
            for company in (wa | mail).company_id:
                what = []
                if company in wa.company_id:
                    what.append(_("WhatsApp"))
                if company in mail.company_id:
                    what.append(_("e-mail"))
                parts.append('%s (%s)' % (company.name, ', '.join(what)))
            rec.main_for = '; '.join(parts)

    def _check_may_choose(self):
        if not self.env.user.has_group('whatsapp_gateway.group_whatsapp_manager') \
                and not self.env.user.has_group('base.group_system'):
            raise UserError(_("Only a WhatsApp manager can choose the main number."))

    def _config_of_company(self):
        self.ensure_one()
        if not self.company_id:
            raise UserError(_("Set the company of %s first.", self.name))
        return self.env['whatsapp.config'].sudo().get_config(self.company_id.id)

    def action_make_main_whatsapp(self):
        self.ensure_one()
        self._check_may_choose()
        self._config_of_company().default_whatsapp_session_id = self.id
        return self._main_done(_("%(company)s sends its documents on %(number)s now.",
                                 company=self.company_id.name, number=self.name))

    def action_make_main_email(self):
        self.ensure_one()
        self._check_may_choose()
        if not self.authorized_email:
            raise UserError(_("%s has no e-mail yet. Press Add email on it first.", self.name))
        self._config_of_company().email_session_id = self.id
        return self._main_done(_("%(company)s e-mails its documents from %(mail)s now.",
                                 company=self.company_id.name, mail=self.authorized_email))

    # ── A number moved to another company / branch (27 Nov 2026) ─────────────
    # One logic for the number's page, Settings and Sending per company: the
    # company it goes to sends from it; a company that sent from it and is not
    # related (parent / branch) to the new one stops, falling back to another
    # number of its own or "not set". Always behind a confirmation pop-up.

    @staticmethod
    def _wa_related(a, b):
        """Same company, or one is a branch (child) of the other."""
        if not a or not b:
            return False
        return a == b or a in b.parent_ids or b in a.parent_ids

    def _wa_replacement(self, company, email=False):
        """Another active number of `company` (not this one) to fall back to."""
        domain = [('active', '=', True), ('company_id', '=', company.id), ('id', '!=', self.id)]
        if email:
            domain += [('authorized_email', '!=', False)]
        return self.sudo().search(domain, order='id', limit=1)

    def _wa_move_plan(self, new_company):
        """What a move to `new_company` will do, as plain sentences."""
        self.ensure_one()
        Config = self.env['whatsapp.config'].sudo()
        lines = []
        target = Config.search([('company_id', '=', new_company.id)], limit=1)
        main = target.default_whatsapp_session_id
        if not main or main == self:
            lines.append(_("%(co)s will send WhatsApp from %(num)s.", co=new_company.name, num=self.name))
        else:
            lines.append(_("%(co)s keeps sending WhatsApp from %(main)s; %(num)s becomes one more of its numbers.",
                           co=new_company.name, main=main.name, num=self.name))
        if self.authorized_email:
            mail = target.email_session_id
            if not mail or mail == self:
                lines.append(_("%(co)s will e-mail from %(mail)s.", co=new_company.name, mail=self.authorized_email))
        for cfg in Config.search(['|', ('default_whatsapp_session_id', '=', self.id), ('email_session_id', '=', self.id)]):
            if self._wa_related(cfg.company_id, new_company):
                continue
            rep = self._wa_replacement(cfg.company_id)
            if rep:
                lines.append(_("%(co)s stops sending from %(num)s and switches to %(rep)s.",
                               co=cfg.company_id.name, num=self.name, rep=rep.name))
            else:
                lines.append(_("%(co)s stops sending from %(num)s - not set (it has no other number).",
                               co=cfg.company_id.name, num=self.name))
        return lines

    def _wa_move_to_company(self, new_company):
        """Do the move (after the user confirmed)."""
        self.ensure_one()
        Config = self.env['whatsapp.config'].sudo()
        for cfg in Config.search(['|', ('default_whatsapp_session_id', '=', self.id), ('email_session_id', '=', self.id)]):
            if self._wa_related(cfg.company_id, new_company):
                continue
            vals = {}
            if cfg.default_whatsapp_session_id == self:
                vals['default_whatsapp_session_id'] = self._wa_replacement(cfg.company_id).id or False
            if cfg.email_session_id == self:
                vals['email_session_id'] = self._wa_replacement(cfg.company_id, email=True).id or False
            cfg.with_context(wa_share=True).write(vals)
        if self.company_id != new_company:
            super(WhatsAppSessionMain, self.sudo().with_context(wa_moving=True)).write({'company_id': new_company.id})
        self._wa_claim_main()

    def _wa_claim_main(self):
        """A company without a main number / e-mail gets this one (never replaces a choice)."""
        for rec in self.sudo():
            if not rec.active or not rec.company_id:
                continue
            cfg = self.env['whatsapp.config'].sudo().get_config(rec.company_id.id)
            vals = {}
            if not cfg.default_whatsapp_session_id or not cfg.default_whatsapp_session_id.active:
                vals['default_whatsapp_session_id'] = rec.id
            if rec.authorized_email and (not cfg.email_session_id or not cfg.email_session_id.active):
                vals['email_session_id'] = rec.id
            if vals:
                cfg.with_context(wa_share=True).write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._wa_claim_main()          # a number connected for a company with no main
        return records

    def write(self, vals):
        moving = []
        if 'company_id' in vals and not self.env.context.get('wa_moving'):
            new = self.env['res.company'].browse(vals['company_id'])
            moving = [rec for rec in self if rec.company_id != new]
        res = super().write(vals)
        for rec in moving:                # changed directly (another module): same result as the pop-up
            rec.with_context(wa_moving=True)._wa_move_to_company(rec.company_id)
        if ('authorized_email' in vals or 'active' in vals) and not self.env.context.get('wa_moving'):
            self._wa_claim_main()         # e-mail added / turned on: main e-mail if the company has none
        return res

    def action_change_company(self):
        """The pop-up: choose the company, see what changes, Confirm."""
        self.ensure_one()
        self._check_may_choose()
        return {
            'type': 'ir.actions.act_window', 'res_model': 'whatsapp.session.company.wizard',
            'view_mode': 'form', 'target': 'new', 'name': _("Change the company of %s", self.name),
            'context': {'default_session_id': self.id},
        }

    def _main_done(self, message):
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'title': _("Main chosen"), 'message': message, 'type': 'success', 'sticky': False,
                       'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'}},
        }
