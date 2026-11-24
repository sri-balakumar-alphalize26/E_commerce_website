# -*- coding: utf-8 -*-
{
    'name': 'Sales Automation: Purchase for a Vendor Order',
    'version': '19.0.1.0.5',
    'summary': 'An order bought from a vendor makes the purchase, the stock and a draft bill',
    'description': """
Store > Orders > Accept > order it in: the purchase order is made and confirmed.
Goods arrived: they go into stock and are kept for the customer, and a draft bill
is made. Nobody is sent anything. A module of its own, so a database without
Purchase keeps working.
""",
    'author': 'Alphalize',
    'category': 'Sales',
    'depends': ['sales_automation_store', 'purchase_stock'],
    'data': [],
    'installable': True,
    'auto_install': True,
    'application': False,
    'license': 'LGPL-3',
}
