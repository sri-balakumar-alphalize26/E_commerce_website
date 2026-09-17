{
    'name': '369 Mart Sign In',
    'version': '19.0.1.0.0',
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
signed up under **369 Mart -> Customers**.
""",
    'author': '369 Mart',
    'license': 'LGPL-3',
    'depends': ['auth_signup', 'website_sale', 'phone_validation', 'mart369_home'],
    'data': [
        'security/ir.model.access.csv',
        'data/auth_settings.xml',
        'views/customer_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
