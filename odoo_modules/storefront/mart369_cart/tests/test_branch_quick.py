"""Quick or Express, decided by where the basket is going.

An item is Quick when a branch with Quick on is within its reach of the
address's map pin and has the item in stock there. Otherwise Express. An
address with no pin follows its pincode's area, and until any branch is set up
the product decides exactly as before.
"""

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from ..models.branch import haversine_km

# Two points a couple of kilometres apart in Muscat, and one in Sohar.
RUWI = (23.5880, 58.3829)
NEAR = (23.6000, 58.4000)
SOHAR = (24.3470, 56.7090)


@tagged('post_install', '-at_install')
class TestBranchQuick(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        # Whatever the database already has must not answer for these tests.
        env['stock.warehouse'].search([]).write({'mart369_quick': False})

        company = env.company
        cls.near_branch = env['stock.warehouse'].search(
            [('company_id', '=', company.id)], limit=1)
        cls.near_branch.write({
            'mart369_quick': True, 'mart369_quick_km': 5.0,
            'mart369_lat': RUWI[0], 'mart369_lng': RUWI[1],
        })
        cls.other_branch = env['stock.warehouse'].create({
            'name': 'Zz Test Second Branch', 'code': 'ZZT2', 'company_id': company.id,
        })

        Template = env['product.template']
        cls.milk = Template.create({'name': 'Zz Branch Milk', 'list_price': 40.0,
                                    'is_published': True})
        cls.eggs = Template.create({'name': 'Zz Branch Eggs', 'list_price': 60.0,
                                    'is_published': True})
        cls.ssd = Template.create({'name': 'Zz Branch SSD', 'list_price': 400.0,
                                   'is_published': True, 'mart_delivery_text': '3-5 days'})
        for tmpl in (cls.milk, cls.eggs, cls.ssd):
            tmpl.is_storable = True
        cls._stock(cls.milk, cls.near_branch, 10)
        cls._stock(cls.eggs, cls.other_branch, 10)   # not at the near branch

        cls.customer = env['res.partner'].create({'name': 'Zz Branch Customer'})
        cls.near_home = cls._address(NEAR, '112')
        cls.far_home = cls._address(SOHAR, '311')

        Area = env['mart369.service.area']
        Area.search([('pincode', 'in', ('991', '992'))]).unlink()
        Area.create({'pincode': '991', 'quick': False, 'express': True})
        Area.create({'pincode': '992', 'quick': True, 'express': True})

    @classmethod
    def _stock(cls, tmpl, branch, qty):
        cls.env['stock.quant'].with_context(inventory_mode=True).create({
            'product_id': tmpl.product_variant_id.id,
            'location_id': branch.lot_stock_id.id,
            'inventory_quantity': qty,
        }).action_apply_inventory()

    @classmethod
    def _address(cls, point, zip_code):
        lat, lng = point if point else (0.0, 0.0)
        return cls.env['res.partner'].create({
            'name': 'Zz Branch Address', 'parent_id': cls.customer.id, 'type': 'other',
            'zip': zip_code, 'partner_latitude': lat, 'partner_longitude': lng,
        })

    def _bill(self, *products, address=None, qty=1):
        items = {str(p.id): qty for p in products}
        return self.env['mart369.cart']._mart369_bill(items, address=address)

    def _mode(self, bill, product):
        return bill['modes'][str(product.id)]

    # ----------------------------------------------------------- distance

    def test_distance_is_a_straight_line_in_km(self):
        self.assertAlmostEqual(haversine_km(*RUWI, *RUWI), 0.0, places=6)
        self.assertLess(haversine_km(*RUWI, *NEAR), 3.0)
        # Muscat to Sohar is about 190 km as the crow flies.
        self.assertTrue(180 < haversine_km(*RUWI, *SOHAR) < 200)

    # -------------------------------------------------------------- rule

    def test_without_an_address_the_product_decides(self):
        bill = self._bill(self.milk, self.eggs, self.ssd)
        self.assertEqual(self._mode(bill, self.milk), 'quick')
        self.assertEqual(self._mode(bill, self.eggs), 'quick')
        self.assertEqual(self._mode(bill, self.ssd), 'all')
        self.assertEqual(bill['movedToExpress'], 0)

    def test_near_a_branch_that_has_it_is_quick(self):
        bill = self._bill(self.milk, address=self.near_home)
        self.assertEqual(self._mode(bill, self.milk), 'quick')
        self.assertEqual(bill['branch'], self.near_branch.name)

    def test_near_a_branch_that_does_not_have_it_goes_express(self):
        bill = self._bill(self.milk, self.eggs, address=self.near_home)
        self.assertEqual(self._mode(bill, self.milk), 'quick')
        self.assertEqual(self._mode(bill, self.eggs), 'all')
        self.assertEqual(bill['movedToExpress'], 1)
        self.assertEqual(bill['movedWhy'], 'stock')

    def test_more_than_the_branch_holds_goes_express(self):
        bill = self._bill(self.milk, address=self.near_home, qty=11)
        self.assertEqual(self._mode(bill, self.milk), 'all')

    def test_another_quick_branch_in_reach_can_hand_it_over(self):
        self.other_branch.write({
            'mart369_quick': True, 'mart369_quick_km': 5.0,
            'mart369_lat': NEAR[0], 'mart369_lng': NEAR[1],
        })
        bill = self._bill(self.eggs, address=self.near_home)
        self.assertEqual(self._mode(bill, self.eggs), 'quick')
        self.assertEqual(bill['branch'], self.other_branch.name)

    def test_beyond_every_reach_is_express(self):
        bill = self._bill(self.milk, address=self.far_home)
        self.assertEqual(self._mode(bill, self.milk), 'all')
        self.assertEqual(bill['movedWhy'], 'far')

    def test_express_items_stay_express_even_next_door(self):
        self._stock(self.ssd, self.near_branch, 5)
        bill = self._bill(self.ssd, address=self.near_home)
        self.assertEqual(self._mode(bill, self.ssd), 'all')
        self.assertEqual(bill['movedToExpress'], 0)

    def test_a_branch_with_quick_off_reaches_nobody(self):
        self.near_branch.mart369_quick = False
        # No branch is ready at all now, so the old rule applies.
        bill = self._bill(self.eggs, address=self.near_home)
        self.assertEqual(self._mode(bill, self.eggs), 'quick')

    # ------------------------------------------------------- no map pin

    def test_no_pin_follows_an_express_only_pincode(self):
        bill = self._bill(self.milk, address=self._address(None, '991001'))
        self.assertEqual(self._mode(bill, self.milk), 'all')
        self.assertEqual(bill['movedWhy'], 'area')

    def test_no_pin_follows_a_quick_pincode(self):
        bill = self._bill(self.eggs, address=self._address(None, '992001'))
        self.assertEqual(self._mode(bill, self.eggs), 'quick')

    def test_no_pin_and_no_area_leaves_the_product_to_decide(self):
        bill = self._bill(self.eggs, address=self._address(None, '555'))
        self.assertEqual(self._mode(bill, self.eggs), 'quick')

    # ------------------------------------------------------------ money

    def test_fees_follow_where_the_items_landed(self):
        """An item moved to Express pays Express delivery, not Quick."""
        rules = self.env['mart369.delivery.rule']._mart369_rules()
        rules['quick'].write({'fee': 30.0, 'free_above': 499.0, 'min_order': 0.0})
        rules['all'].write({'fee': 49.0, 'free_above': 999.0})
        near = self._bill(self.milk, address=self.near_home)
        far = self._bill(self.milk, address=self.far_home)
        self.assertEqual(near['fees'], 30.0)
        self.assertEqual(far['fees'], 49.0)
        self.assertEqual(far['sub'], {'quick': 0.0, 'all': 40.0})

    # ---------------------------------------------------------- editing

    def test_saving_a_branch(self):
        row = self.env['stock.warehouse'].mart369_admin_save(
            self.other_branch.id, {'quick': True, 'quickKm': '3.5', 'lat': '24.35', 'lng': '56.7'})
        self.assertTrue(row['quick'])
        self.assertEqual(row['quickKm'], 3.5)
        self.assertFalse(row['unready'])

    def test_quick_without_a_pin_is_flagged_not_ready(self):
        row = self.env['stock.warehouse'].mart369_admin_save(
            self.other_branch.id, {'quick': True, 'quickKm': 4})
        self.assertTrue(row['unready'])

    def test_bad_values_are_refused(self):
        Branch = self.env['stock.warehouse']
        with self.assertRaises(UserError):
            Branch.mart369_admin_save(self.other_branch.id, {'quickKm': 'far'})
        with self.assertRaises(ValidationError):
            Branch.mart369_admin_save(self.other_branch.id, {'quickKm': -1})
        with self.assertRaises(ValidationError):
            Branch.mart369_admin_save(self.other_branch.id, {'lat': 123})

    def test_a_shopper_cannot_save_a_branch(self):
        shopper = self.env['res.users'].create({
            'name': 'Zz Branch Shopper', 'login': 'zz_branch_shopper',
            'group_ids': [(6, 0, [self.env.ref('base.group_portal').id])],
        })
        with self.assertRaises(AccessError):
            self.env['stock.warehouse'].with_user(shopper).mart369_admin_save(
                self.other_branch.id, {'quick': True})
