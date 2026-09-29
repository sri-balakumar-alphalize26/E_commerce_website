{
    'name': '369 Mart: New Orders Board',
    'version': '19.0.1.1.0',
    'category': 'Website',
    'summary': "369 Mart › Sales › Orders opens on the shop counter: Counter ⇄ All orders",
    'description': """
369 Mart › Sales › Orders: one entry, opening on the Counter - the Store's
counter screen (sales_automation_store) with New, Quick and Express tabs - and a
toggle at the top to All orders (mart369_order's desk) and back.

New orders ring until somebody presses Accept; each card lists what was
ordered, and Accept -> Packed calls the rider - all the Store's own screen,
inherited rather than copied, so the Store app's screen is unchanged.

A screen, not a connection: it lives here rather than in
mart369_whatsapp_bridge, which only joins the two stacks' data. With the
bridge installed each card also says which door the order came in by
(Website / WhatsApp); without it the page still works for every order.
""",
    'author': 'Alphalize',
    'license': 'LGPL-3',
    'depends': [
        'mart369_order',
        'sales_automation_store',
    ],
    'data': [
        'views/orders_board_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'mart369_store_board/static/src/**/*',
        ],
    },
    'uninstall_hook': 'uninstall_hook',
    'installable': True,
    'application': False,
}
