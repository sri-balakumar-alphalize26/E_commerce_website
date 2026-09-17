"""The seam mart369_order will override.

The point of these is that when the order module arrives it overrides three methods
and nothing else in this module moves. If any of these fails, the seam has leaked
into the controllers and the order module will need surgery instead of a subclass.
"""

from odoo.tests import tagged

from .common import Mart369PaymentCase


@tagged('post_install', '-at_install')
class TestMart369Seam(Mart369PaymentCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({'name': 'Seam Customer'})
        cls.gateway = cls._mart369_gateway()
        cls.provider = cls.gateway
        cls.method = cls.env.ref('payment.payment_method_upi')

    def _tx(self, amount=100, kind='order'):
        return self.env['payment.transaction'].sudo().create({
            'provider_id': self.provider.id,
            'payment_method_id': self.method.id,
            'partner_id': self.partner.id,
            'amount': amount,
            'currency_id': self.env.company.currency_id.id,
            'operation': 'online_direct',
            'mart369_kind': kind,
        })

    def test_the_paid_hook_fires_when_a_payment_completes(self):
        calls = []
        tx = self._tx()

        def spy(self):
            calls.append(self.reference)
            return True

        self.patch(type(tx), '_mart369_on_paid', spy)
        tx._set_done()
        tx._post_process()
        self.assertEqual(calls, [tx.reference], 'exactly once, for this transaction')

    def test_the_paid_hook_does_not_fire_while_a_payment_is_pending(self):
        calls = []
        tx = self._tx()
        self.patch(type(tx), '_mart369_on_paid', lambda s: calls.append(s.reference))
        tx._set_pending()
        tx._post_process()
        self.assertEqual(calls, [], 'pending is not paid')

    def test_the_failed_hook_fires_on_a_cancelled_payment(self):
        calls = []
        tx = self._tx()
        self.patch(type(tx), '_mart369_on_failed', lambda s: calls.append(s.reference))
        tx._set_canceled()
        tx._post_process()
        self.assertEqual(calls, [tx.reference])

    def test_a_hook_that_raises_does_not_take_the_others_down(self):
        good = []
        one, two = self._tx(), self._tx()

        def explode(self):
            if self.id == one.id:
                raise ValueError('deliberate')
            good.append(self.reference)

        self.patch(type(one), '_mart369_on_paid', explode)
        (one | two)._set_done()
        (one | two)._post_process()
        self.assertEqual(good, [two.reference],
                         'one bad transaction must not stop the batch')

    def test_the_amount_hook_flags_that_the_browser_priced_it(self):
        amount, client_priced = self.env['payment.transaction']._mart369_amount_for(
            '369M-1', 250)
        self.assertEqual(amount, 250)
        self.assertTrue(client_priced,
                        'there is no cart on the server yet, and the record says so')

    def test_overriding_the_amount_hook_needs_no_controller_change(self):
        Tx = type(self.env['payment.transaction'])
        self.patch(Tx, '_mart369_amount_for',
                   lambda self, ref, claimed, currency=None: (999.0, False))
        amount, client_priced = self.env['payment.transaction']._mart369_amount_for(
            '369M-1', 250)
        self.assertEqual(amount, 999.0, 'the order module wins over the browser')
        self.assertFalse(client_priced)

    def test_a_cash_payment_is_not_paid_until_the_cash_is_collected(self):
        cod_provider = self.env.ref('delivery.payment_provider_cod')
        cod_method = self.env.ref('delivery.payment_method_cash_on_delivery')
        tx = self.env['payment.transaction'].sudo().create({
            'provider_id': cod_provider.id,
            'payment_method_id': cod_method.id,
            'partner_id': self.partner.id,
            'amount': 400,
            'currency_id': self.env.company.currency_id.id,
            'operation': 'online_direct',
        })
        tx._set_pending()
        self.assertNotEqual(tx.state, 'done',
                            'the app calls this paid the moment the order is placed')
        tx._mart369_mark_cod_collected()
        self.assertEqual(tx.state, 'done', 'and only the rider returning makes it true')

    def test_the_txn_the_app_prints_is_the_providers_reference_when_there_is_one(self):
        tx = self._tx()
        tx.sudo().write({'provider_reference': 'rzp_ABC123'})
        self.assertEqual(tx.mart369_txn, 'rzp_ABC123')
