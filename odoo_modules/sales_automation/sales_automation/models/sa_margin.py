# -*- coding: utf-8 -*-
"""Margin: one meaning everywhere (24 Nov 2026).

What is added to the cost, in percent of the cost. One normal margin; when
Different Margins is on, a product category OR a customer group may have its
own - never both at once, so it is always plain which one counts."""
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class SaMarginRule(models.Model):
    _name = 'sa.margin.rule'
    _description = 'Own margin of a category or a group'
    _order = 'id'

    cat_settings_id = fields.Many2one('sa.ai.settings', ondelete='cascade', index=True)
    group_settings_id = fields.Many2one('sa.ai.settings', ondelete='cascade', index=True)
    categ_id = fields.Many2one('product.category', 'Product Category', ondelete='cascade', index=True)
    group_id = fields.Many2one('sa.sales.group', 'Customer Group', ondelete='cascade', index=True)
    percent = fields.Float('Margin (%)', default=lambda self: self.env['sa.ai.settings'].sudo().get_settings().margin_percent)
    sell_example = fields.Float('Customer Pays for 100', compute='_compute_sell_example')

    _categ_once = models.Constraint('unique(categ_id)', 'This category has an own margin already.')
    _group_once = models.Constraint('unique(group_id)', 'This group has an own margin already.')

    @api.depends('percent')
    def _compute_sell_example(self):
        for rule in self:
            rule.sell_example = 100.0 + (rule.percent or 0.0)

    @api.constrains('categ_id', 'group_id', 'percent')
    def _check_rule(self):
        for rule in self:
            if bool(rule.categ_id) == bool(rule.group_id):
                raise ValidationError(_("Choose a category or a group."))
            if not 0 <= rule.percent <= 500:
                raise ValidationError(_("%s: type a margin of 0 to 500 percent.", rule._label()))

    def _label(self):
        self.ensure_one()
        return self.categ_id.display_name or self.group_id.name or ''


class SaAiSettingsMargin(models.Model):
    _inherit = 'sa.ai.settings'

    margin_rules_enabled = fields.Boolean('Different Margins', default=False)
    margin_rules_by = fields.Selection([('category', 'Product category'), ('group', 'Customer group')],
                                       'Different By', default='category', required=True)
    margin_category_ids = fields.One2many('sa.margin.rule', 'cat_settings_id', 'Categories With an Own Margin')
    margin_group_ids = fields.One2many('sa.margin.rule', 'group_settings_id', 'Groups With an Own Margin')
    sa_money = fields.Char(compute='_compute_sa_money')

    @api.depends_context('company')
    def _compute_sa_money(self):
        for rec in self:
            rec.sa_money = self.env.company.currency_id.name or ''

    @api.model
    def _sa_sell(self, cost, margin):
        return (cost or 0.0) * (1.0 + (margin or 0.0) / 100.0)

    def _sa_margin_for(self, category=None, group=None):
        """The margin in percent for a product's category and the asking group."""
        self.ensure_one()
        settings = self.sudo()
        if settings.margin_rules_enabled:
            if settings.margin_rules_by == 'group':
                rule = settings.margin_group_ids.filtered(lambda r: r.group_id == group)[:1] if group else False
                if rule:
                    return rule.percent
            else:
                own = {rule.categ_id.id: rule.percent for rule in settings.margin_category_ids}
                category = category.sudo() if category else category
                while category:
                    if category.id in own:
                        return own[category.id]
                    category = category.parent_id
        return settings.margin_percent or 0.0

    def _easy_problems(self, names):
        out = super()._easy_problems(names)
        touched = {'margin_rules_enabled', 'margin_rules_by', 'margin_category_ids', 'margin_group_ids',
                   'min_margin_percent', 'bargain_enabled'}
        if touched & names and self.margin_rules_enabled and self.bargain_enabled:
            rules = self.margin_group_ids if self.margin_rules_by == 'group' else self.margin_category_ids
            for rule in rules.filtered(lambda r: r.percent < self.min_margin_percent):
                out.append(_("%(name)s (%(a)s%%) is below the Lowest Margin When Bargaining (%(b)s%%).", name=rule._label(),
                             a='%g' % rule.percent, b='%g' % self.min_margin_percent))
        if 'min_margin_percent' in names and not 0 <= self.min_margin_percent <= 500:
            out.append(_("Lowest margin when bargaining: type 0 to 500 percent."))
        return out

    def action_sa_open_margin(self):
        return self.env['ir.actions.actions']._for_xml_id('sales_automation.action_sa_settings_margin')


class SaGroupRequestMargin(models.Model):
    _inherit = 'sa.group.request'

    def _sa_margin_live(self):
        """The margin by the settings as they are now."""
        self.ensure_one()
        return self._settings()._sa_margin_for(self.product_id.categ_id, self.group_id)

    def _sa_margin(self):
        """The margin of this enquiry: the one its prices were looked at with."""
        self.ensure_one()
        return self.sa_margin_used if self.sa_evaluated_on else self._sa_margin_live()
