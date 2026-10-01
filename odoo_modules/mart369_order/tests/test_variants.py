"""Products with a choice: Brand, RAM, Colour.

PRODUCT_SETUP_FLOW.md (the WhatsApp side's own guide) makes one product per
model line and lets the customer pick the exact variant. The storefront has to
sell that same variant: priced with its own extras, ordered by its own id, and
read back under that id so reorder and buy-again add the same laptop again.
"""

from odoo.tests import tagged

from .common import Mart369OrderCase


@tagged('post_install', '-at_install')
class TestMart369Variants(Mart369OrderCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Attribute = cls.env['product.attribute'].sudo()

        def attribute(name, values, sequence):
            return Attribute.create({
                'name': name, 'sequence': sequence, 'create_variant': 'always',
                'display_type': 'radio',
                'value_ids': [(0, 0, {'name': v, 'sequence': k}) for k, v in enumerate(values)],
            })

        cls.brand = attribute('Test Brand', ['Lenovo', 'HP'], 1)
        cls.ram = attribute('Test RAM', ['8GB', '16GB'], 2)
        cls.colour = attribute('Test Colour', ['Black', 'Silver'], 3)

        cls.laptop = cls.env['product.template'].sudo().create({
            'name': 'Test Business Laptop',
            'list_price': 600.0,
            'is_published': True,
            'sale_ok': True,
            'type': 'consu',
            'attribute_line_ids': [
                # One value only: carried in the specs, never asked.
                (0, 0, {'attribute_id': cls.brand.id,
                        'value_ids': [(6, 0, cls.brand.value_ids[:1].ids)]}),
                (0, 0, {'attribute_id': cls.ram.id, 'value_ids': [(6, 0, cls.ram.value_ids.ids)]}),
                (0, 0, {'attribute_id': cls.colour.id,
                        'value_ids': [(6, 0, cls.colour.value_ids.ids)]}),
            ],
        })
        # 16GB costs 200 more, set where the product form sets it.
        cls.laptop.attribute_line_ids.product_template_value_ids.filtered(
            lambda v: v.name == '16GB').price_extra = 200.0

        def variant(ram, colour):
            return cls.laptop.product_variant_ids.filtered(
                lambda v: set(v.product_template_attribute_value_ids.mapped('name'))
                >= {ram, colour})

        cls.silver_16 = variant('16GB', 'Silver')
        cls.black_8 = variant('8GB', 'Black')
        cls.Mixin = cls.env['mart369.serializable'].sudo()

    def _key(self, variant):
        return self.Mixin._mart369_variant_key(variant)

    # -------------------------------------------------------------- the page

    def test_the_page_asks_only_the_questions_with_a_choice(self):
        page = self.env['mart369.product.page'].sudo().payload(self.laptop)
        self.assertEqual([a['name'] for a in page['attrs']], ['Test RAM', 'Test Colour'],
                         'in attribute order, and Brand (one value) is not asked')
        self.assertEqual(len(page['variants']), 4)
        self.assertTrue(page['p']['id'].startswith('v'), 'the page opens on a variant')
        self.assertEqual({c['variantGroup'] for c in page['variants']}, {str(self.laptop.id)})

    def test_a_variant_page_opens_on_that_variant(self):
        page = self.env['mart369.product.page'].sudo().payload(self.laptop, self.silver_16)
        self.assertEqual(page['p']['id'], self._key(self.silver_16))

    def test_a_variant_card_has_its_own_price_and_specs(self):
        cards = {c['id']: c for c in self.Mixin._serialize_variants(
            self.silver_16 | self.black_8)}
        silver, black = cards[self._key(self.silver_16)], cards[self._key(self.black_8)]
        self.assertEqual(silver['price'], 800.0, 'the product price plus the 16GB extra')
        self.assertEqual(black['price'], 600.0)
        self.assertEqual(silver['specs'].get('Test RAM'), '16GB')
        if hasattr(self.silver_16, '_sa_spec_rows'):
            self.assertEqual(list(silver['specs'].items()), self.silver_16._sa_spec_rows(),
                             'the same rows, in the same order, as the WhatsApp page')
        self.assertIn('Lenovo', silver['size'],
                      'the single-value brand is not a spec row, but it names the line')
        self.assertTrue(silver['hidden'], 'never listed on its own')

    def test_a_percent_pricelist_is_applied_to_the_extra_too(self):
        """10% off 600 with +200 for 16GB is 720 - as Odoo and the WhatsApp
        flow charge - not 600*0.9 + 200 = 740."""
        from unittest.mock import patch
        self.laptop.taxes_id = [(5, 0, 0)]
        pricelist = self.env['product.pricelist'].sudo().create({
            'name': 'Test ten off',
            'item_ids': [(0, 0, {'applied_on': '3_global', 'compute_price': 'percentage',
                                 'percent_price': 10.0})],
        })
        fake = type('Request', (), {
            'pricelist': pricelist,
            'fiscal_position': self.env['account.fiscal.position'],
        })()
        website = self.env['website'].sudo().search([], limit=1)
        with patch('odoo.http.request', fake):
            prices = self.Mixin._mart369_website_variant_prices(self.silver_16, website)
        self.assertAlmostEqual(prices[self.silver_16.id]['price'], 720.0, places=2)

    def test_a_no_variant_attribute_is_not_a_question(self):
        wrap = self.env['product.attribute'].sudo().create({
            'name': 'Test Gift wrap', 'create_variant': 'no_variant',
            'value_ids': [(0, 0, {'name': 'Yes'}), (0, 0, {'name': 'No'})],
        })
        self.laptop.attribute_line_ids = [(0, 0, {
            'attribute_id': wrap.id, 'value_ids': [(6, 0, wrap.value_ids.ids)]})]
        names = [a['name'] for a in self.Mixin._mart369_attrs(self.laptop)]
        self.assertNotIn('Test Gift wrap', names)

    def test_the_listing_card_says_the_product_has_a_choice(self):
        card = self.Mixin._serialize_product(
            self.laptop, None, self.Mixin._price_context_for(self.laptop))
        self.assertTrue(card['hasVariants'])
        self.assertEqual(card['id'], str(self.laptop.id), 'listings keep the product id')

    # -------------------------------------------------------------- the bill

    def test_the_bill_prices_the_picked_variant(self):
        key = self._key(self.silver_16)
        bill = self.env['mart369.cart']._mart369_bill({key: 2})
        self.assertEqual(bill['items'], 1600.0)
        self.assertEqual(bill['modes'], {key: 'quick'})
        self.assertEqual(bill['unknown'], [])

    def test_two_variants_of_one_product_are_two_lines(self):
        bill = self.env['mart369.cart']._mart369_bill({
            self._key(self.silver_16): 1, self._key(self.black_8): 1})
        self.assertEqual(bill['items'], 1400.0)
        self.assertEqual(bill['count'], 2)

    def test_an_unpublished_variant_is_reported_not_charged(self):
        self.laptop.is_published = False
        key = self._key(self.silver_16)
        bill = self.env['mart369.cart']._mart369_bill({key: 1})
        self.assertEqual(bill['items'], 0.0)
        self.assertEqual(bill['unknown'], [key])

    # ------------------------------------------------------------- the order

    def test_the_order_sells_the_exact_variant_picked(self):
        key = self._key(self.silver_16)
        order = self._place(items={key: 1}, ref='369M-VAR1')
        line = order.order_line.filtered(lambda l: not l.mart369_kind and not l.is_delivery)
        self.assertEqual(line.product_id, self.silver_16)
        self.assertEqual(line.price_unit, 800.0)
        self.assertIn('16GB', line.name, 'the counter reads which one to pack')

    def test_the_order_reads_back_under_the_basket_id(self):
        """So reorder and buy-again add the same laptop, not its first variant."""
        key = self._key(self.silver_16)
        order = self._place(items={key: 1}, ref='369M-VAR2')
        payload = order._mart369_serialize()
        self.assertEqual(payload['items'], [[key, 1]])
        self.assertIn(key, payload['snap'])

    def test_a_plain_id_of_a_product_with_variants_sells_its_first_variant_whole(self):
        """A basket from before the laptop had variants: its first variant,
        at that variant's price and under its name - not the product's price
        without the extras."""
        first = self.laptop.product_variant_id
        first.product_template_attribute_value_ids.filtered(
            lambda v: v.attribute_id == self.colour).price_extra = 50.0
        self.assertNotEqual(first.lst_price, self.laptop.list_price)
        key = str(self.laptop.id)
        bill = self.env['mart369.cart']._mart369_bill({key: 1})
        self.assertEqual(bill['items'], first.lst_price)
        order = self._place(items={key: 1}, ref='369M-VAR4')
        line = order.order_line.filtered(lambda l: not l.mart369_kind and not l.is_delivery)
        self.assertEqual(line.product_id, first)
        self.assertEqual(line.price_unit, first.lst_price)
        self.assertEqual(line.name, first.display_name)
        self.assertEqual(order._mart369_serialize()['items'], [[self._key(first), 1]],
                         'read back as the variant it sold, so a reorder adds that one')

    def test_a_plain_product_id_still_orders_as_before(self):
        """Baskets and orders from before variants keep their template ids."""
        order = self._place(ref='369M-VAR3')
        self.assertEqual(order._mart369_serialize()['items'],
                         [[str(self.quick_product.id), 4]])
