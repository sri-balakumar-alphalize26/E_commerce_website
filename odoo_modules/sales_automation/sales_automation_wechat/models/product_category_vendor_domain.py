# -*- coding: utf-8 -*-
from odoo import fields, models


class ProductCategory(models.Model):
    """A contact ticked for WhatsApp or WeChat is a vendor here, whether or not
    a purchase order was ever made for it. The base list only offered contacts
    with a supplier rank, and a vendor typed in Contacts starts at zero - the
    owner added one and could not find it on the category (26 Sep 2026)."""
    _inherit = 'product.category'

    sa_vendor_ids = fields.Many2many(
        'res.partner', 'sa_product_category_vendor_rel', 'category_id', 'partner_id',
        string='Vendors',
        domain="['|', '|', ('supplier_rank', '>', 0), ('sa_via_whatsapp', '=', True), ('sa_via_wechat', '=', True)]",
        help="Suppliers asked to quote for products in this category: any contact "
             "with a purchase history, or with the WhatsApp / WeChat tick.")
