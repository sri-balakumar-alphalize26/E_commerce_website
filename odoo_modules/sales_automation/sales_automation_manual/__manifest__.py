# -*- coding: utf-8 -*-
{
    'name': 'Sales Automation - User Manual',
    'version': '19.0.1.6.0',
    'category': 'Sales',
    'summary': 'The full user manual of the WhatsApp sales automation, reachable from every module menu',
    'description': """
Adds ONE "Help" at the end of the menu of Sales Automation, Store, Delivery and
Insights (1.4.0, 27 Nov 2026). It opens a pop-up with "User Manual" (the app's own
manual, or the Full manual of all 4 apps, as PDF) and "How It Works" (the app's
step guide with pictures and a video). Installing this module installs the stack
(gateway, sales automation, store, delivery, insights, WeChat, confirmation
page) through its dependencies. Loyalty on WhatsApp is separate: install
sales_automation_loyalty only where points should be offered in the chat.
""",
    'author': 'Alphalize',
    'license': 'LGPL-3',
    'depends': ['sales_automation_confirm'],
    'data': [
        'views/manual_menus.xml',
    ],
    # 1.6.0 (27 Nov 2026): its own Help pop-up and video player, so Help works with any whatsapp_gateway version
    'assets': {
        'web.assets_backend': [
            'sales_automation_manual/static/src/help_dialog/help_dialog.js',
            'sales_automation_manual/static/src/help_dialog/help_dialog.xml',
            'sales_automation_manual/static/src/help_dialog/help_dialog.scss',
        ],
    },
    'installable': True,
    'application': False,
}
