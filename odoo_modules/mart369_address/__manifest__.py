{
    'name': '369 Mart Delivery Addresses',
    'version': '19.0.1.0.0',
    'category': 'Website',
    'summary': "Customers' delivery addresses, found from their live location.",
    'description': """
369 Mart Delivery Addresses
===========================

Every 369 Mart customer can keep several delivery addresses. The app asks for
the phone's location, turns it into an area, city, state and pincode, and the
customer fills in the rest - flat, name, mobile, and whether it is Home or Work.

An address is an ordinary Odoo delivery contact under the customer, so sale
orders, delivery and invoicing all understand it.

Staff get **369 Mart -> Customers & Addresses**: one colour-coded screen that
shows every customer, their addresses, and what is missing.
""",
    'author': '369 Mart',
    'license': 'LGPL-3',
    'depends': ['mart369_auth', 'base_geolocalize'],
    'data': [
        'security/ir.model.access.csv',
        'views/address_views.xml',
        'views/console_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'mart369_address/static/src/console/console.scss',
            'mart369_address/static/src/console/console.js',
            'mart369_address/static/src/console/console.xml',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
