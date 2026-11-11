"""The hub rules: Ruwi, Sohar and Salalah, and which one delivers what.

Inside one hub, distance decides: Quick up to its reach, "Quick if possible"
up to its second reach, then Express. Between hubs, the hub table decides,
and its Cargo badge marks the long trips. When the customer's own hub has
none, the next hub steps in. While the table is empty nothing changes.
"""

from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from ..models.branch import haversine_km, quick_minutes, quick_time_text

RUWI = (23.5880, 58.3829)
SOHAR = (24.3470, 56.7090)
SALALAH = (17.0151, 54.0924)
QURUM = (23.6140, 58.4720)        # about 9 km from Ruwi Hub
WEST_35 = (23.5880, 58.0390)      # about 35 km from Ruwi Hub
NIZWA = (22.9333, 57.5333)        # about 113 km from Ruwi Hub, nearest hub still Ruwi


@tagged('post_install', '-at_install')
class TestHubRules(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        # Whatever the database already has must not answer for these tests.
        env['stock.warehouse'].search([]).write({
            'mart369_quick': False, 'mart369_lat': 0.0, 'mart369_lng': 0.0,
            'mart369_maybe_km': 0.0,
        })
        env['mart369.hub.rule'].search([]).unlink()

        cls.ruwi_co = env.company
        cls.sohar_co = env['res.company'].create({'name': 'Zz Sohar Hub'})
        cls.salalah_co = env['res.company'].create({'name': 'Zz Salalah Hub'})
        Branch = env['stock.warehouse']
        cls.ruwi = Branch.search([('company_id', '=', cls.ruwi_co.id)], limit=1)
        cls.sohar = Branch.search([('company_id', '=', cls.sohar_co.id)], limit=1)
        cls.salalah = Branch.search([('company_id', '=', cls.salalah_co.id)], limit=1)
        cls.ruwi.write({
            'mart369_quick': True, 'mart369_quick_km': 30.0, 'mart369_maybe_km': 40.0,
            'mart369_quick_eta': 'typed long ago', 'mart369_lat': RUWI[0], 'mart369_lng': RUWI[1],
        })
        cls.sohar.write({'mart369_lat': SOHAR[0], 'mart369_lng': SOHAR[1]})
        cls.salalah.write({'mart369_lat': SALALAH[0], 'mart369_lng': SALALAH[1]})

        Rule = env['mart369.hub.rule']
        for src, dst, days, arrives, cargo in (
                (cls.ruwi, cls.ruwi, 1, 'Next day', False),
                (cls.sohar, cls.ruwi, 1, 'Next day', False),
                (cls.salalah, cls.ruwi, 3, 'In 2-3 days', True),
                (cls.ruwi, cls.sohar, 1, 'Next day', False),
                (cls.ruwi, cls.salalah, 3, 'In 2-3 days', True),
                (cls.sohar, cls.salalah, 3, 'In 2-3 days', True),
                (cls.salalah, cls.sohar, 3, 'In 2-3 days', True)):
            Rule.create({'from_hub_id': src.id, 'to_hub_id': dst.id, 'days': days,
                         'arrives': arrives, 'cargo': cargo})

        Template = env['product.template']

        def product(name, **extra):
            return Template.create(dict({'name': name, 'list_price': 5.0, 'is_published': True,
                                         'is_storable': True}, **extra))

        cls.keyboard = product('Zz Hub Keyboard')
        cls.mouse = product('Zz Hub Mouse')
        cls.fan = product('Zz Hub Fan')
        cls.cable = product('Zz Hub Cable')
        cls.ram = product('Zz Hub RAM')
        cls.ssd = product('Zz Hub SSD')
        cls.cooler = product('Zz Hub Cooler', mart_delivery_text='3-5 days')
        for tmpl, branch, qty in (
                (cls.keyboard, cls.ruwi, 5), (cls.mouse, cls.sohar, 5),
                (cls.fan, cls.salalah, 5), (cls.cable, cls.sohar, 5),
                (cls.cable, cls.salalah, 5), (cls.ram, cls.ruwi, 1),
                (cls.ram, cls.sohar, 5), (cls.cooler, cls.ruwi, 5)):
            cls._stock(tmpl, branch, qty)

        cls.customer = env['res.partner'].create({'name': 'Zz Priya'})
        cls.qurum = cls._address(QURUM)
        cls.west = cls._address(WEST_35)
        cls.nizwa = cls._address(NIZWA)

    @classmethod
    def _stock(cls, tmpl, branch, qty):
        cls.env['stock.quant'].with_company(branch.company_id).with_context(
            inventory_mode=True).create({
                'product_id': tmpl.product_variant_id.id,
                'location_id': branch.lot_stock_id.id,
                'inventory_quantity': qty,
            }).action_apply_inventory()

    @classmethod
    def _address(cls, point, zip_code='112'):
        lat, lng = point if point else (0.0, 0.0)
        return cls.env['res.partner'].create({
            'name': 'Zz Priya Address', 'parent_id': cls.customer.id, 'type': 'other',
            'zip': zip_code, 'partner_latitude': lat, 'partner_longitude': lng,
        })

    def _badge(self, product, address):
        got = self.env['mart369.cart']._mart369_badges([str(product.id)], address=address)
        return got['badges'][str(product.id)]

    # ---------------------------------------------------- Priya, in Ruwi

    def test_near_her_own_hub_it_is_quick_in_a_time_from_her_distance(self):
        badge = self._badge(self.keyboard, self.qurum)
        self.assertEqual(badge['mode'], 'quick')
        km = haversine_km(*QURUM, *RUWI)
        self.assertEqual(badge['when'], quick_time_text(km),
                         'worked out from how far she is, never the typed promise')
        self.assertEqual(badge['seller']['id'], self.ruwi_co.id)
        self.assertNotIn('cargo', badge)

    def test_from_the_next_city_it_is_express_next_day(self):
        badge = self._badge(self.mouse, self.qurum)
        self.assertEqual(badge['mode'], 'all')
        self.assertEqual(badge['when'], 'Next day')
        self.assertNotIn('cargo', badge)
        self.assertEqual(badge['seller']['id'], self.sohar_co.id)

    def test_from_salalah_it_is_express_with_the_cargo_badge(self):
        badge = self._badge(self.fan, self.qurum)
        self.assertEqual(badge['mode'], 'all')
        self.assertEqual(badge['when'], 'In 2-3 days')
        self.assertTrue(badge['cargo'])
        self.assertEqual(badge['seller']['id'], self.salalah_co.id)

    def test_of_two_hubs_that_have_it_the_faster_one_sells_it(self):
        badge = self._badge(self.cable, self.qurum)
        self.assertEqual(badge['seller']['id'], self.sohar_co.id)
        self.assertEqual(badge['when'], 'Next day')

    def test_out_of_stock_at_her_hub_the_next_hub_steps_in(self):
        Cart = self.env['mart369.cart']
        one = Cart._mart369_bill({str(self.ram.id): 1}, address=self.qurum)
        two = Cart._mart369_bill({str(self.ram.id): 2}, address=self.qurum)
        self.assertEqual(one['modes'][str(self.ram.id)], 'quick')
        self.assertEqual(one['sellers'][str(self.ram.id)]['id'], self.ruwi_co.id)
        self.assertEqual(two['modes'][str(self.ram.id)], 'all')
        self.assertEqual(two['sellers'][str(self.ram.id)]['id'], self.sohar_co.id)
        self.assertEqual(two['notes'][str(self.ram.id)], {'when': 'Next day'})

    def test_no_hub_has_it_is_express_as_before(self):
        badge = self._badge(self.ssd, self.qurum)
        self.assertEqual(badge['mode'], 'all')
        self.assertNotIn('when', badge)

    def test_a_delivery_promise_stays_express_with_its_own_words(self):
        badge = self._badge(self.cooler, self.qurum)
        self.assertEqual(badge['mode'], 'all')
        self.assertEqual(badge['when'], '3-5 days')
        self.assertEqual(badge['seller']['id'], self.ruwi_co.id)

    # ----------------------------------------------- distance inside a hub

    def test_a_little_past_the_reach_is_express_that_may_come_quick(self):
        badge = self._badge(self.keyboard, self.west)
        self.assertEqual(badge['mode'], 'all')
        self.assertTrue(badge['maybe'])
        self.assertEqual(badge['when'], 'Next day')

    def test_far_inside_her_hub_is_express_next_day(self):
        badge = self._badge(self.keyboard, self.nizwa)
        self.assertEqual(badge['mode'], 'all')
        self.assertNotIn('maybe', badge)
        self.assertEqual(badge['when'], 'Next day')

    # ----------------------------------------------------------- the bill

    def test_the_bill_carries_the_notes_and_names_only_quick_branches(self):
        items = {str(self.keyboard.id): 1, str(self.fan.id): 1}
        bill = self.env['mart369.cart']._mart369_bill(items, address=self.qurum)
        self.assertEqual(bill['modes'], {str(self.keyboard.id): 'quick', str(self.fan.id): 'all'})
        self.assertEqual(bill['notes'][str(self.fan.id)], {'when': 'In 2-3 days', 'cargo': True})
        self.assertEqual(bill['branch'], self.ruwi.name)

    def test_the_card_and_the_bill_agree(self):
        products = (self.keyboard, self.mouse, self.fan, self.cable, self.ssd, self.cooler)
        items = {str(p.id): 1 for p in products}
        bill = self.env['mart369.cart']._mart369_bill(items, address=self.qurum)
        badges = self.env['mart369.cart']._mart369_badges(list(items), address=self.qurum)['badges']
        for key in items:
            self.assertEqual(bill['modes'][key], badges[key]['mode'], key)
            self.assertEqual(bill['sellers'][key], badges[key]['seller'], key)

    # ------------------------------------------------ switched off = as before

    def test_an_empty_table_works_exactly_as_before(self):
        self.env['mart369.hub.rule'].search([]).unlink()
        items = {str(self.keyboard.id): 1, str(self.fan.id): 1}
        bill = self.env['mart369.cart']._mart369_bill(items, address=self.qurum)
        # The old rule: Ruwi reaches Qurum and has the keyboard; nobody near
        # has the fan.
        self.assertEqual(bill['modes'], {str(self.keyboard.id): 'quick', str(self.fan.id): 'all'})
        self.assertEqual(bill['notes'], {})
        badge = self._badge(self.keyboard, self.qurum)
        self.assertNotIn('when', badge)

    def test_an_address_without_a_pin_uses_the_old_rule(self):
        no_pin = self._address(None)
        bill = self.env['mart369.cart']._mart369_bill({str(self.fan.id): 1}, address=no_pin)
        self.assertEqual(bill['notes'], {})

    # ------------------------------------------------------------ settings

    def test_saving_the_new_branch_settings(self):
        row = self.env['stock.warehouse'].mart369_admin_save(
            self.sohar.id, {'quickKm': '20', 'maybeKm': '25'})
        self.assertEqual(row['maybeKm'], 25.0)
        self.assertEqual(row['quickUpTo'], '1 hr 50 mins', '10 + 5 x 20 km')
        self.assertNotIn('quickEta', row, 'nobody types the Quick time any more')

    def test_the_quick_time_is_worked_out(self):
        self.assertEqual(quick_minutes(0), 10)
        self.assertEqual(quick_minutes(1), 15)
        self.assertEqual(quick_minutes(3), 25)
        self.assertEqual(quick_minutes(5), 35)
        self.assertEqual(quick_minutes(2.2), 25, 'rounded up to the next 5')
        self.assertEqual(quick_time_text(5), '35 mins')
        self.assertEqual(quick_time_text(10), '1 hr')
        self.assertEqual(quick_time_text(12), '1 hr 10 mins')

    def test_the_location_is_one_box_from_google_maps(self):
        Branch = self.env['stock.warehouse']
        row = Branch.mart369_admin_save(self.sohar.id, {'pin': ' 10.3673,  77.9803 '})
        self.assertEqual((row['lat'], row['lng']), (10.3673, 77.9803))
        with self.assertRaises(UserError):
            Branch.mart369_admin_save(self.sohar.id, {'pin': '10.3673'})
        row = Branch.mart369_admin_save(self.sohar.id, {'pin': ''})
        self.assertIsNone(row['lat'], 'an empty box takes the pin away')

    def test_switching_quick_on_fills_the_usual_reaches(self):
        Branch = self.env['stock.warehouse']
        self.sohar.write({'mart369_quick': False, 'mart369_quick_km': 0.0,
                          'mart369_maybe_km': 0.0})
        row = Branch.mart369_admin_save(self.sohar.id, {'quick': True})
        self.assertEqual((row['quickKm'], row['maybeKm']), (5.0, 15.0))
        # Already on: what the operator typed is left alone.
        row = Branch.mart369_admin_save(self.sohar.id, {'quick': True, 'maybeKm': ''})
        self.assertEqual(row['maybeKm'], 0.0)

    def test_quick_if_possible_cannot_be_under_the_reach(self):
        with self.assertRaises(ValidationError):
            self.env['stock.warehouse'].mart369_admin_save(
                self.sohar.id, {'quickKm': '20', 'maybeKm': '10'})

    def test_one_rule_per_pair_of_hubs(self):
        with self.assertRaises(Exception), self.env.cr.savepoint():
            self.env['mart369.hub.rule'].create(
                {'from_hub_id': self.sohar.id, 'to_hub_id': self.ruwi.id})
