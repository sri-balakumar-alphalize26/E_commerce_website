{
    'name': '369 Mart Suite',
    'version': '19.0.1.0.0',
    'category': 'Website',
    'summary': 'Installs every 369 Mart module in one go.',
    'description': """
369 Mart Suite
==============

The whole thing, in one install.

369 Mart is a base module plus ten options that each do one job - the home page,
the product page, the catalogue, sign-in, addresses, delivery and pricing,
payments, orders, account and support. Any of them can be installed on its own,
as long as the things it genuinely needs come with it.

This module contains no code. It exists so that somebody who wants all of it can
install one thing rather than ten, and get the order right.

To install only part of the suite, install **369 Mart** and then pick the
options you want from the Apps list.
""",
    'author': '369 Mart',
    'license': 'LGPL-3',
    'depends': [
        'mart369',
        'mart369_home',
        'mart369_product',
        'mart369_catalog',
        'mart369_auth',
        'mart369_address',
        'mart369_cart',
        'mart369_payment',
        'mart369_order',
        'mart369_account',
        'mart369_support',
    ],
    'data': [],
    'installable': True,
    'application': True,
    # Deliberately not auto_install: this arrives because somebody asked for it.
    'auto_install': False,
}
