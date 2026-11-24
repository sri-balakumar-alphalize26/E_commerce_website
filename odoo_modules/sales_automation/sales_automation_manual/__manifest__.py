# -*- coding: utf-8 -*-
{
    'name': 'Sales Automation - User Manual',
    'version': '19.0.1.3.0',
    'category': 'Sales',
    'summary': 'The full user manual of the WhatsApp sales automation, reachable from every module menu',
    'description': """
Adds a "User Manual" entry under Sales Automation, Store, Delivery and Insights.
Each one opens the manual at the chapter of that module; the PDF can be
downloaded from the page. Installing this module installs the stack
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
    'installable': True,
    'application': False,
}
