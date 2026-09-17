from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestResolver(TransactionCase):
    """Who decides whether a field shows, and what it says.

    This is the whole feature, so the truth table is spelled out rather than
    sampled.
    """

    def setUp(self):
        super().setUp()
        self.Field = self.env['mart369.product.field']
        self.Section = self.env['mart369.product.section']
        self.Override = self.env['mart369.product.override']
        self.CategoryValue = self.env['mart369.product.category.value']

        self.category = self.env['product.public.category'].create({
            'name': 'Resolver Test Category'})
        self.product = self.env['product.template'].create({
            'name': 'Resolver Test Product',
            'is_published': True,
            'list_price': 10,
            'public_categ_ids': [(6, 0, [self.category.id])],
        })
        self.field = self.Field.search([('key', '=', 'manufacturer_address')])
        self.section = self.field.section_id

    def _state(self, state):
        self.Field.set_product_state(self.field.id, self.product.id, state)

    # ------------------------------------------------------------ the table

    def test_truth_table(self):
        """Section x global x product, all nine combinations that matter."""
        cases = [
            # section, global, product state -> visible?
            (True, True, 'follow', True),
            (True, True, 'show', True),
            (True, True, 'hide', False),
            (True, False, 'follow', False),
            (True, False, 'show', True),
            (True, False, 'hide', False),
            (False, True, 'follow', False),
            (False, True, 'show', False),   # the section is the master switch
            (False, False, 'hide', False),
        ]
        for section_show, global_show, state, expected in cases:
            self.section.show = section_show
            self.field.show = global_show
            self._state(state)
            self.assertEqual(
                self.field._visible_for(self.product), expected,
                'section=%s global=%s product=%s should be %s'
                % (section_show, global_show, state, expected))

    def test_following_stores_nothing(self):
        """A product that follows the shop everywhere has no rows of its own.

        That is what lets a later shop-wide change still reach it.
        """
        self._state('hide')
        self.assertEqual(self.Override.search_count(
            [('product_tmpl_id', '=', self.product.id)]), 1)
        self._state('follow')
        self.assertEqual(
            self.Override.search_count([('product_tmpl_id', '=', self.product.id)]), 0,
            'Following the default should leave nothing behind.')

    def test_a_later_global_change_reaches_followers(self):
        other = self.env['product.template'].create({
            'name': 'Follower', 'is_published': True, 'list_price': 5})
        self._state('show')          # this product opts in explicitly
        self.field.show = False      # the shop turns it off afterwards

        self.assertFalse(self.field._visible_for(other), 'a follower follows')
        self.assertTrue(self.field._visible_for(self.product),
                        'a product set to Always show keeps it')

    # ----------------------------------------------------------- the values

    def test_value_falls_back_global_then_category_then_product(self):
        self.field.write({'source': 'text', 'default_value': 'Shop default'})
        self.assertEqual(self.field._value_for(self.product), 'Shop default')

        self.CategoryValue.create({
            'public_categ_id': self.category.id,
            'field_id': self.field.id,
            'value': 'Category default',
        })
        self.assertEqual(self.field._value_for(self.product), 'Category default',
                         'the category beats the shop default')

        self.Override.create({
            'product_tmpl_id': self.product.id,
            'field_id': self.field.id,
            'state': 'follow',
            'value': 'Just this product',
        })
        self.assertEqual(self.field._value_for(self.product), 'Just this product',
                         'the product beats its category')

    def test_a_deeper_category_wins(self):
        """A sub-category refines what its parent set."""
        child = self.env['product.public.category'].create({
            'name': 'Child', 'parent_id': self.category.id})
        self.product.public_categ_ids = [(6, 0, [self.category.id, child.id])]
        self.field.write({'source': 'text', 'default_value': 'Shop'})
        self.CategoryValue.create({
            'public_categ_id': self.category.id,
            'field_id': self.field.id, 'value': 'Parent'})
        self.CategoryValue.create({
            'public_categ_id': child.id,
            'field_id': self.field.id, 'value': 'Child'})
        self.assertEqual(self.field._value_for(self.product), 'Child')

    def test_value_can_come_from_the_product_itself(self):
        field = self.Field.search([('key', '=', 'net_weight')])
        self.product.weight = 2.5
        self.assertEqual(field._value_for(self.product), 2.5)

    def test_unknown_odoo_field_is_empty_not_a_crash(self):
        self.field.write({'source': 'odoo', 'odoo_field': 'no_such_field'})
        self.assertEqual(self.field._value_for(self.product), '')

    # ---------------------------------------------------------- the payload

    def test_resolve_leaves_hidden_fields_out(self):
        before = self.Field._resolve(self.product)
        self.assertIn('manufacturer_address', before)
        self.field.show = False
        after = self.Field._resolve(self.product)
        self.assertNotIn('manufacturer_address', after,
                         'a hidden field is absent, not empty')

    def test_sections_keep_their_order(self):
        rows = self.Field._resolve_sections(self.product)
        info = [f.key for f, _v in rows.get('info', [])]
        self.assertEqual(info, sorted(
            info, key=lambda k: self.Field.search([('key', '=', k)]).sequence),
            'the information table renders in sequence order')

    def test_builder_load_shape(self):
        data = self.Field.builder_load(self.product.id)
        self.assertEqual(set(data),
                         {'sections', 'fields', 'product', 'overrides', 'values'})
        self.assertTrue(data['sections'] and data['fields'])
        self.assertEqual(data['product']['id'], self.product.id)

    def test_reset_puts_a_whole_section_back(self):
        self._state('hide')
        ids = self.section.field_ids.ids
        self.Field.reset_product_state(ids, self.product.id)
        self.assertEqual(self.Override.search_count(
            [('product_tmpl_id', '=', self.product.id)]), 0)

    def test_website_designer_can_edit(self):
        designer = self.env['res.users'].create({
            'name': 'Ops', 'login': 'ops_mart369_product',
            'group_ids': [(6, 0, [
                self.env.ref('base.group_user').id,
                self.env.ref('website.group_website_designer').id,
            ])],
        })
        Field = self.Field.with_user(designer)
        self.assertTrue(Field.builder_load(self.product.id)['fields'])
        Field.set_product_state(self.field.id, self.product.id, 'hide')
        self.assertEqual(
            Field.browse(self.field.id)._state_for(self.product), 'hide')
