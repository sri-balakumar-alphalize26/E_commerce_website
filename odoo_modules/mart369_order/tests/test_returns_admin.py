"""Returns: the ladder, the refusals, and the queue the console reads.

Returns had one test before this - that you cannot return somebody else's
order - so the model's own behaviour was unguarded: the ladder, the refusal at
each end, and the wallet-only refund. Those come first here, because the API
on top is only as honest as they are.

Then the queue itself. The one that matters most is the button's label: the
screen prints `next.label` verbatim, so if that is keyed wrongly every button
in the queue tells an operator to do the step after the one it will actually
do. It did, once.
"""

from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.mart369_order.tests.common import Mart369OrderCase


@tagged('post_install', '-at_install')
class TestReturnLadder(Mart369OrderCase):
    """The model, before anything is built on it."""

    def setUp(self):
        super().setUp()
        self.order = self._place()
        self._pay(self.order)
        self.ret = self.env['mart369.order.return'].create({
            'order_id': self.order.id,
            'kind': 'refund',
            'reason': 'Damaged or leaking',
            'amount': self.order.amount_total,
        })

    def test_it_starts_where_the_customer_left_it(self):
        self.assertEqual(self.ret.state, 'requested')

    def test_it_walks_the_ladder_one_step_at_a_time(self):
        for expected in ('pickup', 'picked', 'done'):
            self.ret.mart369_action_advance()
            self.assertEqual(self.ret.state, expected)

    def test_the_end_of_the_line_is_refused_not_ignored(self):
        """A button that silently does nothing is worse than one that says
        no - the operator presses it twice and assumes it worked."""
        for _ in range(3):
            self.ret.mart369_action_advance()
        with self.assertRaises(UserError):
            self.ret.mart369_action_advance()

    def test_refusing_stops_it(self):
        self.ret.mart369_action_refuse()
        self.assertEqual(self.ret.state, 'refused')

    def test_a_refunded_return_cannot_be_refused(self):
        """The money has gone. Saying "refused" after that would be a lie in
        the customer's own tracking screen."""
        for _ in range(3):
            self.ret.mart369_action_advance()
        with self.assertRaises(UserError):
            self.ret.mart369_action_refuse()

    def test_refused_is_off_the_ladder(self):
        self.ret.mart369_action_refuse()
        self.assertIsNone(self.ret._mart369_next_state())


@tagged('post_install', '-at_install')
class TestReturnsQueue(Mart369OrderCase):
    """What the console reads."""

    def setUp(self):
        super().setUp()
        self.Return = self.env['mart369.order.return']
        self.order = self._place()
        self._pay(self.order)
        self.ret = self.Return.create({
            'order_id': self.order.id,
            'kind': 'refund',
            'reason': 'Wrong item delivered',
            'detail': 'Sending back: 1 x Test Bananas - Pickup: today',
            'amount': self.order.amount_total,
        })

    # ------------------------------------------------------------- the row

    def test_the_row_carries_what_a_queue_needs(self):
        """`_mart369_serialize` is the customer's shape and has none of this:
        no order number, no customer, no next step."""
        row = self.ret._mart369_admin_row()
        self.assertEqual(row['ref'], self.order.mart369_ref)
        self.assertEqual(row['who'], self.partner.display_name)
        self.assertEqual(row['kind'], 'refund')
        self.assertEqual(row['state'], 'requested')
        self.assertTrue(row['canRefuse'])

    def test_the_button_says_the_step_it_will_take(self):
        """The screen prints this verbatim. Keyed by the state it lands in
        rather than the one it leaves, every button in the queue named the
        step after the one it does."""
        for state, label in (
            ('requested', 'Schedule pickup'),
            ('pickup', 'Mark picked up'),
            ('picked', 'Issue refund'),
        ):
            self.assertEqual(self.ret.state, state)
            self.assertEqual(self.ret._mart369_admin_row()['next']['label'], label)
            self.ret.mart369_action_advance()

    def test_a_finished_return_offers_nothing(self):
        for _ in range(3):
            self.ret.mart369_action_advance()
        row = self.ret._mart369_admin_row()
        self.assertIsNone(row['next'])
        self.assertFalse(row['canRefuse'])

    def test_the_currency_travels_whole(self):
        """A bare name prints an amount with no symbol at all."""
        currency = self.ret._mart369_admin_row()['currency']
        self.assertEqual(
            {'code', 'symbol', 'position', 'decimals', 'locale'} & set(currency),
            {'code', 'symbol', 'position', 'decimals', 'locale'})

    # ---------------------------------------------------------- the money

    def test_the_refund_split_is_honest_about_the_gateway(self):
        """`_mart369_refund` moves the wallet leg and nothing else, so the
        screen has to show which part it will not put back."""
        split = self.ret._mart369_refund_split()
        self.assertEqual(split['wallet'], 0.0)
        self.assertEqual(split['gateway'], split['total'])

    def test_a_wallet_paid_order_splits_the_other_way(self):
        order = self._place(ref='369M-WALLET')
        self._pay(order, wallet_used=order.amount_total)
        ret = self.Return.create({
            'order_id': order.id, 'kind': 'refund',
            'reason': 'Quality', 'amount': order.amount_total,
        })
        split = ret._mart369_refund_split()
        self.assertEqual(split['wallet'], split['total'])
        self.assertEqual(split['gateway'], 0.0)

    # ---------------------------------------------------------- the list

    def test_needs_me_holds_only_what_is_open(self):
        self.assertIn(self.ret.id, self._ids('needs'))
        self.ret.mart369_action_refuse()
        self.assertNotIn(self.ret.id, self._ids('needs'))
        self.assertIn(self.ret.id, self._ids('refused'))

    def test_the_tiles_add_up(self):
        counts = self.Return.mart369_returns_counts()
        self.assertEqual(counts['all'], self.Return.search_count([]))
        self.assertEqual(
            counts['needs'],
            counts['requested'] + counts['pickup'] + counts['picked'])

    def test_search_covers_order_customer_and_reason(self):
        for term in (self.order.mart369_ref, self.partner.name, 'Wrong item'):
            self.assertIn(self.ret.id, self._ids('all', q=term),
                          'searching %r did not find it' % term)

    def test_the_kind_filter_narrows(self):
        self.assertIn(self.ret.id, self._ids('all', kind='refund'))
        self.assertNotIn(self.ret.id, self._ids('all', kind='replace'))

    # --------------------------------------------------------- the writes

    def test_advancing_through_the_wrapper_returns_the_new_detail(self):
        data = self.Return.mart369_returns_advance(self.ret.id)
        self.assertEqual(data['state'], 'pickup')
        self.assertEqual(self.ret.state, 'pickup')

    def test_a_made_up_id_is_refused_not_guessed(self):
        with self.assertRaises(ValueError):
            self.Return.mart369_returns_advance(10 ** 7)
        self.assertEqual(self.Return.mart369_returns_detail(10 ** 7), {})
        self.assertEqual(self.Return.mart369_returns_detail('nonsense'), {})

    def test_the_detail_carries_the_photos_and_the_ladder(self):
        data = self.Return.mart369_returns_detail(self.ret.id)
        self.assertEqual(data['photoIds'], [])
        self.assertEqual([s['state'] for s in data['flow']],
                         ['requested', 'pickup', 'picked', 'done'])
        self.assertIn('Sending back', data['detail'])

    # ------------------------------------------------------------ helpers

    def _ids(self, tab, **kw):
        return [int(r['id'])
                for r in self.Return.mart369_returns_list(tab=tab, **kw)['returns']]
