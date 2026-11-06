# -*- coding: utf-8 -*-
from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    qe_delivery_text = fields.Char(
        'Delivery text',
        help="This product's own delivery promise, e.g. Delivered in 5-7 "
             "days. A product with a delivery text is always Express.")
