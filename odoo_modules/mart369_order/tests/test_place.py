"""Placing an order.

The money tests are the point of this file. Everything else in the module can be
rebuilt if it is wrong; a total that disagrees with the one the customer was
shown cannot be, because by then they have paid it.
"""

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import Mart369OrderCase


@tagged('post_install', '-at_install')
class TestMart369Place(Mart369OrderCase):

    # ------------------------------------------------------------- the money

    def test_the_order_total_matches_the_bill_to_the_paisa(self):
        """The whole reason this module prices anything."""
        body = self._basket()
        bill = self.env['mart369.cart']._mart369_bill(body['items'])
        order = self._place()
        self.assertEqual(
            order.currency_id.compare_amounts(order.amount_total, bill['total']), 0,
            'the order and the cart page must agree exactly')

    def test_the_delivery_fee_becomes_a_line_rather_than_a_number(self):
        # 4 x 50 = 200, under the 499 free-delivery line, so 30 is charged.
        order = self._place()
        fees = order.order_line.filtered(lambda l: l.mart369_kind == 'fee')
        self.assertEqual(len(fees), 1)
        self.assertEqual(fees.price_unit, 30.0)
        self.assertEqual(order.amount_total, 230.0)

    def test_a_basket_over_the_free_delivery_line_pays_no_fee(self):
        order = self._place(items={str(self.quick_product.id): 12}, ref='369M-FREE')
        self.assertFalse(order.order_line.filtered(lambda l: l.mart369_kind == 'fee'))
        self.assertEqual(order.amount_total, 600.0)

    def test_the_browsers_own_total_is_not_read_at_all(self):
        """The app may claim anything; it changes nothing."""
        order = self._place(total=1.0, paid=1.0, bill={'total': 1.0})
        self.assertEqual(order.amount_total, 230.0,
                         'priced from Odoo, not from what was posted')

    def test_a_basket_below_the_quick_minimum_is_refused(self):
        with self.assertRaises(UserError):
            self._place(items={str(self.quick_product.id): 1}, ref='369M-SMALL')

    # -------------------------------------------------------------- retrying

    def test_placing_twice_with_one_order_number_places_once(self):
        """The app builds its order number from a timestamp slice, which
        repeats on a double tap."""
        first = self._place()
        second = self._place()
        self.assertEqual(first, second, 'the same record, not a second order')
        self.assertEqual(
            self.env['sale.order'].search_count([('mart369_ref', '=', '369M-TEST1')]), 1)

    def test_a_draft_is_rewritten_rather_than_duplicated(self):
        """The app asks for the order before choosing how to pay, because
        whether cash is allowed is a question about the order - so the
        customer can still go back and change the slot afterwards."""
        first = self._place(items={str(self.quick_product.id): 4})
        self.assertEqual(first.mart369_state, 'draft')
        again = self._place(items={str(self.quick_product.id): 7})
        self.assertEqual(first, again, 'the same draft, rewritten')
        self.assertEqual(
            sum(again.order_line.filtered(
                lambda l: not l.mart369_kind and not l.is_delivery).mapped('product_uom_qty')),
            7.0)

    def test_an_order_already_paid_for_is_never_rewritten(self):
        """Past the draft, the same number is a retry - someone may already
        be packing it."""
        order = self._place()
        self._pay(order)
        self.assertEqual(order.mart369_state, 'placed')
        again = self._place(items={str(self.quick_product.id): 11})
        self.assertEqual(order, again)
        self.assertEqual(
            sum(again.order_line.filtered(
                lambda l: not l.mart369_kind and not l.is_delivery).mapped('product_uom_qty')),
            4.0, 'the basket it was paid for, untouched')

    # ---------------------------------------------------- cash on delivery

    def _cash(self, order):
        """A cash payment the way /pay makes one: pending, never confirmed
        by anyone before the door."""
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

    def test_a_cash_order_is_placed_before_the_money_arrives(self):
        """Nobody confirms a cash payment before the door. Waiting for one
        left the order a draft: in no list, and in front of nobody who
        could pack it."""
        order = self._place()
        self._cash(order)
        self.assertEqual(order.mart369_state, 'placed')

    def test_a_cash_order_is_not_recorded_as_paid(self):
        """It is owed, not paid - the receipt says "to pay on delivery"."""
        order = self._place()
        self._cash(order)
        self.assertEqual(order.mart369_paid, 0.0)

    def test_collecting_the_cash_is_what_marks_it_paid(self):
        order = self._place()
        tx = self._cash(order)
        tx._mart369_mark_cod_collected()
        self.assertEqual(tx.state, 'done')
        self.assertEqual(
            order.currency_id.compare_amounts(order.mart369_paid, order.amount_total), 0)

    # ------------------------------------------------------------ delivery

    def test_an_order_is_given_a_delivery_method(self):
        """Without one, Odoo refuses cash on delivery on every basket: the
        rule is the carrier's, and an order with no carrier has no rule."""
        order = self._place()
        self.assertTrue(order.carrier_id,
                        'an order nobody is delivering cannot be paid for in cash')

    def test_one_customer_cannot_take_over_anothers_order_number(self):
        self._place()
        with self.assertRaises(UserError):
            self.env['sale.order']._mart369_place(
                self.other.partner_id, self._basket())

    # ------------------------------------------------------------- ownership

    def test_an_address_belonging_to_someone_else_is_not_found(self):
        theirs = self.env['res.partner'].sudo().create({
            'name': 'Their House',
            'parent_id': self.other.partner_id.id,
            'type': 'other',
            'street': '9 Elsewhere',
        })
        with self.assertRaises(UserError):
            self._place(address_id=theirs.id, ref='369M-THEIRS')

    def test_a_made_up_address_is_not_found(self):
        with self.assertRaises(UserError):
            self._place(address_id=99999999, ref='369M-NOPE')

    # ---------------------------------------------------------------- basket

    def test_the_basket_lines_are_what_the_app_gets_back(self):
        order = self._place()
        payload = order._mart369_serialize()
        self.assertEqual(payload['items'], [[str(self.quick_product.id), 4]])
        self.assertIn(str(self.quick_product.id), payload['snap'])
        self.assertEqual(payload['snap'][str(self.quick_product.id)]['price'], 50.0)

    def test_the_fee_line_stays_out_of_the_basket(self):
        """It is a line on the order, but the app has always shown it in the
        bill rather than the basket."""
        order = self._place()
        payload = order._mart369_serialize()
        self.assertEqual(len(payload['items']), 1, 'only the product')
        self.assertEqual(payload['bill']['fees'], 30.0)

    def test_an_order_number_is_required(self):
        with self.assertRaises(UserError):
            self.env['sale.order']._mart369_place(self.partner, {'items': {}})

    def test_an_empty_basket_is_refused(self):
        with self.assertRaises(UserError):
            self._place(items={}, ref='369M-EMPTY')

    def test_a_basket_carried_as_pairs_is_understood_too(self):
        """A placed order holds its items as [[id, qty]]; the cart holds
        {id: qty}. Both arrive here."""
        order = self._place(
            items=[[str(self.quick_product.id), 4]], ref='369M-PAIRS')
        self.assertEqual(order.amount_total, 230.0)

    # ------------------------------------------------------------ the states

    def test_a_new_order_is_not_placed_until_it_is_paid_for(self):
        order = self._place()
        self.assertEqual(order.mart369_state, 'draft')
        self.assertFalse(order.mart369_stamp_ids,
                         'nothing has happened to it yet')
