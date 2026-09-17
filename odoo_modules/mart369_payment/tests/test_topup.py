"""Adding money to the 369 Wallet.

The app's own top-up is a two-second setTimeout that then credits the balance
(AccountExtras.jsx:144): the money appears without anybody being charged, and a
second call would credit again. Both of those are fixed here, and the second one -
idempotency - matters more than it looks, because providers really do resend
webhooks.
"""

from odoo.tests import tagged

from .common import Mart369PaymentCase


@tagged('post_install', '-at_install')
class TestMart369Topup(Mart369PaymentCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({'name': 'Topup Customer'})
        cls.card = cls.env['loyalty.card']._mart369_wallet(cls.partner)
        cls.gateway = cls._mart369_gateway()
        cls.provider = cls.gateway
        cls.method = cls.env.ref('payment.payment_method_upi')

    def _tx(self, amount=500):
        return self.env['payment.transaction'].sudo().create({
            'provider_id': self.provider.id,
            'payment_method_id': self.method.id,
            'partner_id': self.partner.id,
            'amount': amount,
            'currency_id': self.env.company.currency_id.id,
            'operation': 'online_direct',
            'mart369_kind': 'topup',
            'mart369_wallet_card_id': self.card.id,
        })

    def test_a_top_up_credits_nothing_until_the_provider_confirms(self):
        self._tx()
        self.card.invalidate_recordset()
        self.assertEqual(self.card.points, 0,
                         'a started top-up is not money in the wallet')

    def test_a_confirmed_top_up_credits_the_wallet(self):
        tx = self._tx(500)
        tx._set_done()
        tx._post_process()
        self.card.invalidate_recordset()
        self.assertEqual(self.card.points, 500)
        self.assertTrue(tx.mart369_history_id, 'and it left a ledger row')

    def test_a_confirmed_top_up_credits_exactly_once_even_if_the_webhook_repeats(self):
        tx = self._tx(500)
        tx._set_done()
        tx._post_process()
        tx._post_process()
        tx._post_process()
        self.card.invalidate_recordset()
        self.assertEqual(self.card.points, 500,
                         'mart369_history_id is the idempotency key, and it held')
        self.assertEqual(len(self.card.history_ids), 1, 'one row, not three')

    def test_a_failed_top_up_leaves_the_balance_untouched(self):
        tx = self._tx(500)
        tx._set_error('Declined')
        tx._post_process()
        self.card.invalidate_recordset()
        self.assertEqual(self.card.points, 0)

    def test_the_top_up_row_says_how_the_money_came_in(self):
        tx = self._tx(250)
        tx._set_done()
        tx._post_process()
        row = tx.mart369_history_id._mart369_serialize()
        self.assertEqual(row['kind'], 'add')
        self.assertEqual(row['amount'], 250)
        self.assertIn('Via', row['sub'])

    def test_the_balance_and_the_ledger_still_agree_after_a_top_up(self):
        tx = self._tx(700)
        tx._set_done()
        tx._post_process()
        self.card.invalidate_recordset()
        self.assertTrue(self.card.mart369_consistent)
