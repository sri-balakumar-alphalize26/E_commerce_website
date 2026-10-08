"""The labels a product of this Odoo category usually lists under Product
details - Processor, RAM, Storage for a laptop - typed once per category.
Empty: the shop's built-in list for the category's name (MART_DETAIL_TEMPLATES
on product.template)."""

from odoo import fields, models


class ProductCategoryDetails(models.Model):
    _inherit = 'product.category'

    mart_detail_labels = fields.Text(
        string='Usual product details',
        help='One label per line, e.g. Processor, RAM, Storage. The 369 Mart '
             'editor\'s "Add the usual details" button adds these to a product '
             'of this category, ready to fill. Empty: a built-in list chosen '
             'from the category\'s name.')
