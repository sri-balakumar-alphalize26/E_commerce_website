# -*- coding: utf-8 -*-
{
    'name': 'Sales Automation - Product Confirmation Page',
    'version': '19.0.2.21.2',
    'category': 'Sales',
    'summary': 'Picture + details page with ACCEPT / REJECT for customers and vendors (WhatsApp and WeChat), with a click log',
    'description': """
When a product is identified for a customer, or a vendor is asked for a price,
they get the product picture and a private link. The link opens one page with
the picture(s), every property in a table and two buttons: ACCEPT / REJECT.
The page is the confirmation: the first press is final and the buttons are
disabled afterwards. The pictures are the product's own, up to 13; nothing is
searched for on the internet. Every open and every press is logged with who,
which account, when, from which address.
""",
    'author': 'Alphalize',
    'license': 'LGPL-3',
    'depends': ['sales_automation_wechat', 'sales_automation_insights'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron.xml',
        'views/sa_confirm_link_views.xml',
        'views/sa_settings_confirm_views.xml',
        'views/sa_group_request_views.xml',
        'views/product_variant_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'sales_automation_confirm/static/src/confirm_desk.xml',
        ],
    },
    'installable': True,
    'application': False,
}
