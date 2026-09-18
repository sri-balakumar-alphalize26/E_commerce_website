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
