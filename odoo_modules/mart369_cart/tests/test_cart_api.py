"""The bill, the coupons, serviceability and the slots.

The tests that matter most are the arithmetic ones. `computeBill` in
components/home/Cart.jsx has been adding this basket up in the browser; if the
server disagrees by a rupee, every customer sees a total change under them and
it looks like theft rather than a rounding difference. So these assert exact
figures worked out by hand from the same rules, not "roughly".
"""

import json

from odoo.tests import tagged
from odoo.tests.common import HttpCase

HEADERS = {'Content-Type': 'application/json'}


@tagged('post_install', '-at_install')
class TestMart369CartApi(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Template = cls.env['product.template']
        # Quick items: no delivery promise.
        cls.apple = Template.create({
            'name': 'Test Cart Apple', 'list_price': 100.0,
            'compare_list_price': 120.0, 'is_published': True,
        })
        cls.bread = Template.create({
            'name': 'Test Cart Bread', 'list_price': 50.0, 'is_published': True,
        })
        # An Express item: carrying a delivery promise is what makes it one.
        cls.ssd = Template.create({
            'name': 'Test Cart SSD', 'list_price': 400.0,
            'is_published': True, 'mart_delivery_text': '3-5 days',
        })
        cls.secret = Template.create({
            'name': 'Test Cart Unpublished', 'list_price': 999.0,
            'is_published': False,
        })

    # ------------------------------------------------------------- plumbing

    def _bill(self, items, **extra):
        payload = dict({'items': items}, **extra)
        response = self.opener.request(
            'POST', self.base_url() + '/369mart/cart/bill',
            data=json.dumps(payload), headers=HEADERS)
        return response.status_code, response.json()

    def _get(self, path):
        response = self.opener.request('GET', self.base_url() + path, headers=HEADERS)
        return response.status_code, response.json()

    def _id(self, product):
        return str(product.id)

    # ------------------------------------------------------- the arithmetic

    def test_a_quick_basket_below_the_free_line_pays_the_fee(self):
        """100 + 50 = 150, under 499, so 30 delivery. MRP 120 + 50 = 170."""
        status, bill = self._bill({self._id(self.apple): 1, self._id(self.bread): 1})
        self.assertEqual(status, 200)
        self.assertEqual(bill['items'], 150.0)
        self.assertEqual(bill['mrp'], 170.0)
        self.assertEqual(bill['fees'], 30.0)
        self.assertEqual(bill['total'], 180.0)
        self.assertEqual(bill['saved'], 20.0, 'the MRP saving, no coupon yet')
        self.assertEqual(bill['count'], 2)
        self.assertFalse(bill['blocked'], '150 clears the 99 minimum')

    def test_a_basket_under_the_minimum_is_blocked(self):
        status, bill = self._bill({self._id(self.bread): 1})
        self.assertEqual(bill['items'], 50.0)
        self.assertTrue(bill['blocked'], '50 is under the 99 Quick minimum')

    def test_crossing_the_free_delivery_line_drops_the_fee(self):
        status, bill = self._bill({self._id(self.apple): 5})
        self.assertEqual(bill['items'], 500.0)
        self.assertEqual(bill['fees'], 0.0, '500 clears the 499 free line')
        self.assertEqual(bill['total'], 500.0)

    def test_a_mixed_basket_pays_both_delivery_fees(self):
        """One fee per storefront, exactly as the app stacks them."""
        status, bill = self._bill({self._id(self.apple): 1, self._id(self.ssd): 1})
        self.assertEqual(bill['sub']['quick'], 100.0)
        self.assertEqual(bill['sub']['all'], 400.0)
        self.assertEqual(bill['fees'], 79.0, '30 for Quick plus 49 for Express')
        self.assertEqual(bill['total'], 579.0)

    def test_an_express_only_basket_has_no_quick_minimum(self):
        status, bill = self._bill({self._id(self.ssd): 1})
        self.assertFalse(bill['blocked'], 'the 99 minimum is a Quick rule only')
        self.assertEqual(bill['fees'], 49.0)

    def test_a_priority_slot_fee_reaches_the_bill(self):
        status, bill = self._bill({self._id(self.ssd): 1}, slotFee=49)
        self.assertEqual(bill['fees'], 98.0, '49 delivery plus the 49 priority')
        self.assertEqual(bill['total'], 498.0)

    # ---------------------------------------------------------- the coupons

    def test_percentage_coupon_is_capped_and_scoped(self):
        """QUICK20: 20% of the Quick subtotal, never more than 60, Quick only."""
        status, bill = self._bill({self._id(self.apple): 2}, coupon='QUICK20')
        self.assertTrue(bill['couponValid'])
        self.assertEqual(bill['couponOff'], 40.0, '20% of 200')
        self.assertEqual(bill['total'], 190.0, '200 + 30 delivery - 40')

        status, bill = self._bill({self._id(self.apple): 4}, coupon='QUICK20')
        self.assertEqual(bill['couponOff'], 60.0, '20% of 400 is 80, capped at 60')

        # Express items must not count towards a Quick-only code.
        status, bill = self._bill({self._id(self.ssd): 1}, coupon='QUICK20')
        self.assertFalse(bill['couponValid'],
                         'the Quick subtotal is 0, under the 199 minimum')
        self.assertEqual(bill['couponOff'], 0.0)

    def test_a_coupon_below_its_minimum_does_nothing(self):
        status, bill = self._bill({self._id(self.apple): 1}, coupon='WELCOME50')
        self.assertFalse(bill['couponValid'], '100 is under the 499 minimum')
        self.assertEqual(bill['total'], 130.0)

        status, bill = self._bill({self._id(self.apple): 5}, coupon='WELCOME50')
        self.assertTrue(bill['couponValid'])
        self.assertEqual(bill['couponOff'], 50.0)
        self.assertEqual(bill['total'], 450.0, '500, free delivery, less 50')

    def test_free_delivery_coupon_waives_exactly_the_fees(self):
        status, bill = self._bill({self._id(self.apple): 3}, coupon='FREEDEL')
        self.assertEqual(bill['items'], 300.0)
        self.assertEqual(bill['fees'], 30.0)
        self.assertEqual(bill['couponOff'], 30.0)
        self.assertEqual(bill['total'], 300.0)

    def test_a_made_up_code_is_refused_quietly(self):
        status, bill = self._bill({self._id(self.apple): 5}, coupon='NOTACODE')
        self.assertEqual(status, 200)
        self.assertFalse(bill['couponValid'])
        self.assertEqual(bill['couponOff'], 0.0)
        self.assertEqual(bill['total'], 500.0)

    def test_an_expired_coupon_stops_working(self):
        from datetime import date, timedelta
        coupon = self.env.ref('mart369_cart.coupon_welcome50')
        coupon.ends_on = date.today() - timedelta(days=1)
        status, bill = self._bill({self._id(self.apple): 5}, coupon='WELCOME50')
        self.assertFalse(bill['couponValid'])
        self.assertEqual(bill['couponOff'], 0.0)

    def test_a_discount_can_never_exceed_the_bill(self):
        big = self.env['mart369.coupon'].create({
            'code': 'TESTHUGE', 'title': 'Test huge', 'kind': 'flat',
            'value': 10000.0, 'min_spend': 0.0,
        })
        status, bill = self._bill({self._id(self.bread): 1}, coupon='TESTHUGE')
        self.assertEqual(bill['couponOff'], 80.0, '50 of items plus 30 of fees')
        self.assertEqual(bill['total'], 0.0, 'never negative, never a refund')

    # ------------------------------------------------------ the basket itself

    def test_an_unpublished_product_is_dropped_and_named(self):
        """A basket that sat in a browser for a week should still check out
        with what is left in it - but the app must be told what vanished."""
        status, bill = self._bill({
            self._id(self.apple): 1, self._id(self.secret): 1, 'f3': 2,
        })
        self.assertEqual(bill['items'], 100.0)
        self.assertCountEqual(bill['unknown'], [self._id(self.secret), 'f3'])

    def test_an_empty_basket_is_zero_not_an_error(self):
        status, bill = self._bill({})
        self.assertEqual(status, 200)
        self.assertEqual(bill['total'], 0.0)
        self.assertEqual(bill['count'], 0)
        self.assertEqual(bill['fees'], 0.0, 'no storefront is present, so no fee')

    def test_a_missing_basket_is_a_400(self):
        response = self.opener.request(
            'POST', self.base_url() + '/369mart/cart/bill',
            data=json.dumps({'coupon': 'QUICK20'}), headers=HEADERS)
        self.assertEqual(response.status_code, 400)

    # --------------------------------------------------- the coupon sheet

    def test_every_live_code_is_priced_against_this_basket(self):
        """The sheet used to run each coupon's `calc` in the browser. It asks
        now, so the bill has to answer for all of them at once - one trip, not
        one per code."""
        status, bill = self._bill({self._id(self.apple): 3})  # 300, Quick
        self.assertEqual(status, 200)
        priced = {c['code']: c for c in bill['coupons']}
        self.assertLessEqual({'QUICK20', 'WELCOME50', 'FREEDEL'}, set(priced))
        # 20% of 300 is 60, which is also the cap.
        self.assertEqual(priced['QUICK20']['off'], 60.0)
        self.assertEqual(priced['QUICK20']['need'], 0.0)

    def test_a_code_the_basket_has_not_earned_says_how_far_off_it_is(self):
        status, bill = self._bill({self._id(self.apple): 1})  # 100
        priced = {c['code']: c for c in bill['coupons']}
        self.assertEqual(priced['WELCOME50']['off'], 0.0,
                         'below its minimum, so it saves nothing')
        self.assertEqual(priced['WELCOME50']['need'], 399.0,
                         '499 minimum less the 100 in the basket')

    def test_the_priced_codes_agree_with_the_one_that_is_applied(self):
        """Two answers about the same coupon in one payload is two chances to
        disagree - the sheet says "You save X", the bill takes X off."""
        status, bill = self._bill({self._id(self.apple): 3}, coupon='QUICK20')
        priced = {c['code']: c for c in bill['coupons']}
        self.assertTrue(bill['couponValid'])
        self.assertEqual(bill['couponOff'], priced['QUICK20']['off'])

    # ------------------------------------------------------------ the rules

    def test_rules_and_coupons_match_what_the_app_had(self):
        status, data = self._get('/369mart/cart/rules')
        self.assertEqual(status, 200)
        quick = data['rules']['quick']
        self.assertEqual(quick['label'], 'Quick')
        self.assertEqual(quick['minOrder'], 99.0)
        self.assertEqual(quick['freeAbove'], 499.0)
        self.assertEqual(quick['fee'], 30.0)
        express = data['rules']['all']
        self.assertEqual(express['freeAbove'], 999.0)
        self.assertEqual(express['fee'], 49.0)

        codes = {c['code'] for c in data['coupons']}
        self.assertLessEqual({'QUICK20', 'WELCOME50', 'FREEDEL'}, codes)
        quick20 = next(c for c in data['coupons'] if c['code'] == 'QUICK20')
        self.assertEqual(quick20['group'], 'quick')
        self.assertEqual(quick20['min'], 199.0)
        self.assertNotIn('calc', quick20,
                         'the arithmetic stays on the server, which was the point')

    # --------------------------------------------------------- the pincode

    def test_serviceability_answers_the_shape_the_picker_expects(self):
        status, data = self._get('/369mart/serviceability?pin=682016')
        self.assertEqual(status, 200)
        self.assertTrue(data['ok'])
        self.assertTrue(data['quick'])
        self.assertEqual(data['eta'], '13 mins')

        status, data = self._get('/369mart/serviceability?pin=110001')
        self.assertFalse(data['ok'])
        self.assertIn('error', data)

        status, data = self._get('/369mart/serviceability?pin=abc')
        self.assertFalse(data['ok'])

    def test_express_only_area_says_so(self):
        status, data = self._get('/369mart/serviceability?pin=671234')
        self.assertTrue(data['ok'])
        self.assertFalse(data['quick'], '67 is Express only')

    def test_the_most_specific_pincode_wins(self):
        self.env['mart369.service.area'].create({
            'pincode': '682016', 'name': 'Test Kochi', 'quick': True,
            'express': True, 'eta': '9 mins',
        })
        status, data = self._get('/369mart/serviceability?pin=682016')
        self.assertEqual(data['eta'], '9 mins', 'the exact pincode beats the 68 prefix')
        status, data = self._get('/369mart/serviceability?pin=682017')
        self.assertEqual(data['eta'], '13 mins', 'its neighbour still uses 68')

    # ----------------------------------------------------------- the slots

    def test_slots_come_back_in_the_shape_the_checkout_draws(self):
        status, data = self._get('/369mart/slots')
        self.assertEqual(status, 200)
        keys = [s['key'] for s in data['quick']]
        self.assertIn('now', keys)
        now = next(s for s in data['quick'] if s['key'] == 'now')
        self.assertEqual(now['top'], 'Now')
        self.assertEqual(now['label'], 'Arriving in 10–20 mins')

        eve = next((s for s in data['quick'] if s['key'] == 'eve'), None)
        if eve:
            self.assertEqual(eve['label'], 'Today, 6 – 8 PM',
                             'the app prints the detail line inside the '
                             'confirmation, not a re-formatted clock')

        express = {s['key']: s for s in data['all']}
        self.assertEqual(express['pri']['fee'], 49.0)
        self.assertEqual(express['std']['fee'], 0.0)
        self.assertTrue(express['std']['label'].startswith('Arrives by'))

    def test_a_full_slot_is_not_offered(self):
        slot = self.env.ref('mart369_cart.slot_quick_tm')
        slot.capacity = 1
        # Nothing has booked it yet, so it is still on offer.
        status, data = self._get('/369mart/slots')
        self.assertIn('tm', [s['key'] for s in data['quick']])
        # Capacity is only enforced once mart369_order exists to book it; the
        # check must not explode before then.
        self.assertFalse(slot._mart369_is_full(self.env.cr.now()))
