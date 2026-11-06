"""The staff Orders screens, worked like a marketplace seller's: the most
urgent order on top, a payment filter, bulk printing, removing an item that
ran out, a rider, and a delivery that did not happen.
"""

from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import Mart369OrderCase, Mart369OrderHttpCase


@tagged('post_install', '-at_install')
class TestOrderWorkbench(Mart369OrderCase):

    def _refs(self, **kwargs):
        page = self.env['sale.order'].mart369_admin_list(tab='all', **kwargs)
        return [row['ref'] for row in page['orders']]

    # ------------------------------------------------ urgent first, payment

    def test_most_urgent_first_and_the_payment_filter(self):
        paid = self._place()
        self._pay(paid)
        cash = self._place(ref='369M-TEST2')
        self._cash(cash)
        now = fields.Datetime.now()
        paid.sudo().mart369_due_at = now + timedelta(minutes=40)
        cash.sudo().mart369_due_at = now + timedelta(minutes=5)

        refs = self._refs(sort='due')
        self.assertLess(refs.index(cash.mart369_ref), refs.index(paid.mart369_ref),
                        'the promise nearest to breaking comes first')

        self.assertIn(cash.mart369_ref, self._refs(pay='cod'))
        self.assertNotIn(paid.mart369_ref, self._refs(pay='cod'))
        self.assertIn(paid.mart369_ref, self._refs(pay='prepaid'))
        self.assertNotIn(cash.mart369_ref, self._refs(pay='prepaid'))

    # ------------------------------------------------------------- printing

    def test_the_picklist_counts_each_product_once_across_orders(self):
        one = self._place()
        self._pay(one)
        two = self._place(ref='369M-TEST2', items={str(self.quick_product.id): 2})
        self._pay(two)
        groups = (one | two)._mart369_picklist()
        items = [i for g in groups for i in g['items']]
        mine = [i for i in items if i['name'] == self.quick_product.display_name]
        self.assertEqual(len(mine), 1, 'one line per product, not per order')
        self.assertEqual(mine[0]['qty'], 6)
        self.assertEqual(sorted(mine[0]['refs']), ['369M-TEST1', '369M-TEST2'])

    def test_a_slip_says_whether_to_collect_cash(self):
        paid = self._place()
        self._pay(paid)
        cash = self._place(ref='369M-TEST2')
        self._cash(cash)
        self.assertEqual(paid._mart369_print_payment()[0], 'paid')
        self.assertEqual(cash._mart369_print_payment(), ('collect', cash.amount_total))


@tagged('post_install', '-at_install')
class TestOrderPrintRoute(Mart369OrderHttpCase):

    def test_staff_print_slips_and_picklists_a_shopper_cannot(self):
        order = self._place()
        self._pay(order)
        url = '/369mart/admin/orders/print?kind=%s&refs=' + order.mart369_ref

        shopper = self.env['res.users'].sudo().create({
            'name': 'A Shopper', 'login': 'wb_shopper', 'password': 'wb_shopper',
            'group_ids': [(6, 0, [self.env.ref('base.group_portal').id])]})
        self.authenticate(shopper.login, 'wb_shopper')
        self.assertEqual(self.url_open(url % 'slips').status_code, 403)

        self.authenticate('admin', 'admin')
        for kind in ('slips', 'picklist'):
            res = self.url_open(url % kind)
            self.assertEqual(res.status_code, 200, kind)
            self.assertIn('application/pdf', res.headers['Content-Type'])
            self.assertIn(order.mart369_ref.encode(), res.content, kind)
        self.assertEqual(self.url_open(url % 'labels').status_code, 400)
        self.assertEqual(self.url_open(
            '/369mart/admin/orders/print?kind=slips&refs=369M-NOPE').status_code, 404)


@tagged('post_install', '-at_install')
class TestRemoveAnItem(Mart369OrderCase):

    def setUp(self):
        super().setUp()
        self.apples = self._mart369_product('Test Apples', 30.0)

    def _two_lines(self, ref='369M-TEST1'):
        return self._place(ref=ref, items={str(self.quick_product.id): 4, str(self.apples.id): 2})

    def _line(self, order, tmpl):
        return order.order_line.filtered(lambda l: l.product_id.product_tmpl_id == tmpl)

    def _wallet(self):
        return self.env['loyalty.card'].sudo()._mart369_wallet(self.partner)

    def test_a_paid_order_gets_the_item_back_in_the_wallet_at_once(self):
        order = self._two_lines()
        self._pay(order)
        line = self._line(order, self.apples)
        value = order.currency_id.round(line.price_total)
        before = self._wallet().points

        result = self.env['sale.order'].mart369_admin_remove_line(order.mart369_ref, line.id)

        self.assertEqual(result['refund'], value)
        self.assertAlmostEqual(self._wallet().points, before + value, places=2)
        self.assertEqual(line.product_uom_qty, 0, 'kept on the order at quantity 0')
        self.assertEqual(line.mart369_removed_qty, 2)
        detail = result['order']
        self.assertNotIn('Test Apples', [i['name'] for i in detail['items']])
        self.assertEqual(detail['removed'][0]['refund'], value)
        self.assertFalse(detail['canRemove'], 'one item left: that is a cancel, not a removal')
        self.assertEqual(order._mart369_serialize()['removed'][0]['qty'], 2,
                         "the customer's order page says so too")
        if order.invoice_ids.filtered(lambda m: m.move_type == 'out_invoice' and m.state == 'posted'):
            self.assertTrue(order.invoice_ids.filtered(
                lambda m: m.move_type == 'out_refund' and m.state == 'posted'),
                'the posted invoice gets a credit note for the line')

        with self.assertRaises(UserError):
            self.env['sale.order'].mart369_admin_remove_line(order.mart369_ref, line.id)
        self.assertAlmostEqual(self._wallet().points, before + value, places=2,
                               msg='a second click refunds nothing')
        last = self._line(order, self.quick_product)
        with self.assertRaises(UserError):
            self.env['sale.order'].mart369_admin_remove_line(order.mart369_ref, last.id)

    def test_cash_on_delivery_owes_less_instead(self):
        order = self._two_lines()
        tx = self._cash(order)
        before = self._wallet().points
        line = self._line(order, self.apples)

        result = self.env['sale.order'].mart369_admin_remove_line(order.mart369_ref, line.id)

        self.assertEqual(result['refund'], 0.0, 'nothing was paid, nothing to refund')
        self.assertAlmostEqual(self._wallet().points, before, places=2)
        self.assertAlmostEqual(tx.amount, order.amount_total, places=2,
                               msg='the cash to collect follows the new total')

    def test_not_once_it_has_left_the_store(self):
        order = self._two_lines()
        self._pay(order)
        while order.mart369_state != 'out':
            order.mart369_action_advance()
        with self.assertRaises(UserError):
            self.env['sale.order'].mart369_admin_remove_line(
                order.mart369_ref, self._line(order, self.apples).id)


@tagged('post_install', '-at_install')
class TestRiderAndFailedDelivery(Mart369OrderCase):

    def setUp(self):
        super().setUp()
        self.rider = self.env['res.users'].sudo().create({
            'name': 'Arun Rider', 'login': 'wb_rider',
            'group_ids': [(6, 0, [self.env.ref('base.group_user').id,
                                  self.env.ref('mart369_roles.group_rider').id])]})
        self.Order = self.env['sale.order']

    def _out(self, cash=False):
        order = self._place()
        if cash:
            self._cash(order)
        else:
            self._pay(order)
        while order.mart369_state != 'out':
            order.mart369_action_advance()
        return order

    def _wallet(self):
        return self.env['loyalty.card'].sudo()._mart369_wallet(self.partner).points

    def test_only_a_rider_can_be_given_an_order(self):
        order = self._out()
        detail = self.Order.mart369_admin_set_rider(order.mart369_ref, self.rider.id)
        self.assertEqual(detail['rider'], 'Arun Rider')
        self.assertIn(self.rider.id, [r['id'] for r in detail['riders']])
        with self.assertRaises(UserError):
            self.Order.mart369_admin_set_rider(order.mart369_ref, self.other.id)
        self.assertEqual(self.Order.mart369_admin_set_rider(order.mart369_ref, False)['rider'], '')

    def test_try_again_counts_the_attempt_and_changes_the_code(self):
        order = self._out()
        code = order.sudo().mart369_otp_code
        result = self.Order.mart369_admin_failed(order.mart369_ref, 'Customer not reachable', 'retry')
        self.assertEqual(result['refund'], 0.0)
        self.assertEqual(order.mart369_state, 'out', 'still out for delivery')
        self.assertEqual(order.mart369_attempts, 1)
        self.assertEqual(result['order']['failedReason'], 'Customer not reachable')
        new = order.sudo().mart369_otp_code
        self.assertTrue(new and new != code, 'a fresh door code')
        order.mart369_action_deliver(new)
        self.assertEqual(order.mart369_state, 'delivered')

    def test_return_to_store_refunds_what_was_paid_to_the_wallet(self):
        order = self._out()
        before = self._wallet()
        paid = order.mart369_paid
        result = self.Order.mart369_admin_failed(order.mart369_ref, 'Wrong address', 'return')
        self.assertEqual(result['refund'], paid)
        self.assertAlmostEqual(self._wallet(), before + paid, places=2)
        self.assertEqual(order.mart369_state, 'cancelled')
        self.assertFalse(order.mart369_slot_key, 'the slot is freed')
        with self.assertRaises(UserError):
            self.Order.mart369_admin_failed(order.mart369_ref, 'Wrong address', 'return')
        self.assertAlmostEqual(self._wallet(), before + paid, places=2,
                               msg='a closed order cannot be refunded twice')

    def test_a_cash_order_returned_has_nothing_to_refund(self):
        order = self._out(cash=True)
        before = self._wallet()
        result = self.Order.mart369_admin_failed(order.mart369_ref, 'Customer refused the order', 'return')
        self.assertEqual(result['refund'], 0.0)
        self.assertAlmostEqual(self._wallet(), before, places=2)
        tx = self.env['payment.transaction'].sudo().search(
            [('mart369_order_ref', '=', order.mart369_ref)])
        self.assertEqual(set(tx.mapped('state')), {'cancel'}, 'the cash is not collected')

    def test_only_an_order_out_for_delivery_can_fail(self):
        order = self._place()
        self._pay(order)
        with self.assertRaises(UserError):
            self.Order.mart369_admin_failed(order.mart369_ref, 'Wrong address', 'retry')
