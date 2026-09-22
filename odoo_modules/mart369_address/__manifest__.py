{
    'name': '369 Mart Delivery Addresses',
    'version': '19.0.1.2.0',
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

Staff see them in two places: on each customer's profile under
**369 Mart -> Customers**, and all together under **369 Mart -> Addresses**,
where a missing pincode, mobile or map fix is called out in red.
""",
    'author': '369 Mart',
    'license': 'LGPL-3',
    'depends': [
        'mart369','mart369_auth', 'base_geolocalize'],
    'assets': {
        'web.assets_backend': [
            # The desk leans on mart369's builder.scss for the shell, the
            # buttons and the loading line - that module is a dependency, so it
            # is already earlier in the bundle.
            'mart369_address/static/src/desk/**/*',
        ],
    },
    'data': [
        'security/ir.model.access.csv',
        # The desk action first: the menu in address_views.xml points at it,
        # and Odoo resolves an xmlid as it reads, not afterwards.
        'views/address_desk_views.xml',
        'views/address_views.xml',
        'data/address_demo.xml',
    ],
    'images': [
        'static/description/address_desk.png',
        'static/description/customer_addresses.png',
        'static/description/addresses_board.png',
        'static/description/addresses_list.png',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
