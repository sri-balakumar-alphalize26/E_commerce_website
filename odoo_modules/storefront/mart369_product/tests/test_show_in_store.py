"""Show in store (28 Nov 2026): every new product starts on, until someone switches it off."""
from odoo.tests import TransactionCase, tagged
from odoo.tools.misc import file_path


@tagged('post_install', '-at_install')
class TestShowInStore(TransactionCase):

    def test_a_new_product_starts_in_the_store(self):
        product = self.env['product.template'].create({'name': 'Zz new'})
        self.assertTrue(product.is_published)
        self.assertEqual(self.env['product.template']._fields['is_published'].string, 'Show in store')

    def test_one_made_without_a_category_or_imported_is_on(self):
        rows = self.env['product.template'].load(['name'], [['Zz imported 1'], ['Zz imported 2']])
        self.assertFalse(rows['messages'])
        self.assertTrue(all(self.env['product.template'].browse(rows['ids']).mapped('is_published')))

    def test_an_import_saying_off_still_comes_in_on(self):
        Template = self.env['product.template'].with_context(import_file=True)
        rows = Template.load(['name', 'is_published'], [['Zz import off', 'False']])
        self.assertFalse(rows['messages'])
        self.assertTrue(self.env['product.template'].browse(rows['ids']).is_published)

    def test_switched_off_stays_off(self):
        product = self.env['product.template'].create({'name': 'Zz hidden', 'is_published': False})
        self.assertFalse(product.is_published, 'an import column or a person saying off is kept')
        on = self.env['product.template'].create({'name': 'Zz on'})
        on.is_published = False
        on.write({'name': 'Zz on, renamed', 'description_sale': 'x'})
        self.assertFalse(on.is_published, 'an edit does not switch it back on')
        on.is_published = True
        self.assertTrue(on.is_published)

    def test_a_copy_starts_in_the_store(self):
        product = self.env['product.template'].create({'name': 'Zz first'})
        self.assertTrue(product.copy().is_published)

    def test_the_words_on_screen(self):
        with open(file_path('mart369_product/static/src/products/show_in_store_button.js'), encoding='utf-8') as f:
            js = f.read()
        self.assertIn('_t("In store")', js)
        self.assertIn('_t("Hidden")', js)
        for ref in ('mart369_product.mart369_show_in_store_search', 'mart369_product.mart369_show_in_store_template_list',
                    'mart369_product.mart369_show_in_store_variant_list'):
            self.assertIn('Show in store', self.env.ref(ref).arch_db)
