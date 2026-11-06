# -*- coding: utf-8 -*-
{
    'name': 'WhatsApp Sales Automation - Quick or Express',
    'version': '19.0.1.0.2',
    'summary': 'Decide Quick or Express from shop reach, stock and pincode area; fees and slots',
    'description': """
Quick or Express
================

`sales_automation_delivery` sorts a delivery into Quick or Express from one
fact: is every line on the shelf at the order's warehouse. It never asks how
far away the customer is.

This module replaces that question with the 369 Mart rule:

1. the product has its own delivery text - Express;
2. a shop that does Quick, within its reach of the customer's map pin, has
   the goods - Quick, from that shop;
3. otherwise the customer's pincode area decides;
4. no area matches - Quick.

It also carries the delivery fee rules (minimum order, fee, free above) and
the delivery slots (order-before time, extra fee, capacity).

The result is written onto the sale order and, at confirmation, onto the
delivery job, so the order lands in Store > Quick Delivery or
Store > Express Delivery with a promised time that matches.
""",
    'author': 'Alphalize Technologies',
    'category': 'Sales/Sales',
    'license': 'LGPL-3',
    # `sales_automation_store` for the Store menu the screens sit under; it
    # brings `sales_automation_delivery` (the job, the shops, the promise).
    'depends': ['sales_automation_store', 'sale_stock'],
    'data': [
        'security/ir.model.access.csv',
        'data/qe_data.xml',
        'views/qe_rule_views.xml',
        'views/sa_delivery_shop_views.xml',
        'views/sa_delivery_settings_views.xml',
        'views/product_views.xml',
        'views/sale_order_views.xml',
        'views/qe_menus.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
