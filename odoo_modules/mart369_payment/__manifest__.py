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
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
