from odoo import fields, models


class Mart369ProductSection(models.Model):
    """One band of the product page in the app.

    Switching a section off hides it and everything in it, for every product
    at once. Individual fields inside it are switched separately.
    """

    _name = 'mart369.product.section'
    _description = '369 Mart Product Page Section'
    _order = 'sequence, id'

    key = fields.Char(
        string='Key', required=True,
        help='The internal name the app uses, e.g. info. Leave it alone once '
             'the app is live.')
    name = fields.Char(
        string='Section', required=True, translate=True,
        help='What this part of the page is called, e.g. Product information.')
    sequence = fields.Integer(default=10)
    show = fields.Boolean(
        string='Show in the app', default=True,
        help='Off: this whole section disappears from every product page, '
             'whatever the individual fields say.')
    note = fields.Char(
        string='What it is', translate=True,
        help='A short reminder for whoever is editing.')
    field_ids = fields.One2many(
        'mart369.product.field', 'section_id', string='Fields')
    field_count = fields.Integer(
        string='Fields shown', compute='_compute_field_count')
    active = fields.Boolean(default=True)

    _key_uniq = models.Constraint('unique (key)', 'Two sections cannot share a key.')

    def _compute_field_count(self):
        for rec in self:
            rec.field_count = len(rec.field_ids.filtered('show'))

    def action_toggle_show(self):
        for rec in self:
            rec.show = not rec.show
        return True
