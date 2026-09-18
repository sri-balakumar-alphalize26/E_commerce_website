{
    'name': '369 Mart Account',
    'version': '19.0.1.0.0',
    'category': 'Website',
    'summary': "The customer's own things - profile, reviews, notifications, "
               "referrals, wishlist and rewards.",
    'description': """
369 Mart Account
================

Everything on the app's account page was the browser's own. The profile edit
was thrown away the moment the page reloaded - `onSave` set React state and
nothing else, after the screen had already said "Saved". Reviews, notifications,
referrals, the wishlist and the scratch cards were seed data in the bundle,
identical for every customer and gone with the browser's storage.

This module gives each of them a record:

* **Profile** - a name, email and mobile that survive a reload;
* **Reviews** - real `rating.rating` on the product, with a verified-purchase
  check against what the customer actually bought;
* **Notifications** - built from the customer's real orders, with what they have
  read remembered;
* **Referrals** - a code that is unique and stays the same, and invites that
  really move from invited to joined to ordered;
* **Wishlist** - Odoo's own `product.wishlist`;
* **Rewards** - scratch cards that orders really mint, paying into the 369
  Wallet when they are scratched.

Operators work these in **369 Mart -> Reviews**, **Referrals** and **Rewards**.
""",
    'author': '369 Mart',
    'license': 'LGPL-3',
    'depends': [
        'mart369_order',
        'rating',
        'website_sale_wishlist',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/account_data.xml',
        'views/review_views.xml',
        'views/referral_views.xml',
        'views/scratch_views.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'mart369_account/static/src/account/account_views.scss',
            'mart369_account/static/src/account/account_board.js',
            'mart369_account/static/src/account/account_views.js',
            'mart369_account/static/src/account/account_views.xml',
        ],
    },
    'images': [
        'static/description/reviews_board.png',
        'static/description/referrals_board.png',
        'static/description/rewards_board.png',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
