"""The order desk - the backend screen, and the methods it reaches.

The desk talks to the model over `orm.call` rather than over HTTP, so it goes
through four public wrappers the console does not use. Those are tested here;
the screen itself is driven by a tour, because a component that loads and
draws nothing is a passing unit test and a broken screen.

The tour has to seed its own order. The product tours can lean on demo data,
but nothing ships a placed order - a shop with no orders is the normal state
of a fresh database, and the desk's empty state is exactly what a tour asserting
on rows would then be looking at.
"""

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import Mart369OrderCase, Mart369OrderHttpCase


@tagged('post_install', '-at_install')
class TestDeskMethods(Mart369OrderCase):
    """The wrappers `orm.call` needs, because it refuses a leading underscore."""

    def _order(self, **overrides):
        order = self._place(**overrides)
        self._pay(order)
        return order

    def test_detail_is_found_by_the_number_on_the_screen(self):
        order = self._order()
        detail = self.env['sale.order'].mart369_admin_detail(order.mart369_ref)
        self.assertEqual(detail['ref'], order.mart369_ref)
        self.assertEqual(detail['flow'], ['placed', 'packed', 'out', 'delivered'])

    def test_a_made_up_number_is_not_an_error(self):
        """The panel asks for whatever the list gave it. If the order has gone
        the screen should empty the panel, not blow up."""
        self.assertEqual(self.env['sale.order'].mart369_admin_detail('369M-NOPE'), {})
        self.assertEqual(self.env['sale.order'].mart369_admin_detail(False), {})

    def test_an_unpaid_basket_is_not_an_order(self):
        self._place(ref='369M-DRAFT')
        self.assertEqual(self.env['sale.order'].mart369_admin_detail('369M-DRAFT'), {})

    def test_advance_walks_the_ladder_and_hands_back_what_it_became(self):
        order = self._order()
        after = self.env['sale.order'].mart369_admin_advance(order.mart369_ref)
        self.assertEqual(after['state'], 'packed')
        self.assertEqual(after['next'], {'state': 'out', 'label': 'Send out'})

    def test_advance_ships_an_express_order(self):
        order = self._order(
            items={str(self.express_product.id): 1}, mode='all', ref='369M-EXP')
        after = self.env['sale.order'].mart369_admin_advance(order.mart369_ref)
        self.assertEqual(after['state'], 'shipped')

    def test_advancing_nothing_is_refused(self):
        with self.assertRaises(UserError):
            self.env['sale.order'].mart369_admin_advance('369M-NOPE')

    def test_a_delivered_order_cannot_be_moved_on(self):
        order = self._order()
        for __ in range(3):
            order.mart369_action_advance()
        with self.assertRaises(UserError):
            self.env['sale.order'].mart369_admin_advance(order.mart369_ref)

    def test_cancel_records_the_reason_on_the_timeline(self):
        order = self._order()
        after = self.env['sale.order'].mart369_admin_cancel(
            order.mart369_ref, 'Store closed')
        self.assertEqual(after['state'], 'cancelled')
        self.assertIsNone(after['next'])
        stamp = order.mart369_stamp_ids.filtered(lambda s: s.state == 'cancelled')
        self.assertEqual(stamp.note, 'Store closed')

    def test_a_reason_nobody_offered_is_refused(self):
        """It lands on the customer's own tracking screen, so it is picked
        from the list both screens are given, not typed."""
        order = self._order()
        for reason in (None, '', 'because'):
            with self.assertRaises(UserError):
                self.env['sale.order'].mart369_admin_cancel(order.mart369_ref, reason)
        self.assertEqual(order.mart369_state, 'placed')

    def test_the_reasons_come_with_the_list(self):
        """Both front ends read them from here, so neither keeps a copy."""
        page = self.env['sale.order'].mart369_admin_list()
        self.assertIn('Store closed', page['reasons'])

    def test_returns_are_a_tab_of_their_own(self):
        """The board's `has_return` filter, which the queue had no answer for.

        It counts orders carrying a return, not open return records - those are
        a different number, so they get a different name.
        """
        order = self._order()
        for __ in range(3):
            order.mart369_action_advance()

        # Measured as a change, not against zero. These counts are over the
        # whole shop, so any database that already holds a return - a seeded
        # demo, or production - made the old `== 0` fail on arrival.
        before = self.env['sale.order'].mart369_admin_counts()

        self.env['mart369.order.return'].create({
            'order_id': order.id,
            'reason': 'Arrived damaged',
        })
        counts = self.env['sale.order'].mart369_admin_counts()
        self.assertEqual(counts['counts']['returns'],
                         before['counts']['returns'] + 1)
        self.assertEqual(counts['returnsOpen'], before['returnsOpen'] + 1)
        rows = self.env['sale.order'].mart369_admin_list(tab='returns')['orders']
        self.assertIn(order.mart369_ref, [r['ref'] for r in rows])

    def test_cancelling_a_packed_order_is_refused(self):
        order = self._order()
        order.mart369_action_advance()
        with self.assertRaises(UserError):
            self.env['sale.order'].mart369_admin_cancel(
                order.mart369_ref, 'Store closed')
        self.assertEqual(order.mart369_state, 'packed')


@tagged('post_install', '-at_install')
class TestOrderDeskTour(Mart369OrderHttpCase):

    def test_desk_tour(self):
        # Nothing ships a placed order, and the desk's empty state is what a
        # tour asserting on rows would otherwise be looking at.
        order = self._place(ref='369M-TOUR')
        self._pay(order)
        self.assertEqual(order.mart369_state, 'placed')

        # Generous for the same reason as the other tours in this repo: the
        # first request after an upgrade rebuilds the backend asset bundle.
        self.start_tour('/odoo/mart-orders', 'mart369_order_desk',
                        login='admin', timeout=600)

        self.assertEqual(order.mart369_state, 'packed',
                         'the tour pressed the button and the write landed')
