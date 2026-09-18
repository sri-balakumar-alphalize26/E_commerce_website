{
    'name': '369 Mart Orders',
    'version': '19.0.1.0.0',
    'category': 'Website',
    'summary': 'Real orders behind the app - placed, packed, delivered, returned.',
    'description': """
369 Mart Orders
===============

The module the rest of the backend has been waiting for.

Until now an order existed only in the browser. The app invented its own order
number, kept the order in `localStorage`, and moved it from *placed* to
*delivered* on a timer so the screens could be demonstrated. Payment had
nowhere to attach: `mart369_payment` shipped with three named seams that return
nothing, because there was no order to move.

This module makes the order a real `sale.order`:

* placed, packed, shipped, out for delivery, delivered, cancelled - stamped, so
  the timeline survives a reload and the demo clock can go;
* the money is decided here, not in the browser - the payment a customer is
  asked for is read off the order;
* the delivery code is issued by the server, once, instead of being computed
  from the order number;
* slots are really booked, coupons are really spent, and the invoice is a real
  document;
* cancellations and returns, with the refund going back the way it came.

Operators work orders in **369 Mart -> Orders**, on a board that moves an order
on in one click.
""",
    'author': '369 Mart',
    'license': 'LGPL-3',
    'depends': [
        'mart369_cart',
        'mart369_payment',
        'stock',
        'account',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/order_data.xml',
        'views/order_views.xml',
        'views/return_views.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'mart369_order/static/src/orders/order_views.scss',
            'mart369_order/static/src/orders/order_board.js',
            'mart369_order/static/src/orders/order_views.js',
            'mart369_order/static/src/orders/order_views.xml',
        ],
    },
    'images': [
        'static/description/orders_board.png',
        'static/description/orders_list.png',
        'static/description/order_form.png',
        'static/description/order_timeline.png',
        'static/description/returns_board.png',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
