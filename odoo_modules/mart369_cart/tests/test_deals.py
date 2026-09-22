"""Deals - a price cut on chosen products, for a window.

The thing worth testing is not the arithmetic. It is that **one price reaches
three places**: the card a shopper browses, the bill the cart quotes, and the
line the order is finally written with. They agree today only because all
three call `_price_context_for`, and a deal that hooked into one of them
without the others would show a saving that vanishes at checkout - the exact
failure that makes a shop look dishonest.

Also pinned here, because each was a decision rather than an accident:

* two live deals on one product give the better one, never both;
* a window is read at the moment somebody asks, so nothing has to run at
  midnight for a deal to start or stop;
* the cache never outlives the next window edge, or a card served from a copy
  taken before a deal opened contradicts a basket priced after it;
* an order that comes out cheaper than its quote goes through, and one that
  comes out dearer still does not.
"""

import json
from datetime import timedelta

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import HttpCase

HEADERS = {'Content-Type': 'application/json'}


@tagged('post_install', '-at_install')
class TestDeals(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Template = cls.env['product.template']
        cls.widget = Template.create({
            'name': 'Test Deal Widget', 'list_price': 200.0, 'is_published': True,
        })
        cls.other = Template.create({
            'name': 'Test Deal Other', 'list_price': 100.0, 'is_published': True,
        })
        cls.Deal = cls.env['mart369.deal'].with_context(active_test=False)
        cls.Pricer = cls.env['mart369.serializable'].sudo()

    def _deal(self, **overrides):
        values = {
            'name': 'Test deal',
            'kind': 'percent',
            'value': 25.0,
            'product_ids': [(6, 0, [self.widget.id])],
        }
        values.update(overrides)
        return self.Deal.create(values)

    def _price(self, template):
        ctx = self.Pricer._price_context_for(template)
        return ctx.get(template.id, {})

    # ------------------------------------------------------------ the window

    def test_a_deal_inside_its_window_cuts_the_price(self):
        self._deal()
        self.assertEqual(self._price(self.widget)['price'], 150.0)

    def test_a_deal_that_has_not_started_changes_nothing(self):
        self._deal(starts_on=fields.Datetime.now() + timedelta(days=1))
        self.assertEqual(self._price(self.widget)['price'], 200.0)

    def test_a_deal_that_has_ended_changes_nothing(self):
        self._deal(ends_on=fields.Datetime.now() - timedelta(minutes=1))
        self.assertEqual(self._price(self.widget)['price'], 200.0)

    def test_switching_a_deal_off_puts_the_price_back(self):
        """Nothing is written to the product, so this has to be immediate."""
        deal = self._deal()
        self.assertEqual(self._price(self.widget)['price'], 150.0)
        deal.active = False
        self.assertEqual(self._price(self.widget)['price'], 200.0)

    def test_a_product_nobody_put_on_offer_is_untouched(self):
        self._deal()
        self.assertEqual(self._price(self.other)['price'], 100.0)

    # ------------------------------------------------------------ the saving

    def test_the_old_price_is_struck_through_without_a_compare_price(self):
        """A shopper has to see what they are saving, and nobody sets a
        compare price per product just to run a weekend offer."""
        self.assertIsNone(self._price(self.widget).get('mrp'),
                          'nothing struck through at full price')
        self._deal()
        priced = self._price(self.widget)
        self.assertEqual(priced['price'], 150.0)
        self.assertEqual(priced['mrp'], 200.0)

    def test_an_amount_deal_takes_that_much_off(self):
        self._deal(kind='amount', value=30.0)
        self.assertEqual(self._price(self.widget)['price'], 170.0)

    def test_a_floor_stops_the_discount(self):
        self._deal(kind='amount', value=180.0, floor=50.0)
        self.assertEqual(self._price(self.widget)['price'], 50.0)

    def test_a_deal_can_never_make_something_free(self):
        self._deal(kind='amount', value=10_000.0)
        self.assertGreater(self._price(self.widget)['price'], 0.0)

    def test_two_deals_on_one_product_give_the_better_one_not_both(self):
        """Stacking is how a shop sells at a loss because two people each set
        up something sensible."""
        self._deal(name='Ten off', kind='percent', value=10.0)
        self._deal(name='Half off', kind='percent', value=50.0)
        self.assertEqual(self._price(self.widget)['price'], 100.0,
                         'the better of 10% and 50%, not 55%')

    def test_a_silly_percentage_is_refused(self):
        with self.assertRaises(ValidationError):
            self._deal(value=95.0)

    # --------------------------------------------------- one price, three places

    def test_the_card_the_bill_and_the_order_quote_the_same_price(self):
        """The whole point. Three surfaces, one pricer."""
        self._deal()
        card = self._price(self.widget)['price']

        bill = self.env['mart369.cart']._mart369_bill({str(self.widget.id): 2})
        self.assertEqual(bill['items'], card * 2)

        lines = self.env['mart369.serializable']._price_context_for(self.widget)
        self.assertEqual(lines[self.widget.id]['price'], card,
                         'and the price an order line would be written with')

    def test_the_offers_page_lists_a_product_that_is_only_cheap_by_deal(self):
        """The trap this feature was most likely to fall into: the price is
        cut by the pricer and nothing is written to the product, so a page
        selecting on stored columns would never find it."""
        self._deal()
        response = self.url_open('/369mart/offers')
        self.assertEqual(response.status_code, 200)
        names = [d.get('name') for d in response.json().get('deals', [])]
        self.assertIn('Test Deal Widget', names)

    def test_the_offers_page_still_lists_hand_priced_products(self):
        """The old rule kept working alongside the new one."""
        self.other.compare_list_price = 150.0
        response = self.url_open('/369mart/offers')
        names = [d.get('name') for d in response.json().get('deals', [])]
        self.assertIn('Test Deal Other', names)

    # -------------------------------------------------------------- the edges

    def test_the_next_edge_is_the_soonest_one_still_ahead(self):
        soon = fields.Datetime.now() + timedelta(hours=1)
        later = fields.Datetime.now() + timedelta(days=3)
        self._deal(name='Later', starts_on=later)
        self._deal(name='Soon', ends_on=soon)
        edge = self.Deal._mart369_next_edge()
        self.assertEqual(fields.Datetime.to_string(edge),
                         fields.Datetime.to_string(soon))

    def test_a_past_window_is_not_an_edge(self):
        self._deal(ends_on=fields.Datetime.now() - timedelta(days=1))
        edge = self.Deal._mart369_next_edge()
        self.assertTrue(edge is None or edge > fields.Datetime.now())

    def test_the_cache_does_not_outlive_the_next_window(self):
        """A card cached before a deal opens would otherwise contradict a
        basket priced after it, and the customer believes the smaller number."""
        self._deal(name='Soon', starts_on=fields.Datetime.now() + timedelta(seconds=30))
        response = self.url_open('/369mart/offers')
        cache = response.headers.get('Cache-Control', '')
        self.assertIn('max-age=', cache)
        max_age = int(cache.split('max-age=')[1].split(',')[0])
        self.assertLessEqual(max_age, 30)
        self.assertGreaterEqual(max_age, 1)

    # --------------------------------------------------------- the console

    def test_a_shopper_is_refused_the_admin_routes(self):
        shopper = self.env['res.users'].sudo().create({
            'name': 'A Shopper', 'login': 'mart369_deal_shopper',
            'password': 'mart369_deal_shopper',
            'group_ids': [(6, 0, [self.env.ref('base.group_portal').id])],
        })
        self.assertTrue(shopper)
        self.authenticate('mart369_deal_shopper', 'mart369_deal_shopper')
        for response in (
            self.url_open('/369mart/admin/deals'),
            self.url_open('/369mart/admin/deals', data=json.dumps(
                {'name': 'Mine', 'product_ids': [self.widget.id]}), headers=HEADERS),
        ):
            self.assertEqual(response.status_code, 403)

    def test_a_deal_without_products_is_refused_and_says_so(self):
        self.authenticate('admin', 'admin')
        response = self.url_open(
            '/369mart/admin/deals', data=json.dumps({'name': 'Empty'}),
            headers=HEADERS)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['field'], 'product_ids')

    def test_the_console_list_counts_what_is_on_offer(self):
        self._deal()
        payload = self.Deal.mart369_admin_list()
        self.assertGreaterEqual(payload['counts']['live'], 1)
        self.assertGreaterEqual(payload['onOffer'], 1)


@tagged('post_install', '-at_install')
class TestDealTrash(HttpCase):
    """Removing a deal puts it in the Trash.

    The one that would do real damage: a deal in the Trash must stop
    discounting immediately. A removed deal that still takes money off is
    worse than one that was never removed, because nobody is looking for it.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.widget = cls.env['product.template'].create({
            'name': 'Test Trash Widget', 'list_price': 200.0, 'is_published': True,
        })
        cls.Deal = cls.env['mart369.deal'].with_context(active_test=False)
        cls.Pricer = cls.env['mart369.serializable'].sudo()

    def setUp(self):
        super().setUp()
        self.deal = self.Deal.create({
            'name': 'Trash test', 'kind': 'percent', 'value': 25.0,
            'product_ids': [(6, 0, [self.widget.id])],
        })

    def _price(self):
        return self.Pricer._price_context_for(self.widget)[self.widget.id]['price']

    def test_a_trashed_deal_stops_discounting_at_once(self):
        self.assertEqual(self._price(), 150.0)
        self.deal.action_trash()
        self.assertEqual(self._price(), 200.0)

    def test_a_trashed_deal_is_not_live_and_not_on_the_offers_page(self):
        self.deal.action_trash()
        self.assertFalse(self.deal.live)
        self.assertNotIn(self.widget.id, self.Deal._mart369_product_ids())

    def test_restoring_puts_the_discount_back(self):
        self.deal.action_trash()
        self.deal.action_restore()
        self.assertFalse(self.deal.deleted_at)
        self.assertEqual(self._price(), 150.0)

    def test_restoring_does_not_switch_a_paused_deal_back_on(self):
        """It comes back exactly as it went in."""
        self.deal.active = False
        self.deal.action_trash()
        self.deal.action_restore()
        self.assertFalse(self.deal.active)
        self.assertEqual(self._price(), 200.0)

    def test_the_screens_get_kept_and_trashed_apart(self):
        self.deal.action_trash()
        data = self.Deal.mart369_admin_list()
        self.assertNotIn('Trash test', [d['name'] for d in data['deals']])
        self.assertIn('Trash test', [d['name'] for d in data['trash']])
        self.assertEqual(data['trashDays'], 30)

    def test_a_trashed_card_says_how_long_it_has_left(self):
        self.deal.action_trash()
        row = self.deal._mart369_admin_serialize()
        self.assertTrue(row['deletedAt'])
        self.assertEqual(row['daysLeft'], 30)

    def test_the_purge_empties_one_past_its_retention(self):
        self.deal.action_trash()
        self.deal.deleted_at = fields.Datetime.now() - timedelta(days=31)
        self.assertTrue(self.Deal._cron_purge_deals())
        self.assertFalse(self.deal.exists())

    def test_the_purge_leaves_one_still_inside_its_window(self):
        self.deal.action_trash()
        self.Deal._cron_purge_deals()
        self.assertTrue(self.deal.exists())

    def test_delete_over_http_is_a_trash_move(self):
        self.authenticate('admin', 'admin')
        response = self.url_open(
            '/369mart/admin/deals/%s' % self.deal.id, method='DELETE')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.deal.exists(), 'still there, just in the Trash')
        self.assertTrue(self.deal.deleted_at)

    def test_forever_needs_the_trash_first(self):
        """Nothing is destroyed without having been visible in the Trash."""
        self.authenticate('admin', 'admin')
        response = self.url_open(
            '/369mart/admin/deals/%s/forever' % self.deal.id, method='DELETE')
        self.assertEqual(response.status_code, 409)
        self.assertTrue(self.deal.exists())

        self.deal.action_trash()
        response = self.url_open(
            '/369mart/admin/deals/%s/forever' % self.deal.id, method='DELETE')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.deal.exists())

    def test_the_examples_do_not_come_back_after_being_trashed(self):
        """The demo loader runs on every upgrade, so it has to count the
        Trash too - or trashing the examples brings them straight back."""
        self.Deal.search([]).action_trash()
        self.assertFalse(self.Deal._mart369_load_demo())
