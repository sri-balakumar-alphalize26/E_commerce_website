{
    'name': '369 Mart Sign In',
    'version': '19.0.1.1.0',
    'category': 'Website',
    'summary': 'Customers create their own 369 Mart account and sign in with their name or email.',
    'description': """
369 Mart Sign In
================

Anyone can create an account on the 369 Mart storefront with a full name,
an email and a password, then sign in with either the name or the email.

Every account made this way is a *portal* user: it can see its own orders,
addresses and details, and nothing else. It cannot open the Odoo backend.

The storefront talks to ``/369mart/auth/*`` (JSON). Operators see who has
signed up under **369 Mart -> Customers**: a numbers strip, a list, a board
grouped by status (New / Active / Dormant) and a full profile per customer.
""",
    'author': '369 Mart',
    'license': 'LGPL-3',
    'depends': [
        'mart369','auth_signup', 'website_sale', 'phone_validation'],
    'data': [
        'security/ir.model.access.csv',
        'data/auth_settings.xml',
        'data/ir_cron.xml',
        'views/customer_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'mart369_auth/static/src/customers/customer_views.scss',
            'mart369_auth/static/src/customers/customer_dashboard.js',
            'mart369_auth/static/src/customers/customer_views.js',
            'mart369_auth/static/src/customers/customer_views.xml',
        ],
    },
    'images': [
        'static/description/customers_list.png',
        'static/description/customers_board.png',
        'static/description/customer_profile.png',
        'static/description/customer_password.png',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
