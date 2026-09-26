"""The order in Odoo's own books (order_accounting.py, payment_journal.py).

What an accountant opening Sales, Inventory and Invoicing should find after a
369 Mart order: the invoice paid, the payment in the right journal, the goods
gone from stock, and a cancelled cash order no longer counted as revenue.
None of these announce themselves when they break - every screen in the app
still looks right - so each is pinned here.
"""

from odoo.tests import tagged

from .common import Mart369OrderCase

PAID = ('paid', 'in_payment')


@tagged('post_install', '-at_install')
class TestBooks(Mart369OrderCase):

    def _invoice(self, order):
        return order.invoice_ids.filtered(
            lambda m: m.move_type == 'out_invoice' and m.state == 'posted')

    def _payments(self, order):
        return self.env['account.payment'].sudo().search([
            ('reconciled_invoice_ids', 'in', self._invoice(order).ids)])

    def _deliver(self, order):
        code = order.sudo().mart369_otp_code
        order.mart369_action_advance()
        order.mart369_action_advance()
        order.mart369_action_deliver(code)

    def _journal(self, kind):
        return self.env['account.journal']._mart369_journal_for(kind, self.env.company)

    # -------------------------------------------------------------- paying

    def test_a_paid_order_has_a_paid_invoice(self):
        order = self._place()
        self._pay(order)
        invoice = self._invoice(order)
        self.assertEqual(len(invoice), 1)
        self.assertIn(invoice.payment_state, PAID, 'the money met the bill')
        self.assertEqual(len(self._payments(order)), 1)

    def test_paying_twice_books_one_payment(self):
        order = self._place()
        tx = self._pay(order)
        tx._post_process()
        order._mart369_settle_invoice()
        self.assertEqual(len(self._payments(order)), 1)

    def test_a_split_payment_books_the_wallet_part_in_the_wallet_journal(self):
        order = self._place()
        total = order.amount_total
        tx = self._pay(order, amount=total - 20.0, wallet_used=20.0)
        self.assertIn(self._invoice(order).payment_state, PAID)
        wallet = tx.mart369_wallet_payment_id
        self.assertTrue(wallet, 'the wallet part is a payment of its own')
        self.assertEqual(wallet.journal_id, self._journal('mart369_wallet'))
        self.assertAlmostEqual(wallet.amount, 20.0, places=2)

        order._mart369_settle_invoice()
        self.assertEqual(tx.mart369_wallet_payment_id, wallet, 'booked once')

    def test_a_wallet_only_order_is_booked_in_the_wallet_journal(self):
        order = self._place()
        provider = self.env.ref('mart369_payment.payment_provider_wallet').sudo()
        provider.write({'state': 'test'})
        tx = self.env['payment.transaction'].sudo().create({
            'provider_id': provider.id,
            'payment_method_id': provider.payment_method_ids[:1].id,
            'partner_id': self.partner.id,
            'amount': order.amount_total,
            'currency_id': order.currency_id.id,
            'operation': 'online_direct',
            'mart369_kind': 'order',
            'mart369_order_ref': order.mart369_ref,
            'mart369_wallet_used': order.amount_total,
        })
        tx._set_done()
        tx._post_process()
        self.assertEqual(tx.payment_id.journal_id, self._journal('mart369_wallet'))
        self.assertIn(self._invoice(order).payment_state, PAID)
        self.assertFalse(tx.mart369_wallet_payment_id, 'not booked a second time')

    # ----------------------------------------------------- cash at the door

    def test_cash_is_owed_until_the_door_then_paid_in_the_cash_journal(self):
        order = self._place()
        tx = self._cash(order)
        self.assertEqual(self._invoice(order).payment_state, 'not_paid')

        self._deliver(order)
        self.assertEqual(tx.state, 'done')
        self.assertIn(self._invoice(order).payment_state, PAID)
        self.assertEqual(tx.payment_id.journal_id, self._journal('cash_on_delivery'))

    # --------------------------------------------------------------- stock

    def test_delivering_takes_the_goods_out_of_stock(self):
        template = self._mart369_product('Test Rice 5kg', 400.0)
        template.write({'is_storable': True})
        product = template.product_variant_id
        order = self._place(items={str(template.id): 3})
        location = order.warehouse_id.lot_stock_id
        self.env['stock.quant'].sudo()._update_available_quantity(product, location, 10)

        self._pay(order)
        picking = order.picking_ids.filtered(lambda p: p.picking_type_code == 'outgoing')
        self.assertTrue(picking)
        self.assertNotEqual(picking.state, 'done', 'not before the door')

        self._deliver(order)
        self.assertEqual(picking.state, 'done')
        self.assertEqual(product.with_context(location=location.id).qty_available, 7)

        order._mart369_validate_pickings()
        self.assertEqual(product.with_context(location=location.id).qty_available, 7,
                         'validating again moves nothing')

    # ---------------------------------------------------------- cancelling

    def test_a_cash_order_cancelled_before_the_door_is_no_longer_billed(self):
        order = self._place()
        self._cash(order)
        invoice = self._invoice(order)
        self.assertEqual(invoice.payment_state, 'not_paid')

        order._mart369_cancel(reason='Changed my mind')
        self.assertEqual(order.state, 'cancel')
        self.assertEqual(invoice.payment_state, 'reversed', 'revenue no longer counts it')

    def test_a_paid_order_cancelled_keeps_its_paid_invoice_and_gets_a_credit_note(self):
        order = self._place()
        self._pay(order)
        invoice = self._invoice(order)
        payments = self._payments(order)
        self.assertEqual(len(payments), 1)

        order._mart369_cancel(reason='Store closed')
        # The full credit note from the wallet refund reverses the sale, so
        # Odoo reads the invoice as Reversed - but the money did arrive, and
        # its payment stays on the books.
        self.assertIn(invoice.payment_state, PAID + ('reversed',))
        self.assertNotEqual(payments.state, 'canceled', 'the money did arrive')
        notes = order.invoice_ids.filtered(
            lambda m: m.move_type == 'out_refund' and m.state == 'posted')
        self.assertEqual(len(notes), 1, 'the wallet refund answers it')

    # ------------------------------------------------ a customer with a wallet

    def test_a_customer_with_a_wallet_still_gets_a_confirmed_order(self):
        """Found on the live database: `sale_loyalty` touches every loyalty
        card the order carries on confirm, the wallet included. The wallet
        guard refused that, the confirm failed quietly, and a paid order was
        left a quotation with no invoice and no delivery."""
        wallet = self.env['loyalty.card'].sudo()._mart369_wallet(self.partner)
        order = self._place()
        self.env['sale.order.coupon.points'].sudo().create({
            'order_id': order.id, 'coupon_id': wallet.id, 'points': 0})
        self._cash(order)
        self.assertEqual(order.state, 'sale')
        self.assertTrue(self._invoice(order))
        self.assertTrue(order.picking_ids)

    # ------------------------------------------------------------ journals

    def test_the_journals_are_made_once(self):
        Provider = self.env['payment.provider']
        Provider._mart369_setup_journals()
        cod = self._journal('cash_on_delivery')
        wallet = self._journal('mart369_wallet')
        Provider._mart369_setup_journals()
        self.assertEqual(self._journal('cash_on_delivery'), cod)
        self.assertEqual(self._journal('mart369_wallet'), wallet)
        self.assertEqual(cod.type, 'cash')
        self.assertNotEqual(cod, wallet)
