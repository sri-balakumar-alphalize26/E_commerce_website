{
    'name': '369 Mart: WhatsApp Bridge',
    'version': '19.0.1.0.0',
    'category': 'Website',
    'summary': 'One shop across the website and the WhatsApp selling flow',
    'description': """
The website (mart369_*) and the WhatsApp selling flow (sales_automation_*)
each run a whole shop on their own. This module is the only place the two
meet - neither stack is edited, and uninstalling it separates them again.

What it does:

* every order carries a channel (website / WhatsApp), and the console's
  orders board shows both;
* moving an order on the console drives the real WhatsApp delivery job, and
  a rider or shop moving the job moves the console order;
* website customers who opted in get real WhatsApp updates, sent through the
  gateway session, with the wording and switches on the console's Settings;
* website orders become rider-app jobs with the right delivery kind, the
  right cash to collect, and the website's own door code;
* the WhatsApp menu sells the storefront's published catalogue at the
  storefront's price (bargaining still applies on top);
* a WhatsApp customer with a store account is the same res.partner.
""",
    'author': 'Alphalize',
    'license': 'LGPL-3',
    'depends': [
        'mart369_order',
        'mart369_support',
        'mart369_address',
        'mart369_auth',
        'mart369_catalog',
        # The product's own "Sell when Out-of-Stock" (models/stock_rule.py).
        'website_sale_stock',
        'sales_automation_store',
        'sales_automation_confirm',
    ],
    'data': [
        'views/sale_order_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'mart369_whatsapp_bridge/static/src/**/*',
        ],
    },
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
    'installable': True,
    'application': False,
}
