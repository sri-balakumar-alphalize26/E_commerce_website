{
    'name': '369 Mart',
    'version': '19.0.1.0.0',
    'category': 'Website',
    'summary': 'Installs the whole 369 Mart backend in one go.',
    'description': """
369 Mart
========

The whole thing, in one install.

369 Mart is ten modules that build on each other: the home page needs the
product page, the cart needs the catalogue and the address book, orders need
the cart and payments, and the account and support screens need orders. Picking
them out of the Apps list one at a time works, but only if you happen to know
that order.

This module contains no code of its own. It exists so that installing **369
Mart** installs the other ten and gets the order right, and so that the suite
has one obvious thing to look for.

What comes with it:

* **Home page** - banners, sections and tiles, editable without code
* **Product page** - what each product page shows, field by field
* **Catalog** - categories, browsing and search
* **Sign in** - customers create their own accounts
* **Delivery addresses** - found from the customer's live location
* **Delivery & pricing** - the bill, fees, coupons, service areas and slots
* **Payments & wallet** - real payments, saved methods, the 369 Wallet
* **Orders** - placed, packed, delivered, returned, invoiced
* **Account** - profile, reviews, notifications, referrals, wishlist, rewards
* **Support** - the bot, real tickets, and order updates on WhatsApp

Removing this module does **not** remove the ten. Uninstall those individually
if that is what you want.
""",
    'author': '369 Mart',
    'license': 'LGPL-3',
    # Every module by name rather than just the two leaves. The leaves alone
    # would pull the rest in, but then this list would quietly stop describing
    # the suite the moment somebody changed a dependency in the middle of it.
    'depends': [
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
    # Shows up as an app in the Apps list, which is where somebody looking for
    # "369 Mart" will actually look.
    'application': True,
    # Deliberately NOT auto_install: this should arrive because somebody asked
    # for it, not because its dependencies happened to line up.
    'auto_install': False,
}
