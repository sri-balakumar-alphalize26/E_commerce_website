# -*- coding: utf-8 -*-
{
    'name': 'WhatsApp Sales Automation - Delivery',
    'version': '19.0.29.0.5',
    'summary': 'Dispatch confirmed WhatsApp orders to riders and couriers',
    'description': """
Delivery dispatch for WhatsApp orders
=====================================

`sales_automation` takes a WhatsApp group enquiry to a confirmed sale order and
an invoice, then stops. Nobody is told to carry the parcel.

This module adds the last step. When an order is confirmed it picks the shop
nearest the customer, picks who should carry it, and sends the job to that
person on WhatsApp with a link they tap to accept. The rider needs no app
install and no 369ai login: the link opens a page with the address, what to
collect, and three buttons - Accepted, Picked up, Delivered.

The delivery *is* the outgoing `stock.picking` 369ai already creates when the
order is confirmed, so there is one state, not two, and marking it delivered
moves the stock.
""",
    'author': 'Alphalize Technologies',
    'category': 'Sales/Sales',
    'license': 'LGPL-3',
    # `stock` for the picking that is the delivery job, `sales_automation` for
    # the WhatsApp session, the outbox guard and the address-word matching.
    'depends': ['sales_automation', 'stock'],
    'data': [
        'security/sales_automation_delivery_security.xml',
        'security/ir.model.access.csv',
        'views/sa_delivery_shop_views.xml',
        'views/sa_delivery_partner_views.xml',
        'views/stock_picking_delivery_views.xml',
        'views/sa_delivery_otp_views.xml',
        'report/sa_delivery_report_views.xml',
        'views/delivery_job_templates.xml',
        'views/delivery_track_templates.xml',
        'views/menu.xml',
        'views/fleet_map_views.xml',
        'views/sa_app_reports_views.xml',
        'views/sa_delivery_otp_wizard_views.xml',
        'data/sa_dispatch_cron.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'sales_automation_delivery/static/src/fleet_map.js',
            'sales_automation_delivery/static/src/fleet_map.xml',
            'sales_automation_delivery/static/src/fleet_map.scss',
            'sales_automation_delivery/static/src/photo_lightbox.js',
            'sales_automation_delivery/static/src/photo_lightbox.scss',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
}
