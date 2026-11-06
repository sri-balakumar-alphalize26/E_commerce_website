{
    'name': '369 Mart Orders',
    'version': '19.0.1.4.0',
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

Operators work orders in **369 Mart -> Orders**: a queue that answers "what do
I pack next" rather than "show me the orders". It opens on what is still on its
way, longest wait first, and every row carries the button for its own next step
- which differs between a Quick order and an Express one, so the server says
which and what it is called. The same screen the app's admin console shows, off
the same two methods.

The kanban board, the list and the form are still there under **Advanced ->
Orders (all views)**, for the grouping, export and saved filters the queue does
not try to do.
""",
    'author': '369 Mart',
    'license': 'LGPL-3',
    'depends': [
        'mart369',
        'mart369_cart',
        'mart369_payment',
        # Riders are staff with the Rider role; an order is given to one.
        'mart369_roles',
        'stock',
        'account',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/order_data.xml',
        # Cash on delivery and 369 Wallet journals, per company.
        'data/payment_journal_data.xml',
        # The invoice document. The record it draws is an ordinary posted
        # account.move; only the paper is ours.
        'report/invoice_report.xml',
        # Packing slips and the picklist, printed for the ticked orders.
        'report/order_print_report.xml',
        'data/print_paperformat.xml',
        'views/order_views.xml',
        'views/return_views.xml',
        'views/return_desk_views.xml',
        'views/menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'mart369_order/static/src/orders/order_views.scss',
            'mart369_order/static/src/orders/order_board.js',
            'mart369_order/static/src/orders/order_views.js',
            'mart369_order/static/src/orders/order_views.xml',
            # After order_views.scss, which this leans on for the $m369-*
            # tokens - a bundle compiles in the order it is listed.
            'mart369_order/static/src/desk/**/*',
        ],
        'web.assets_tests': [
            'mart369_order/static/tests/tours/**/*',
        ],
    },
    'images': [
        # The desk first: it is what Orders opens on now.
        'static/description/order_desk.png',
        'static/description/order_desk_panel.png',
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
