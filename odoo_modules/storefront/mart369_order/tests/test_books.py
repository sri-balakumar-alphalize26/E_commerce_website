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

    # ------------------------------------------------------------- returns

    def _delivered_rice(self):
        """3 of a stocked product delivered out of 10: 7 left on the shelf."""
        template = self._mart369_product('Test Atta 5kg', 300.0)
        template.write({'is_storable': True})
        product = template.product_variant_id
        order = self._place(items={str(template.id): 3})
        location = order.warehouse_id.lot_stock_id
        self.env['stock.quant'].sudo()._update_available_quantity(product, location, 10)
        self._pay(order)
        self._deliver(order)
        on_hand = lambda: product.with_context(location=location.id).qty_available  # noqa: E731
        self.assertEqual(on_hand(), 7)
        return order, on_hand

    def _return(self, order):
        return self.env['mart369.order.return'].sudo().create({
            'order_id': order.id, 'reason': 'Damaged', 'amount': order.amount_total})

    def _finish(self, ret):
        while ret.state != 'done':
            ret.mart369_action_advance()

    def test_a_finished_return_puts_the_goods_back_in_stock(self):
        order, on_hand = self._delivered_rice()
        ret = self._return(order)
        self._finish(ret)
        self.assertEqual(on_hand(), 10, 'the goods are back on the shelf')
        self.assertEqual(ret.return_picking_id.picking_type_code, 'incoming')
        self.assertEqual(ret.return_picking_id.state, 'done')
        self.assertTrue(ret.refunded, 'and the refund still happens')

        ret._mart369_restock()
        self.assertEqual(on_hand(), 10, 'restocking again moves nothing')

    def test_a_second_return_on_the_same_order_restocks_nothing(self):
        order, on_hand = self._delivered_rice()
        self._finish(self._return(order))
        second = self._return(order)
        self._finish(second)
        self.assertEqual(on_hand(), 10, 'the goods came back once')
        self.assertFalse(second.return_picking_id)

    def test_a_return_refused_after_pickup_leaves_stock_alone(self):
        order, on_hand = self._delivered_rice()
        ret = self._return(order)
        ret.mart369_action_advance()
        ret.mart369_action_advance()
        self.assertEqual(ret.state, 'picked')
        ret.mart369_action_refuse()
        self.assertEqual(on_hand(), 7, 'the goods go back to the customer')
        self.assertFalse(ret.return_picking_id)

    def test_a_return_with_nothing_delivered_still_refunds(self):
        """An older order whose delivery was never validated."""
        order = self._place()
        self._pay(order)
        order.picking_ids.action_cancel()
        order.write({'mart369_state': 'delivered'})
        ret = self._return(order)
        self._finish(ret)
        self.assertTrue(ret.refunded)
        self.assertFalse(ret.return_picking_id)

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


@tagged('post_install', '-at_install')
class TestWalletBooks(Mart369OrderCase):
    """Cash at the door and the 369 Wallet as real entries (wallet_books.py).

    'paid', never 'in_payment': a payment with no journal entry leaves its
    invoice In payment for ever, which is exactly what went unnoticed."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env['payment.provider']._mart369_setup_journals()
        cls.company = cls.env.company
        cls.liability = cls.company.mart369_wallet_account_id
        cls.rewards = cls.company.mart369_wallet_reward_account_id
        cls.card = cls.env['loyalty.card'].sudo()._mart369_wallet(cls.partner)

    def _journal(self, kind):
        return self.env['account.journal']._mart369_journal_for(kind, self.company)

    def _invoice(self, order):
        return order.invoice_ids.filtered(
            lambda m: m.move_type == 'out_invoice' and m.state == 'posted')

    def _balance(self, account):
        """Credit minus debit of the posted lines on `account`."""
        lines = self.env['account.move.line'].sudo().search([
            ('account_id', '=', account.id), ('parent_state', '=', 'posted')])
        return sum(lines.mapped('credit')) - sum(lines.mapped('debit'))

    def _deliver(self, order):
        code = order.sudo().mart369_otp_code
        order.mart369_action_advance()
        order.mart369_action_advance()
        order.mart369_action_deliver(code)

    def _wallet_only(self, order):
        provider = self.env.ref('mart369_payment.payment_provider_wallet').sudo()
        provider.write({'state': 'test'})
        self.card._mart369_move(order.amount_total, 'add', 'Seed')
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
        return tx

    # ------------------------------------------------------------- setup

    def test_the_accounts_are_set_once(self):
        self.assertEqual(self.liability.account_type, 'liability_current')
        self.assertFalse(self.liability.reconcile)
        self.assertEqual(self.rewards.account_type, 'expense')
        for kind in ('cash_on_delivery', 'mart369_wallet'):
            journal = self._journal(kind)
            lines = (journal.inbound_payment_method_line_ids
                     + journal.outbound_payment_method_line_ids)
            self.assertTrue(all(lines.mapped('payment_account_id')), kind)
        self.assertEqual(
            self._journal('mart369_wallet').inbound_payment_method_line_ids.payment_account_id,
            self.liability)
        accounts = self.env['account.account'].sudo().search_count([])
        self.env['payment.provider']._mart369_setup_journals()
        self.assertEqual(self.env['account.account'].sudo().search_count([]), accounts)
        self.assertEqual(self.company.mart369_wallet_account_id, self.liability)

    # ------------------------------------------------------------ money in

    def test_cash_at_the_door_is_a_real_entry(self):
        order = self._place()
        tx = self._cash(order)
        self._deliver(order)
        move = tx.payment_id.move_id
        self.assertTrue(move, 'the cash is in the books')
        self.assertEqual(move.state, 'posted')
        cod_cash = self._journal('cash_on_delivery').default_account_id
        self.assertTrue(move.line_ids.filtered(
            lambda l: l.account_id == cod_cash and l.debit))
        self.assertEqual(self._invoice(order).payment_state, 'paid')

    def test_spending_the_wallet_uses_the_liability(self):
        order = self._place()
        before = self._balance(self.liability)
        tx = self._wallet_only(order)
        move = tx.payment_id.move_id
        self.assertTrue(move.line_ids.filtered(
            lambda l: l.account_id == self.liability and l.debit))
        self.assertEqual(self._invoice(order).payment_state, 'paid')
        # The seed 'add' had no transaction, so only the spend moved it.
        self.assertAlmostEqual(before - self._balance(self.liability),
                               order.amount_total, places=2)

    def test_a_split_wallet_part_uses_the_liability(self):
        order = self._place()
        tx = self._pay(order, amount=order.amount_total - 20.0, wallet_used=20.0)
        wallet = tx.mart369_wallet_payment_id
        self.assertTrue(wallet.move_id.line_ids.filtered(
            lambda l: l.account_id == self.liability and l.debit == 20.0))
        # The invoice follows the gateway part too (a bank statement settles
        # that one); the wallet part is settled the moment it posts.
        self.assertEqual(wallet.state, 'paid')

    # --------------------------------------------------------- money back

    def test_a_refund_to_the_wallet_is_booked_and_matches_the_credit_note(self):
        order = self._place()
        self._pay(order)
        before = self._balance(self.liability)
        order._mart369_cancel(reason='Store closed')
        row = self.env['loyalty.history'].sudo().search([
            ('order_model', '=', 'sale.order'), ('order_id', '=', order.id),
            ('mart369_kind', '=', 'refund')])
        self.assertEqual(len(row), 1, 'cancelling keeps the refund row (sale_loyalty deleted it)')
        self.assertTrue(row.mart369_move_id, 'the refund is an entry')
        self.assertEqual(row.mart369_move_id.journal_id, self._journal('mart369_wallet'))
        self.assertAlmostEqual(self._balance(self.liability) - before,
                               order.amount_total, places=2)
        note = order.invoice_ids.filtered(
            lambda m: m.move_type == 'out_refund' and m.state == 'posted')
        self.assertTrue(note)
        self.assertTrue(note.currency_id.is_zero(note.amount_residual),
                        'the credit note is settled by the wallet refund')

    def test_cancelling_keeps_the_wallet_ledger_whole(self):
        """Odoo's sale_loyalty deletes an order's history rows on cancel;
        the wallet's own rows are money and must survive it."""
        order = self._place()
        self._pay(order, amount=order.amount_total - 10.0, wallet_used=10.0)
        self.card._mart369_move(10.0, 'add', 'Seed')
        self.card._mart369_move(10.0, 'spend', 'Order', order=order)
        order._mart369_cancel(reason='Changed my mind')
        self.card.invalidate_recordset()
        self.assertTrue(self.card.mart369_consistent,
                        'the balance still matches its ledger')
        kinds = self.env['loyalty.history'].sudo().search([
            ('order_model', '=', 'sale.order'), ('order_id', '=', order.id)]).mapped('mart369_kind')
        self.assertIn('spend', kinds)
        self.assertIn('refund', kinds)

    def test_a_failed_split_leg_given_back_books_nothing(self):
        self.card._mart369_move(30.0, 'add', 'Seed')
        self.card._mart369_move(30.0, 'spend', 'Order')
        row = self.card._mart369_move(30.0, 'refund', 'Payment failed', sub='TX-1')
        self.assertFalse(row.mart369_move_id)

    def test_a_top_up_is_booked_and_nets_the_receivable(self):
        tx = self.env['payment.transaction'].sudo().create({
            'provider_id': self.gateway.id,
            'payment_method_id': self.method.id,
            'partner_id': self.partner.id,
            'amount': 300.0,
            'currency_id': self.company.currency_id.id,
            'operation': 'online_direct',
            'mart369_kind': 'topup',
            'mart369_wallet_card_id': self.card.id,
        })
        before = self._balance(self.liability)
        tx._set_done()
        tx._post_process()
        row = tx.mart369_history_id
        self.assertTrue(row.mart369_move_id)
        self.assertAlmostEqual(self._balance(self.liability) - before, 300.0, places=2)
        if tx.payment_id.move_id:
            receivable = (tx.payment_id.move_id + row.mart369_move_id).line_ids.filtered(
                lambda l: l.account_id.account_type == 'asset_receivable')
            self.assertTrue(all(receivable.mapped('reconciled')),
                            'the gateway money and the wallet cancel out')

    def test_a_reward_is_an_expense_owed_to_the_customer(self):
        row = self.card._mart369_move(50.0, 'reward', 'Scratch card prize')
        move = row.mart369_move_id
        self.assertEqual(move.state, 'posted')
        self.assertTrue(move.line_ids.filtered(
            lambda l: l.account_id == self.rewards and l.debit == 50.0))
        self.assertTrue(move.line_ids.filtered(
            lambda l: l.account_id == self.liability and l.credit == 50.0))

    def test_the_liability_follows_the_wallets(self):
        """Every booked movement moves the account by exactly as much as it
        moves the wallets."""
        Card = self.env['loyalty.card'].sudo()
        program = Card._mart369_program()

        def points():
            return sum(Card.search([('program_id', '=', program.id)]).mapped('points'))

        start_points, start_books = points(), self._balance(self.liability)
        self.card._mart369_move(40.0, 'reward', 'Referral')
        order = self._place()
        self._pay(order)
        order._mart369_cancel(reason='Out of stock')
        spent = self._place()
        tx = self._pay(spent, amount=spent.amount_total - 15.0, wallet_used=15.0)
        # The split's own checkout debit (payment_api.py does it in real life).
        self.card._mart369_move(15.0, 'spend', 'Order', order=spent)
        self.assertTrue(tx.mart369_wallet_payment_id)

        self.assertAlmostEqual(points() - start_points,
                               self._balance(self.liability) - start_books, places=2)

    # ------------------------------------------------------------ history

    def test_payments_made_before_the_accounts_are_caught_up(self):
        order = self._place()
        journal = self._journal('cash_on_delivery')
        lines = journal.inbound_payment_method_line_ids
        account = lines[:1].payment_account_id
        lines.payment_account_id = False
        tx = self._cash(order)
        self._deliver(order)
        payment = tx.payment_id
        self.assertFalse(payment.move_id, 'the old behaviour: no entry')

        lines.payment_account_id = account
        Journal = self.env['account.journal']
        Journal._mart369_books_catch_up(self.company)
        self.assertTrue(payment.move_id)
        self.assertEqual(payment.move_id.state, 'posted')
        self.assertEqual(self._invoice(order).payment_state, 'paid')
        self.assertEqual(Journal._mart369_books_catch_up(self.company), 0, 'and only once')

    def test_the_opening_entry_is_a_draft_for_the_accountant(self):
        self.card._mart369_move(75.0, 'add', 'Old money')
        self.env['ir.model.data'].sudo().search([
            ('module', '=', 'mart369_order'),
            ('name', '=', 'wallet_opening_company_%s' % self.company.id)]).unlink()
        Journal = self.env['account.journal']
        move = Journal._mart369_wallet_opening(self.company)
        self.assertEqual(move.state, 'draft')
        Card = self.env['loyalty.card'].sudo()
        program = Card._mart369_program()
        total = sum(Card.search([
            ('program_id', '=', program.id), ('points', '>', 0),
            '|', ('company_id', '=', self.company.id), ('company_id', '=', False),
        ]).mapped('points'))
        credit = move.line_ids.filtered(lambda l: l.account_id == self.liability)
        self.assertAlmostEqual(credit.credit, total, places=2)
        self.assertFalse(Journal._mart369_wallet_opening(self.company), 'made once')
