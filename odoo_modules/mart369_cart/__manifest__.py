{
    'name': '369 Mart Delivery & Pricing',
    'version': '19.0.1.2.0',
    'category': 'Website',
    'summary': 'The bill, delivery fees, coupons, service areas and slots.',
    'description': """
369 Mart Delivery & Pricing
===========================

Until now the 369 Mart app added up its own basket. The prices were in the
browser's bundle, the delivery fee was a constant next to them, and a coupon's
discount was a line of JavaScript - so the customer's own machine decided what
it would be charged.

This module moves all of that into Odoo, without changing a single screen:

* the bill - items, MRP saving, delivery fees, coupon, total;
* what delivery costs and when it stops costing anything;
* which pincodes are served, and how fast;
* the delivery slots, now with a capacity so two hundred orders cannot all
  choose the same window.

Everything starts out holding the numbers the app has been using, so nothing a
shopper sees changes on the day it is installed. From then on an operator edits
them in **369 Mart -> Delivery & Pricing**.
""",
    'author': '369 Mart',
    'license': 'LGPL-3',
    'depends': [
        'mart369', 'mart369_catalog', 'mart369_address', 'delivery'],
    'data': [
        'security/ir.model.access.csv',
        'data/cart_data.xml',
        'views/pricing_views.xml',
        'views/deal_views.xml',
        # After the views, so the menu exists by the time the examples do.
        'data/deal_cron.xml',
        'data/deal_demo.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'mart369_cart/static/src/deals/**/*',
        ],
    },
    'images': [
        # Deals and coupons first: they are what staff open this module for.
        'static/description/deal_desk.png',
        'static/description/deal_desk_panel.png',
        'static/description/deals.png',
        'static/description/deal_form.png',
        'static/description/delivery_rules.png',
        'static/description/coupons.png',
        'static/description/service_areas.png',
        'static/description/slots.png',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
