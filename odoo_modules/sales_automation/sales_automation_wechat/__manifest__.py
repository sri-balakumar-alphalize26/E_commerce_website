# -*- coding: utf-8 -*-
{
    'name': 'Sales Automation - WeChat Vendors',
    'version': '19.0.1.7.5',
    'category': 'Sales',
    'summary': 'Price checks to vendors on WeChat through a bridge PC that polls 369ai over the public URL',
    'description': """
Some vendors are only on personal WeChat. A small bridge program on a Windows PC
(WeChat for Windows 3.9.x, dedicated shop account) polls this server for
price checks, sends them in WeChat, and posts the replies back. 369ai never
calls the PC: the PC calls 369ai, over the public tunnel URL, with an API key.
Replies become vendor quotes exactly like WhatsApp replies; the cheapest wins.
When the bridge is down, the counter screen shows the messages to relay by hand.
""",
    'author': 'Alphalize',
    'license': 'LGPL-3',
    'depends': ['sales_automation_store'],
    'data': [
        'security/ir.model.access.csv',
        'views/sa_wechat_message_views.xml',
        'views/res_partner_views.xml',
        'views/sa_settings_wechat_views.xml',
        'views/sa_connections_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'sales_automation_wechat/static/src/wechat_relay.js',
            'sales_automation_wechat/static/src/wechat_relay.xml',
            'sales_automation_wechat/static/src/wechat_relay.scss',
        ],
    },
    'installable': True,
    'application': False,
}
