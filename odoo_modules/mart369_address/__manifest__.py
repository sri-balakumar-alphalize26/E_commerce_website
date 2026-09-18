{
    'name': '369 Mart Delivery Addresses',
    'version': '19.0.1.1.0',
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
    'data': [
        'security/ir.model.access.csv',
        'views/address_views.xml',
    ],
    'images': [
        'static/description/customer_addresses.png',
        'static/description/addresses_board.png',
        'static/description/addresses_list.png',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
