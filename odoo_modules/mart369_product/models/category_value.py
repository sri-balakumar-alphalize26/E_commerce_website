from odoo import fields, models


class Mart369ProductCategoryValue(models.Model):
    """What a field says for one shop category.

    Fresh fruit and headphones genuinely differ - "Shelf life: 3-5 days,
    refrigerated" against "Warranty: 1 year" - so a category can set a value
    once instead of it being typed on two hundred products. A product can
    still override its category.
    """

    _name = 'mart369.product.category.value'
    _description = '369 Mart Product Field by Category'
    _order = 'public_categ_id, field_id'
    _rec_name = 'field_id'

    public_categ_id = fields.Many2one(
        'product.public.category', string='Category',
        required=True, ondelete='cascade', index=True)
    field_id = fields.Many2one(
        'mart369.product.field', string='Field',
        required=True, ondelete='cascade', index=True)
    value = fields.Text(
        string='Value for this category',
        help='Used for every product in this category, unless the product '
             'itself says otherwise.')
    section_id = fields.Many2one(
        related='field_id.section_id', string='Section', store=True)

    _categ_field_uniq = models.Constraint(
        'unique (public_categ_id, field_id)',
        'That field is already set for this category.')
