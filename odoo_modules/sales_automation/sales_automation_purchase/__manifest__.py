# -*- coding: utf-8 -*-
{
    'name': 'Sales Automation - Vendor Orders',
    'version': '19.0.1.0.0',
    'category': 'Sales',
    'summary': 'What a paid order still needs from a vendor, with every price received (to look at only)',
    'description': """
When a WhatsApp group order is paid, each item the shop does not have becomes a
"buy line": what was paid, who was asked, what each vendor said, and what the
shop would earn. Store > Vendor Orders shows them.

This version only shows. It orders nothing, sends nothing and changes no stock,
price, enquiry or order. Purchase Orders come in a later version, and the
Purchase app becomes a dependency only then.
""",
    'author': 'Alphalize',
    'license': 'LGPL-3',
    'depends': ['sales_automation_confirm'],
    'data': [
        'security/sales_automation_purchase_security.xml',
        'security/ir.model.access.csv',
        'data/ir_cron.xml',
        'views/sa_settings_vendor_orders_views.xml',
        'views/vendor_orders_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'sales_automation_purchase/static/src/vendor_orders.js',
            'sales_automation_purchase/static/src/vendor_orders.xml',
            'sales_automation_purchase/static/src/vendor_orders.scss',
        ],
    },
    'installable': True,
    'application': False,
}
