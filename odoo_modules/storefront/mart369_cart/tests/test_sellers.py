"""Who sells it, and Quick or Express on every card.

Once the shop has more than one company - one per hub - a product says which
company sells it: the company of the branch that would hand it over Quick,
else the product's own, else the shop's. The cards ask the same rule as the
bill (`_mart369_badges`), so a card and the cart never disagree. A
one-company shop shows no seller anywhere.
"""

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

# A couple of kilometres apart in Sohar, and one point in Muscat.
SOHAR = (24.3470, 56.7090)
SOHAR_HOME = (24.3600, 56.7200)
MUSCAT = (23.5880, 58.3829)


@tagged('post_install', '-at_install')
class TestSellers(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        # Whatever the database already has must not answer for these tests.
        env['stock.warehouse'].search([]).write({'mart369_quick': False})
        # Nor its hub rules: these tests are the shop without them.
        env['mart369.hub.rule'].search([]).unlink()

        cls.main = env.company
        cls.sohar = env['res.company'].create({'name': 'Zz Sohar Hub'})
        cls.sohar_branch = env['stock.warehouse'].search(
            [('company_id', '=', cls.sohar.id)], limit=1)
        cls.sohar_branch.write({
            'mart369_quick': True, 'mart369_quick_km': 10.0,
            'mart369_lat': SOHAR[0], 'mart369_lng': SOHAR[1],
        })

        Template = env['product.template']
        # Shared by every company: whoever has it nearby sells it.
        cls.fan = Template.create({'name': 'Zz Seller Fan', 'list_price': 5.0,
                                   'is_published': True, 'is_storable': True})
        # Nobody has any: no branch can hand it over.
        cls.hinge = Template.create({'name': 'Zz Seller Hinge', 'list_price': 3.0,
                                     'is_published': True, 'is_storable': True})
        # Sohar's own product.
        cls.cable = Template.create({'name': 'Zz Seller Cable', 'list_price': 2.0,
                                     'is_published': True, 'company_id': cls.sohar.id})
        cls.env['stock.quant'].with_company(cls.sohar).with_context(inventory_mode=True).create({
            'product_id': cls.fan.product_variant_id.id,
            'location_id': cls.sohar_branch.lot_stock_id.id,
            'inventory_quantity': 8,
        }).action_apply_inventory()

        cls.customer = env['res.partner'].create({'name': 'Zz Seller Customer'})
        cls.sohar_home = cls._address(SOHAR_HOME, '311')
        cls.muscat_home = cls._address(MUSCAT, '112')

        Area = env['mart369.service.area']
        Area.search([('pincode', 'in', ('993', '994'))]).unlink()
        Area.create({'pincode': '993', 'quick': False, 'express': True})
        Area.create({'pincode': '994', 'quick': True, 'express': True})

    @classmethod
    def _address(cls, point, zip_code):
        return cls.env['res.partner'].create({
            'name': 'Zz Seller Address', 'parent_id': cls.customer.id, 'type': 'other',
            'zip': zip_code, 'partner_latitude': point[0], 'partner_longitude': point[1],
        })

    @property
    def Cart(self):
        return self.env['mart369.cart']

    def _badges(self, *products, address=None, pin=None):
        keys = [str(p.id) for p in products]
        return self.Cart._mart369_badges(keys, address=address, pin=pin)

    # ------------------------------------------------------------ the seller

    def test_more_than_one_company_turns_sellers_on(self):
        self.assertTrue(self.Cart._mart369_sellers_on())

    def test_the_branch_that_has_it_nearby_sells_it_quick(self):
        badge = self._badges(self.fan, address=self.sohar_home)['badges'][str(self.fan.id)]
        self.assertEqual(badge['mode'], 'quick')
        self.assertEqual(badge['seller'], {'id': self.sohar.id, 'name': 'Zz Sohar Hub'})

    def test_far_from_every_branch_goes_express_from_the_shop(self):
        badge = self._badges(self.fan, address=self.muscat_home)['badges'][str(self.fan.id)]
        self.assertEqual(badge['mode'], 'all')
        self.assertEqual(badge['seller']['id'], self.env.company.id)

    def test_out_of_stock_nearby_goes_express(self):
        badge = self._badges(self.hinge, address=self.sohar_home)['badges'][str(self.hinge.id)]
        self.assertEqual(badge['mode'], 'all')

    def test_a_product_of_one_company_is_sold_by_it(self):
        badge = self._badges(self.cable, address=self.muscat_home)['badges'][str(self.cable.id)]
        self.assertEqual(badge['seller']['id'], self.sohar.id)

    def test_without_an_address_the_product_decides(self):
        badges = self._badges(self.fan, self.hinge)['badges']
        self.assertEqual(badges[str(self.fan.id)]['mode'], 'quick')
        self.assertEqual(badges[str(self.hinge.id)]['mode'], 'quick')

    def test_a_delivery_promise_is_express_and_says_so(self):
        self.hinge.mart_delivery_text = '3-5 days'
        badge = self._badges(self.hinge, address=self.sohar_home)['badges'][str(self.hinge.id)]
        self.assertEqual(badge['mode'], 'all')
        self.assertEqual(badge['eta'], '3-5 days')

    # ------------------------------------------------------- a guest's pincode

    def test_a_guest_pincode_alone_follows_its_area(self):
        # No branch reaches a pin that is not there, so the area decides.
        self.sohar_branch.mart369_quick = False
        express = self._badges(self.fan, pin='993001')['badges'][str(self.fan.id)]
        quick = self._badges(self.fan, pin='994001')['badges'][str(self.fan.id)]
        self.assertEqual(express['mode'], 'all')
        self.assertEqual(quick['mode'], 'quick')

    # --------------------------------------------------------------- the rest

    def test_unknown_and_unpublished_ids_are_left_out(self):
        self.hinge.is_published = False
        got = self.Cart._mart369_badges([str(self.fan.id), str(self.hinge.id), '999999999', 'junk'])
        self.assertEqual(set(got['badges']), {str(self.fan.id)})

    def test_the_card_and_the_bill_agree(self):
        items = {str(self.fan.id): 1, str(self.hinge.id): 1, str(self.cable.id): 1}
        bill = self.Cart._mart369_bill(items, address=self.sohar_home)
        badges = self._badges(self.fan, self.hinge, self.cable, address=self.sohar_home)['badges']
        for key in items:
            self.assertEqual(bill['modes'][key], badges[key]['mode'], key)
            self.assertEqual(bill['sellers'][key], badges[key]['seller'], key)

    # ---------------------------------------------------- a one-company shop

    def test_one_company_shows_no_seller_anywhere(self):
        self.patch(type(self.Cart), '_mart369_sellers_on', lambda self: False)
        got = self._badges(self.fan, address=self.sohar_home)
        self.assertFalse(got['sellers'])
        self.assertNotIn('seller', got['badges'][str(self.fan.id)])
        bill = self.Cart._mart369_bill({str(self.fan.id): 1}, address=self.sohar_home)
        self.assertEqual(bill['sellers'], {})
        # Everything else about the bill is as it always was.
        self.assertEqual(bill['modes'][str(self.fan.id)], 'quick')
