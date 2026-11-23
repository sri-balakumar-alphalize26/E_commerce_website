# -*- coding: utf-8 -*-
"""Vendors & Customer Replies: what the numbers do, and numbers that cannot work
are refused (23 Nov 2026). Checked when a person saves the page; code that writes
settings is as before."""
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

DAY = 24 * 60


class SaAiSettingsEasy(models.Model):
    _inherit = 'sa.ai.settings'

    easy_example = fields.Text(compute='_compute_easy_example')
    easy_vendors = fields.Text(compute='_compute_easy_vendors')

    @api.depends('margin_percent', 'sourcing_window_minutes', 'price_approval_enabled', 'price_approval_tolerance_percent',
                 'customer_reply_minutes', 'pay_remind_minutes', 'pay_remind_max')
    def _compute_easy_example(self):
        money = self.env.company.currency_id.name or ''
        for rec in self:
            sell = 100.0 * (1.0 + (rec.margin_percent or 0.0) / 100.0)
            lines = [
                _("1. A customer asks for a product that is not in stock. Every vendor of its category is asked."),
                _("2. We wait up to %s minutes. When every vendor has answered we go on at once.", rec.sourcing_window_minutes or 10),
                _("3. Vendor A says 110 %(m)s, vendor B says 100 %(m)s. The lowest is taken: 100 %(m)s.", m=money),
                _("4. Your margin of %(p)s%% is added: %(sell).2f %(m)s.", p='%g' % (rec.margin_percent or 0.0), sell=sell, m=money),
            ]
            if rec.price_approval_enabled:
                tolerance = rec.price_approval_tolerance_percent or 0.0
                lines.append(_("5. The product page has another price? You choose on Store > Enquiries before the customer is told.")
                             if not tolerance else
                             _("5. The product page price differs by more than %s%%? You choose on Store > Enquiries before the "
                               "customer is told.", '%g' % tolerance))
            else:
                lines.append(_("5. The customer is told this price at once, also when the product page has another one."))
            lines.append(_("6. The customer has %s minutes to answer.", rec.customer_reply_minutes) if rec.customer_reply_minutes
                         else _("6. The customer can answer for 24 hours."))
            lines.append(_("7. Not paid? A reminder after %(n)s minutes, at most %(x)s time(s).", n=rec.pay_remind_minutes,
                           x=rec.pay_remind_max) if rec.pay_remind_minutes and rec.pay_remind_max else _("7. Not paid? No reminder is sent."))
            rec.easy_example = '\n'.join(lines)

    def _compute_easy_vendors(self):
        Category = self.env['product.category'].sudo()
        every = Category.search([])
        without = every.filtered(lambda c: not c._sa_vendors_for_sourcing())
        for rec in self:
            rec.easy_vendors = _("%(have)s of %(all)s product categories have vendors to ask.",
                                 have=len(every) - len(without), all=len(every))

    def action_sa_open_categories(self):
        return {'type': 'ir.actions.act_window', 'name': _("Product Categories"), 'res_model': 'product.category',
                'view_mode': 'list,form', 'target': 'current'}

    # ------------------------------------------------------------ what cannot work
    def _easy_problems(self, names):
        """What is wrong with the fields in `names`, one sentence each."""
        self.ensure_one()
        out = []
        if 'sourcing_window_minutes' in names and not 1 <= self.sourcing_window_minutes <= DAY:
            out.append(_("Wait for vendor prices: type 1 to 1440 minutes (a day)."))
        if 'margin_percent' in names and not 0 <= self.margin_percent <= 500:
            out.append(_("Your margin: type 0 to 500 percent."))
        if {'margin_percent', 'min_margin_percent'} & names and self.bargain_enabled \
                and self.min_margin_percent > self.margin_percent:
            out.append(_("Your margin (%(a)s%%) is below the Lowest Margin of the Bargaining page (%(b)s%%).",
                         a='%g' % self.margin_percent, b='%g' % self.min_margin_percent))
        if 'price_approval_tolerance_percent' in names and not 0 <= self.price_approval_tolerance_percent <= 100:
            out.append(_("Ignore small differences: type 0 to 100 percent."))
        if 'customer_reply_minutes' in names and not (self.customer_reply_minutes == 0 or 5 <= self.customer_reply_minutes <= DAY):
            out.append(_("Customer must answer within: type 0 (a whole day) or 5 to 1440 minutes."))
        if 'pay_remind_minutes' in names and not (self.pay_remind_minutes == 0 or 5 <= self.pay_remind_minutes <= 7 * DAY):
            out.append(_("Remind after: type 0 (never) or 5 to 10080 minutes (a week)."))
        if 'pay_remind_max' in names and not 0 <= self.pay_remind_max <= 10:
            out.append(_("How many reminders: type 0 to 10."))
        phone = (self.price_escalation_phone or '').strip()
        if 'price_escalation_phone' in names and phone:
            digits = ''.join(c for c in phone if c.isdigit())
            if not self.env['whatsapp.connect']._split('+' + digits):
                out.append(_("\"%s\" is not a whole phone number. Type it with the country code.", phone))
        return out

    def web_save(self, vals, specification, next_id=None):
        result = super().web_save(vals, specification, next_id=next_id)
        for rec in self:
            problems = rec._easy_problems(set(vals))
            if problems:
                raise ValidationError('\n'.join(problems))
        return result
