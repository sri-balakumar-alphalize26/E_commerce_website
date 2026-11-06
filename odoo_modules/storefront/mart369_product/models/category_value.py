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

    def set_value(self, value):
        """Write the wording, or remove the row when it is cleared.

        An empty row is worse than no row. `_value_for` asks
        `if self.id in cat_values` - membership, not truthiness - so a stored
        empty string beats the shop default and blanks the field for every
        product in the category, with nothing on screen saying why. Clearing
        the box has to mean "this category has nothing of its own".
        """
        self.ensure_one()
        value = (value or '').strip()
        if not value:
            self.unlink()
            return False
        self.value = value
        return True
