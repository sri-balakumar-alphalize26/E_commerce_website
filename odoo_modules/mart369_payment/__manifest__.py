{
    'name': '369 Mart Payments & Wallet',
    'version': '19.0.1.0.0',
    'category': 'Website',
    'summary': "Real payments, saved cards and UPI IDs, and the 369 Wallet.",
    'description': """
369 Mart Payments & Wallet
==========================

The storefront's payment screen is a demo: it makes up its own transaction ids,
succeeds without reading what it was given, and writes "paid" before any money
has moved. This module replaces it with Odoo's own payment framework, so a
payment is marked paid by the provider's webhook after a signature check and
never by the browser.

It also gives the **369 Wallet** one balance and one ledger that cannot drift
apart, and keeps saved cards and UPI IDs as real ``payment.token`` records - so
no card number is ever held in the browser.

Staff see every payment and every wallet under **369 Mart -> Payments** and
**369 Mart -> Wallets**, in the same look as the Customers screen.
""",
    'author': '369 Mart',
    'license': 'LGPL-3',
    'depends': [
        'mart369',
        'mart369_auth',
        'sale',
        'payment',
        'payment_custom',
        # Ships cash on delivery whole - method, provider, and the rule that
        # refuses cash unless the carrier allows it. We only set the limit.
        'delivery',
        'loyalty',
        'sale_loyalty',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/payment_method_data.xml',
        'data/payment_provider_data.xml',
        'data/loyalty_program_data.xml',
        'data/payment_params.xml',
        'data/payment_cleanup.xml',
        'views/payment_transaction_views.xml',
        'views/loyalty_card_views.xml',
        'views/desk_views.xml',
        'views/menus.xml',
        # Seeds once and guards itself - see the file's own comment.
        'data/wallet_demo.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'mart369_payment/static/src/payments/payment_dashboard.js',
            'mart369_payment/static/src/payments/payment_views.js',
            'mart369_payment/static/src/payments/payment_views.xml',
            # The two desks. After the strip above, which they do not use but
            # which defines the shared look a bundle compiles in order.
            'mart369_payment/static/src/desk/**/*',
        ],
    },
    'images': [
        # The two desks, and the movements behind one wallet.
        'static/description/payment_desk.png',
        'static/description/wallet_desk.png',
        'static/description/wallet_desk_ledger.png',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
