# -*- coding: utf-8 -*-
{
    'name': 'Sales Automation: Store Screen',
    'version': '19.0.9.12.1',
    'summary': 'New paid orders alert the shop, who pack them and call a rider',
    'description': """
Puts the shop between the payment and the rider.

Until now a paid order paged a rider immediately, so a rider could arrive
before anyone had picked the goods off the shelf. This adds the two states
that were missing - the shop accepting an order, and the shop saying it is
packed - and the rider is only called at the second one.

The screen it adds is a working surface rather than a list view: a new order
raises an alarm that keeps sounding until somebody accepts it, which is what
a person with their hands full actually needs.
""",
    'author': 'Alphalize',
    'category': 'Sales',
    'depends': ['sales_automation_delivery', 'bus'],
    'data': [
        'security/sa_notice_security.xml',
        'security/ir.model.access.csv',
        'data/ir_cron.xml',
        'views/store_views.xml',
        'views/sale_order_store_views.xml',
        'views/store_menus.xml',
        'views/sa_notice_settings_views.xml',
        'views/sa_supply_settings_views.xml',
        'views/staff_delivery_templates.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'sales_automation_store/static/src/board.js',
            'sales_automation_store/static/src/board.xml',
            'sales_automation_store/static/src/board.scss',
            'sales_automation_store/static/src/fields.js',
            'sales_automation_store/static/src/fields.xml',
            'sales_automation_store/static/src/fields.scss',
            'sales_automation_store/static/src/chat_log.js',
            'sales_automation_store/static/src/chat_log.xml',
            'sales_automation_store/static/src/chat_log.scss',
            'sales_automation_store/static/src/vendor_cards.js',
            'sales_automation_store/static/src/vendor_cards.xml',
            'sales_automation_store/static/src/vendor_cards.scss',
            'sales_automation_store/static/src/store_screen.js',
            'sales_automation_store/static/src/browser_tz_service.js',
            'sales_automation_store/static/src/store_screen.xml',
            'sales_automation_store/static/src/store_screen.scss',
            'sales_automation_store/static/src/hand_over.js',
            'sales_automation_store/static/src/hand_over.xml',
            'sales_automation_store/static/src/hand_over.scss',
            'sales_automation_store/static/src/notice_shared.js',
            'sales_automation_store/static/src/enquiry_alarm_shared.js',
            'sales_automation_store/static/src/enquiry_screen.js',
            'sales_automation_store/static/src/enquiry_alarm_service.js',
            'sales_automation_store/static/src/enquiry_screen.xml',
            'sales_automation_store/static/src/enquiry_screen.scss',
            'sales_automation_store/static/src/notice_service.js',
            'sales_automation_store/static/src/notice_bell.js',
            'sales_automation_store/static/src/notice_bell.xml',
            'sales_automation_store/static/src/notice_bell.scss',
            'sales_automation_store/static/src/notice_panel.js',
            'sales_automation_store/static/src/notice_panel.xml',
            'sales_automation_store/static/src/notice_panel.scss',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
