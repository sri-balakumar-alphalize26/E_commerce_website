"""Fixtures for the order tests.

A basket that can really be ordered needs more standing behind it than it looks:
published products with prices, a delivery rule per storefront so the bill knows
what postage costs, a customer with an address, and a gateway that can take
money. All of that is built here so the tests themselves read as the thing they
are checking.

The payment fixtures are mart369_payment's own - reused rather than rebuilt,
which is what its `common.py` docstring asked for when this module landed.
"""

from odoo.tests import HttpCase, TransactionCase

from odoo.addons.mart369_payment.tests.common import Mart369PaymentFixtures


class Mart369OrderFixtures(Mart369PaymentFixtures):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.gateway = cls._mart369_gateway()
        cls.method = cls.env.ref('payment.payment_method_upi')

        # A customer, with a login, because every order route is auth='user'.
        cls.customer = cls.env['res.users'].sudo().create({
            'name': 'Order Tester',
            'login': 'order.tester@369mart.test',
            'password': 'order-tester-369',
            'email': 'order.tester@369mart.test',
        })
        cls.partner = cls.customer.partner_id
        cls.address = cls.env['res.partner'].sudo().create({
            'name': 'Order Tester',
            'parent_id': cls.partner.id,
            'type': 'other',
            'street': '3 Test Street',
            'city': 'Dindigul',
            'zip': '624003',
            'phone': '+91 98765 43210',
        })

        # Somebody else, to prove ownership is really checked.
        cls.other = cls.env['res.users'].sudo().create({
            'name': 'Someone Else',
            'login': 'someone.else@369mart.test',
            'password': 'someone-else-369',
            'email': 'someone.else@369mart.test',
        })

        # Two products: one Quick (no delivery promise), one Express.
        cls.quick_product = cls._mart369_product('Test Bananas', 50.0)
        cls.express_product = cls._mart369_product(
            'Test Headphones', 1200.0, delivery='Delivery in 2-3 days')

        cls._mart369_rules()

    @classmethod
    def _mart369_product(cls, name, price, delivery=None):
        values = {
            'name': name,
            'list_price': price,
            'is_published': True,
            'sale_ok': True,
            'type': 'consu',
        }
        if delivery:
            values['mart_delivery_text'] = delivery
        return cls.env['product.template'].sudo().create(values)

    @classmethod
    def _mart369_rules(cls):
        """The two delivery rules, holding the numbers the app shipped with."""
        Rule = cls.env['mart369.delivery.rule'].sudo()
        for mode, values in (
            ('quick', {'label': 'Quick', 'eta': 'Delivery in 13 mins',
                       'min_order': 99.0, 'free_above': 499.0, 'fee': 30.0}),
            ('all', {'label': 'Express', 'eta': 'Delivery in 2-3 days',
                     'min_order': 0.0, 'free_above': 999.0, 'fee': 49.0}),
        ):
            rule = Rule.search([('mode', '=', mode)], limit=1)
            if rule:
                rule.write(values)
            else:
                Rule.create(dict(values, mode=mode))

    # ------------------------------------------------------------------ acting

    def _basket(self, **overrides):
        """A basket the cart page would have let through."""
        body = {
            'ref': '369M-TEST1',
            'items': {str(self.quick_product.id): 4},
            'address_id': self.address.id,
            'mode': 'quick',
            'slot': 'Today, 6 - 8 PM',
        }
        body.update(overrides)
        return body

    def _place(self, **overrides):
        return self.env['sale.order']._mart369_place(self.partner, self._basket(**overrides))

    def _pay(self, order, amount=None, wallet_used=0.0):
        """A completed gateway payment for an order, the way /pay makes one."""
        tx = self.env['payment.transaction'].sudo().create({
            'provider_id': self.gateway.id,
            'payment_method_id': self.method.id,
            'partner_id': self.partner.id,
            'amount': amount if amount is not None else order.amount_total,
            'currency_id': order.currency_id.id,
            'operation': 'online_direct',
            'mart369_kind': 'order',
            'mart369_order_ref': order.mart369_ref,
            'mart369_wallet_used': wallet_used,
        })
        tx._set_done()
        tx._post_process()
        return tx

    def _cash(self, order):
        """A cash-on-delivery payment the way /pay makes one: pending until
        the door."""
        cod = self.env.ref('delivery.payment_provider_cod').sudo()
        cod.write({'state': 'test'})
        tx = self.env['payment.transaction'].sudo().create({
            'provider_id': cod.id,
            'payment_method_id': cod.payment_method_ids[:1].id,
            'partner_id': self.partner.id,
            'amount': order.amount_total,
            'currency_id': order.currency_id.id,
            'operation': 'online_direct',
            'mart369_kind': 'order',
            'mart369_order_ref': order.mart369_ref,
        })
        tx._set_pending()
        tx._post_process()
        return tx


class Mart369OrderCase(Mart369OrderFixtures, TransactionCase):
    pass


class Mart369OrderHttpCase(Mart369OrderFixtures, HttpCase):
    pass
