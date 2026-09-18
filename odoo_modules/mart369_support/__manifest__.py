{
    'name': '369 Mart Support',
    'version': '19.0.1.0.0',
    'category': 'Website',
    'summary': 'The support bot, real tickets, and order updates on WhatsApp.',
    'description': """
369 Mart Support
================

The app had two support bots with the same name and different answers. One lived
in `botReplies.js` and one was written inline on the order tracking page, so
"Mitra" told a customer their order was "being packed" on one screen and "being
prepared" on the other, quoted a two-minute wait for an agent in one place and
thirty minutes in the other, and recited delivery fees and coupon codes that had
already drifted from the ones the cart actually charges.

Asking for a human did nothing at all. The bot said *"I've noted this against
your order and will update you within 30 minutes"*, created no record, and
notified nobody - and the whole conversation was kept in `sessionStorage`, so it
was gone when the tab closed.

This module gives support one brain and a memory:

* one set of answers, edited in Odoo rather than in a bundle, so both screens
  say the same thing;
* delivery charges, minimums and coupon codes **read from the real ones**
  instead of being retyped;
* asking for an agent opens a **real ticket** with the conversation on it, so
  the promise the bot makes is one somebody can keep;
* order updates on WhatsApp, when a WhatsApp gateway is installed.

Operators work these in **369 Mart -> Support**.
""",
    'author': '369 Mart',
    'license': 'LGPL-3',
    # No im_livechat and no helpdesk: helpdesk is not available here, and the
    # ticket below does the job without it. WhatsApp is found at runtime rather
    # than depended on - see models/whatsapp.py for why.
    'depends': [
        'mart369',
        'mart369_order',
        'mail',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/bot_rules.xml',
        'views/ticket_views.xml',
        'views/rule_views.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'mart369_support/static/src/support/support_board.js',
            'mart369_support/static/src/support/support_views.js',
            'mart369_support/static/src/support/support_views.xml',
        ],
    },
    'images': [
        'static/description/tickets_board.png',
        'static/description/ticket_form.png',
        'static/description/rules_list.png',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
