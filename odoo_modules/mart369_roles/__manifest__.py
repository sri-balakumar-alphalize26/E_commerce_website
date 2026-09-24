{
    'name': '369 Mart Roles',
    'version': '19.0.1.1.0',
    'category': 'Website',
    'summary': 'Owner, Manager, Packer, Accountant, Rider and Seller roles on the user form.',
    'description': """
369 Mart Roles
==============

Adds a **369 Mart** section to Settings > Users & Companies > Users, where each
person is given a role:

* **369 Mart**: Packer, Manager or Owner (each includes the one before)
* **369 Mart Accounts**: Accountant
* **369 Mart Delivery**: Rider
* **369 Mart Seller**: Seller (a portal login, for outside sellers)

Which shop someone works in - 369 Mart or a seller's branch/company - is Odoo's
own Allowed Companies field on the same form. Role says *what*, companies say
*where*.

Standalone: nothing else in the suite depends on this module yet. On install,
the administrator becomes Owner and anyone who already had the website
designer right (today's staff check) becomes Manager, so nobody loses access.
""",
    'author': '369 Mart',
    'license': 'LGPL-3',
    'depends': ['mart369', 'mart369_auth', 'website'],
    'data': [
        'security/roles.xml',
        'views/res_users_views.xml',
        'views/staff_desk_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'mart369_roles/static/src/**/*',
        ],
    },
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
    'auto_install': False,
}
