"""The 369 Wallet invariant.

The bug being fixed is that the storefront keeps the balance and the ledger in two
separate localStorage keys that nothing reconciles. These tests exist to make the
same mistake impossible here: if any of them fails, the customer's money and the
customer's history can disagree.
"""

from psycopg2 import IntegrityError

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger


@tagged('post_install', '-at_install')
class TestMart369Wallet(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({'name': 'Wallet Tester'})
        cls.other = cls.env['res.partner'].create({'name': 'Someone Else'})
        cls.Card = cls.env['loyalty.card']
        cls.wallet = cls.Card._mart369_wallet(cls.partner)

    def _total(self, card):
        card.invalidate_recordset()
        return sum(card.history_ids.mapped('issued')) - sum(card.history_ids.mapped('used'))

    # ------------------------------------------------------------ one per customer

    def test_a_customer_has_exactly_one_wallet(self):
        again = self.Card._mart369_wallet(self.partner)
        self.assertEqual(again, self.wallet, 'asking twice returns the same wallet')

    def test_a_second_wallet_for_the_same_customer_is_refused_by_the_database(self):
        program = self.Card._mart369_program()
        with self.assertRaises(IntegrityError, msg='the unique index is the authority'), \
                mute_logger('odoo.sql_db'):
            with self.env.cr.savepoint():
                self.Card.create({
                    'program_id': program.id,
                    'partner_id': self.partner.id,
                    'points': 0.0,
                })

    def test_two_customers_get_different_wallets(self):
        theirs = self.Card._mart369_wallet(self.other)
        self.assertNotEqual(theirs, self.wallet, 'one wallet each, not one shared')

    # ------------------------------------------------- the balance/ledger invariant

    def test_every_balance_change_writes_exactly_one_ledger_row(self):
        before = len(self.wallet.history_ids)
        self.wallet._mart369_move(100, 'add', 'Money added', 'Via Google Pay')
        self.wallet.invalidate_recordset()
        self.assertEqual(len(self.wallet.history_ids), before + 1,
                         'one movement, one row')

    def test_the_balance_always_equals_the_ledger_sum(self):
        self.wallet._mart369_move(250, 'add', 'Money added')
        self.wallet._mart369_move(40, 'spend', 'Order', 'Order #369M-24091612')
        self.wallet._mart369_move(15, 'refund', 'Refund')
        self.wallet.invalidate_recordset()
        self.assertEqual(self.wallet.points, self._total(self.wallet),
                         'balance and ledger agree to the paisa')
        self.assertTrue(self.wallet.mart369_consistent,
                        'and the record says so itself')

    def test_points_cannot_be_written_outside_the_move_helper(self):
        with self.assertRaises(UserError, msg='a bare write would desync the ledger'):
            self.wallet.write({'points': 9999})

    def test_points_can_still_be_written_on_an_ordinary_coupon(self):
        program = self.env['loyalty.program'].create({
            'name': 'Not a wallet',
            'program_type': 'loyalty',
            'reward_ids': [(0, 0, {
                'reward_type': 'discount', 'discount': 5,
                'discount_mode': 'percent', 'discount_applicability': 'order',
            })],
        })
        coupon = self.Card.create({'program_id': program.id, 'partner_id': self.other.id})
        coupon.write({'points': 12})
        self.assertEqual(coupon.points, 12, 'the guard is for wallets only')

    # ------------------------------------------------------------------ overdrafts

    def test_spending_more_than_the_balance_is_refused_and_changes_nothing(self):
        self.wallet._mart369_move(50, 'add', 'Money added')
        rows = len(self.wallet.history_ids)
        with self.assertRaises(UserError):
            self.wallet._mart369_move(80, 'spend', 'Order')
        self.wallet.invalidate_recordset()
        self.assertEqual(self.wallet.points, 50, 'the balance did not move')
        self.assertEqual(len(self.wallet.history_ids), rows, 'and no row was written')

    def test_a_debit_is_never_silently_clamped_to_zero(self):
        self.wallet._mart369_move(30, 'add', 'Money added')
        with self.assertRaises(UserError, msg='Math.max(0, ...) is what we are replacing'):
            self.wallet._mart369_move(100, 'spend', 'Order')
        self.wallet.invalidate_recordset()
        self.assertEqual(self.wallet.points, 30, 'not zero, and not negative')

    def test_topping_up_past_the_wallet_limit_is_refused(self):
        self.wallet._mart369_move(9950, 'add', 'Money added')
        with self.assertRaises(UserError):
            self.wallet._mart369_move(100, 'add', 'Money added')
        self.wallet.invalidate_recordset()
        self.assertEqual(self.wallet.points, 9950, 'the limit held')

    def test_a_movement_with_no_amount_is_refused(self):
        with self.assertRaises(UserError):
            self.wallet._mart369_move(0, 'add', 'Money added')

    def test_an_unknown_kind_is_refused(self):
        with self.assertRaises(UserError):
            self.wallet._mart369_move(10, 'donation', 'Money added')

    # ------------------------------------------------------------ the app's shape

    def test_the_ledger_serializes_to_the_six_keys_the_ui_reads(self):
        self.wallet._mart369_move(100, 'add', 'Money added', 'Via Google Pay')
        row = self.wallet._mart369_ledger()[0]._mart369_serialize()
        self.assertEqual(set(row), {'id', 'kind', 'amount', 'title', 'sub', 'at'},
                         'exactly what AccountExtras.jsx renders, no more')
        self.assertIsInstance(row['id'], str, 'the app compares ids with ===')
        self.assertEqual(row['kind'], 'add')
        self.assertEqual(row['title'], 'Money added')
        self.assertEqual(row['sub'], 'Via Google Pay')
        self.assertGreater(row['at'], 10 ** 12, 'milliseconds, not seconds')

    def test_ledger_amounts_are_always_positive_and_the_kind_carries_the_sign(self):
        self.wallet._mart369_move(200, 'add', 'Money added')
        self.wallet._mart369_move(75, 'spend', 'Order', 'Order #369M-24091612')
        rows = [r._mart369_serialize() for r in self.wallet._mart369_ledger()]
        self.assertTrue(all(r['amount'] > 0 for r in rows),
                        'KIND_META draws the sign; the number never carries it')
        self.assertEqual({r['kind'] for r in rows}, {'add', 'spend'})

    def test_the_ledger_comes_back_newest_first(self):
        self.wallet._mart369_move(10, 'add', 'First')
        self.wallet._mart369_move(20, 'add', 'Second')
        titles = [r.mart369_title for r in self.wallet._mart369_ledger()]
        self.assertEqual(titles[0], 'Second', 'newest first, like the app log')

    # ------------------------------------------------------------- the order link

    def test_a_ledger_row_carries_a_real_order_link_not_a_string_match(self):
        order = self.env['sale.order'].create({'partner_id': self.partner.id})
        self.wallet._mart369_move(100, 'add', 'Money added')
        history = self.wallet._mart369_move(
            60, 'spend', 'Order', 'Order #%s' % order.name, order=order)
        self.assertEqual(history.order_model, 'sale.order',
                         'the reference fields are the real link')
        self.assertEqual(history.order_id, order.id)
        self.assertIn('Order #', history._mart369_serialize()['sub'],
                      "and the subtitle still satisfies the app's regex")

    def test_the_description_odoo_shows_is_built_from_our_two_lines(self):
        history = self.wallet._mart369_move(25, 'reward', 'Scratch card reward', 'From order #369M-1')
        self.assertIn('Scratch card reward', history.description,
                      "Odoo's own loyalty screens stay readable")
