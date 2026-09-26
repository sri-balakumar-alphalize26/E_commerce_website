{
    'name': '369 Mart Loyalty Points',
    'version': '19.0.1.1.0',
    'category': 'Website',
    'summary': "Loyalty points earned on 369 Mart and Sales orders, and spent at checkout.",
    'description': """
369 Mart Loyalty Points
=======================

`pos_loyalty_card` keeps one loyalty card per customer, keyed by their mobile
number, and a points rule: spend so much, earn so many; so many points take a
rupee off. It started life inside Point of Sale; the shop sells online and
from Odoo's Sales instead, so the card no longer needs Point of Sale and this
module does the earning and spending on `sale.order`:

* **Earning** at the step staff choose in Settings -> Loyalty: placed, packed,
  out for delivery, delivered, or once the return window has closed. App
  orders follow their own steps; an order made in Odoo's Sales earns when it
  is confirmed, or when its delivery is done, by the same setting.
* **Redeeming** at the app's checkout, as a discount line on the bill - the
  same way a coupon is - within the rule's minimum, its points-per-rupee and
  its maximum share of the order, and once a day.
* **Giving back**: a cancellation, a return, an item taken out or a credit
  note takes back the points the order earned; points it spent come back when
  the order is cancelled or refunded in full.
* **A card on the first order**, found by the customer's mobile number when
  they already have one, and made silently when they do not.
* **The screens under 369 Mart**: Loyalty (cards, history, rules, settings)
  and WhatsApp, in place of the card's own app.
""",
    'author': '369 Mart',
    'license': 'LGPL-3',
    'depends': [
        'mart369_order',
        'mart369_auth',
        'pos_loyalty_card',
        # A staff order earns when its delivery is done: picking -> sale order.
        'sale_stock',
    ],
    'data': [
        'security/roles.xml',
        'data/loyalty_data.xml',
        'views/history_views.xml',
        'views/menus.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
