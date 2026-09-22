"""The staff side of orders, for the app's own console.

Three things are worth pinning here, and they are the three that would not
announce themselves when they break.

**Who may look.** These routes have no `_own()` fence - that is the whole point
of them - so the group check is the only thing between a shopper and every
customer's phone number. It is checked on every route, and a shopper is refused
rather than handed an empty list.

**Which step is next.** The console draws whatever button the server tells it
to. If the payload ever offers "Start packing" on an express order the screen
will show it, the operator will press it, and the constraint on `sale.order`
will refuse the write - so the label is checked against the order's own flow
rather than against a list kept here.

**What the payload carries.** The delivery code exists so that a stranger at a
door cannot take a parcel. A console that prints it, or prints the hash it is
checked against, undoes that quietly and looks fine on screen.
"""

import json

from odoo.tests import tagged

from .common import Mart369OrderHttpCase


@tagged('post_install', '-at_install')
class TestAdminOrders(Mart369OrderHttpCase):

    def setUp(self):
        super().setUp()
        self.shopper = self.env['res.users'].sudo().create({
            'name': 'A Shopper',
            'login': 'mart369_order_shopper',
            'password': 'mart369_order_shopper',
            'group_ids': [(6, 0, [self.env.ref('base.group_portal').id])],
        })

    # ------------------------------------------------------------- acting

    def _order(self, **overrides):
        """A placed and paid order, which is the only kind the console sees."""
        order = self._place(**overrides)
        self._pay(order)
        return order

    def _get(self, path):
        return self.url_open(path)

    def _post(self, path, payload=None):
        return self.url_open(
            path, data=json.dumps(payload or {}),
            headers={'Content-Type': 'application/json'})

    def _staff(self):
        self.authenticate('admin', 'admin')

    # -------------------------------------------------------------- the lock

    def test_a_shopper_is_refused_every_admin_route(self):
        """Refused, not filtered. A shopper must not learn this exists."""
        order = self._order()
        self.authenticate('mart369_order_shopper', 'mart369_order_shopper')
        for response in (
            self._get('/369mart/admin/orders'),
            self._get('/369mart/admin/orders/counts'),
            self._get('/369mart/admin/orders/%s' % order.mart369_ref),
            self._post('/369mart/admin/orders/%s/advance' % order.mart369_ref),
            self._post('/369mart/admin/orders/%s/cancel' % order.mart369_ref,
                       {'reason': 'Store closed'}),
            self._get('/369mart/admin/orders/%s/invoice' % order.mart369_ref),
        ):
            self.assertEqual(response.status_code, 403)

    def test_a_signed_out_visitor_gets_nothing(self):
        """Sent to the login page, not answered.

        `auth='user'` redirects rather than refusing, and the redirect lands on
        a page that answers 200 - so this asserts on the hop, not on the status
        the browser finally sees.
        """
        order = self._order()
        response = self.url_open(
            '/369mart/admin/orders/%s' % order.mart369_ref, allow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertIn('/web/login', response.headers.get('Location', ''))

    # -------------------------------------------------------------- the list

    def test_the_list_opens_on_what_still_needs_doing(self):
        live = self._order()
        done = self._order(ref='369M-DONE')
        for __ in range(3):
            done.mart369_action_advance()
        self.assertEqual(done.mart369_state, 'delivered')

        self._staff()
        body = self._get('/369mart/admin/orders').json()
        self.assertTrue(body['ok'])
        refs = [row['ref'] for row in body['orders']]
        self.assertIn(live.mart369_ref, refs)
        self.assertNotIn(done.mart369_ref, refs,
                         'a delivered order is not something to do')

    def test_the_longest_wait_is_at_the_top(self):
        """The default sort is the whole point of the screen."""
        first = self._order(ref='369M-OLD')
        second = self._order(ref='369M-NEW')
        first.mart369_placed_at = '2020-01-01 06:00:00'
        second.mart369_placed_at = '2020-01-02 06:00:00'

        self._staff()
        rows = self._get('/369mart/admin/orders').json()['orders']
        refs = [r['ref'] for r in rows if r['ref'] in ('369M-OLD', '369M-NEW')]
        self.assertEqual(refs, ['369M-OLD', '369M-NEW'])

    def test_the_list_can_be_searched_by_order_number(self):
        order = self._order(ref='369M-FINDME')
        self._order(ref='369M-OTHER')
        self._staff()
        rows = self._get('/369mart/admin/orders?q=FINDME').json()['orders']
        self.assertEqual([r['ref'] for r in rows], [order.mart369_ref])

    def test_a_page_says_how_many_there_are_in_all(self):
        """Without the total the screen cannot say whether Show more has
        anything behind it."""
        self._order(ref='369M-P1')
        self._order(ref='369M-P2')
        self._staff()
        body = self._get('/369mart/admin/orders?limit=1').json()
        self.assertEqual(len(body['orders']), 1)
        self.assertGreaterEqual(body['total'], 2)

    def test_the_tiles_count_what_the_board_counts(self):
        self._order()
        self._staff()
        body = self._get('/369mart/admin/orders/counts').json()
        board = self.env['sale.order'].mart369_order_dashboard()
        self.assertEqual(body['counts']['placed'], board['packing'])
        self.assertEqual(body['counts']['out'], board['out'])
        self.assertEqual(body['counts']['late'], board['late'])
        self.assertEqual(body['counts']['needs'], board['live'])

    # ------------------------------------------------------------ the ladder

    def test_the_button_is_labelled_for_this_order_s_own_flow(self):
        quick = self._order()
        express = self._order(
            items={str(self.express_product.id): 1}, mode='all', ref='369M-EXP')
        self._staff()
        rows = {r['ref']: r for r in self._get('/369mart/admin/orders').json()['orders']}
        self.assertEqual(rows[quick.mart369_ref]['next'],
                         {'state': 'packed', 'label': 'Start packing'})
        self.assertEqual(rows[express.mart369_ref]['next'],
                         {'state': 'shipped', 'label': 'Mark shipped'})

    def test_advance_walks_a_quick_order_down_its_own_ladder(self):
        order = self._order()
        self._staff()
        for expected in ('packed', 'out', 'delivered'):
            response = self._post(
                '/369mart/admin/orders/%s/advance' % order.mart369_ref)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['order']['state'], expected)

    def test_advance_ships_an_express_order_rather_than_packing_it(self):
        order = self._order(
            items={str(self.express_product.id): 1}, mode='all', ref='369M-EXP')
        self._staff()
        response = self._post('/369mart/admin/orders/%s/advance' % order.mart369_ref)
        self.assertEqual(response.json()['order']['state'], 'shipped')

    def test_moving_a_delivered_order_on_is_a_conflict(self):
        """Not a 400. The operator did nothing wrong - the screen was stale."""
        order = self._order()
        for __ in range(3):
            order.mart369_action_advance()
        self._staff()
        response = self._post('/369mart/admin/orders/%s/advance' % order.mart369_ref)
        self.assertEqual(response.status_code, 409)
        self.assertFalse(response.json()['ok'])

    def test_a_made_up_order_number_is_a_404(self):
        self._staff()
        self.assertEqual(
            self._get('/369mart/admin/orders/369M-NOPE').status_code, 404)
        self.assertEqual(
            self._post('/369mart/admin/orders/369M-NOPE/advance').status_code, 404)

    def test_an_unpaid_basket_is_not_an_order(self):
        draft = self._place(ref='369M-DRAFT')
        self.assertEqual(draft.mart369_state, 'draft')
        self._staff()
        self.assertEqual(
            self._get('/369mart/admin/orders/369M-DRAFT').status_code, 404)

    # ----------------------------------------------------------- cancelling

    def test_a_placed_order_can_be_cancelled_with_a_reason(self):
        order = self._order()
        self._staff()
        response = self._post(
            '/369mart/admin/orders/%s/cancel' % order.mart369_ref,
            {'reason': 'Item out of stock'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['order']['state'], 'cancelled')
        self.assertEqual(
            order.mart369_stamp_ids.filtered(lambda s: s.state == 'cancelled').note,
            'Item out of stock')

    def test_cancelling_a_packed_order_is_a_conflict(self):
        order = self._order()
        order.mart369_action_advance()
        self._staff()
        response = self._post(
            '/369mart/admin/orders/%s/cancel' % order.mart369_ref,
            {'reason': 'Store closed'})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(order.mart369_state, 'packed')

    def test_a_reason_nobody_offered_is_refused(self):
        """The reason lands on the customer's own timeline, so it is picked
        from a list rather than typed."""
        order = self._order()
        self._staff()
        for payload in ({}, {'reason': ''}, {'reason': 'because'}):
            response = self._post(
                '/369mart/admin/orders/%s/cancel' % order.mart369_ref, payload)
            self.assertEqual(response.status_code, 400)
        self.assertEqual(order.mart369_state, 'placed')

    def test_a_cancelled_order_offers_no_next_step(self):
        order = self._order()
        order._mart369_cancel(reason='Store closed')
        self._staff()
        body = self._get('/369mart/admin/orders/%s' % order.mart369_ref).json()
        self.assertIsNone(body['order']['next'])
        self.assertFalse(body['order']['canCancel'])

    # ------------------------------------------------------------ the drawer

    def test_the_drawer_carries_the_ladder_this_order_is_on(self):
        """So four steps are drawn with the right middle one, rather than the
        screen keeping its own copy of the flow."""
        order = self._order(
            items={str(self.express_product.id): 1}, mode='all', ref='369M-EXP')
        self._staff()
        body = self._get('/369mart/admin/orders/%s' % order.mart369_ref).json()
        self.assertEqual(body['order']['flow'],
                         ['placed', 'shipped', 'out', 'delivered'])

    def test_the_timeline_is_the_stamps_and_not_a_guess(self):
        order = self._order()
        order.mart369_action_advance()
        self._staff()
        body = self._get('/369mart/admin/orders/%s' % order.mart369_ref).json()
        self.assertEqual([s['state'] for s in body['order']['timeline']],
                         ['placed', 'packed'])
        self.assertTrue(all(s['at'] for s in body['order']['timeline']))

    def test_the_delivery_code_never_leaves_the_server(self):
        order = self._order()
        self._staff()
        response = self._get('/369mart/admin/orders/%s' % order.mart369_ref)
        body = response.json()
        self.assertIsNotNone(body['order']['otp']['issuedAt'],
                             'a paid order has been issued a code')
        self.assertIsNone(body['order']['otp']['usedAt'])
        # Neither the code nor the hash it is checked against, anywhere in the
        # payload - not just in the block that is meant to hold them.
        digest = order.sudo().mart369_otp_hash
        self.assertTrue(digest)
        self.assertNotIn(digest, response.text)
        self.assertNotIn('otp_hash', response.text)

    def test_the_invoice_is_the_consoles_own_route(self):
        """The shopper's invoice route is fenced to that shopper's own orders,
        so staff following it for anybody else would get a 404 and no clue
        why. This one answers 404 only because nothing has been invoiced."""
        order = self._order()
        self._staff()
        response = self._get('/369mart/admin/orders/%s/invoice' % order.mart369_ref)
        self.assertIn(response.status_code, (200, 404))
        if response.status_code == 404:
            self.assertIn('invoice', response.json()['error'].lower())

    def test_the_list_does_not_carry_the_drawer_s_extra_query(self):
        """`orderCount` costs a search per row, so it is the drawer's only."""
        self._order()
        self._staff()
        row = self._get('/369mart/admin/orders').json()['orders'][0]
        self.assertNotIn('orderCount', row['customer'])
        detail = self._get('/369mart/admin/orders/%s' % row['ref']).json()['order']
        self.assertGreaterEqual(detail['customer']['orderCount'], 1)
