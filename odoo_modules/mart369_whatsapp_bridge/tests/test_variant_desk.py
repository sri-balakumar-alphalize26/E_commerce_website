"""The console's Edit product screen and the senior's Variant specs table.

The screen sends the rows it shows and the ids taken off it. A row added from
Odoo's Product Variants form while the screen was open is on neither list, and
must survive the save.
"""

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestVariantDeskSpecs(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Product = self.env['product.template']
        self.Spec = self.env['sa.variant.spec'].sudo()
        categ = self.env['product.category'].create({'name': 'Zz Spec Computers'})
        self.pid = self.Product.mart369_desk_save(
            {'name': 'Zz Spec Laptop', 'list_price': 600, 'categ_id': str(categ.id)})
        self.variant = self.Product.browse(self.pid).product_variant_id
        self.warranty = self.Spec.create({'product_id': self.variant.id, 'sequence': 10,
                                          'name': 'Warranty', 'value': '1 year'})
        self.ports = self.Spec.create({'product_id': self.variant.id, 'sequence': 20,
                                       'name': 'Ports', 'value': '2x USB-C'})

    def _save(self, change):
        self.Product.mart369_desk_save({}, product_id=self.pid, variants={
            'per': {str(self.variant.id): change}})

    def _rows(self):
        return [(s.name, s.value) for s in
                self.variant.sa_spec_ids.sorted(lambda s: (s.sequence, s.id))]

    def _on_screen(self, *specs):
        return [{'id': s.id, 'name': s.name, 'value': s.value} for s in specs]

    def test_a_row_added_elsewhere_survives_a_save(self):
        screen = self._on_screen(self.warranty, self.ports)
        self.Spec.create({'product_id': self.variant.id, 'sequence': 30,
                          'name': 'Battery', 'value': '6 hours'})
        screen[0]['value'] = '2 years'
        self._save({'specs': screen, 'specs_removed': []})
        self.assertEqual(self._rows(), [('Warranty', '2 years'), ('Ports', '2x USB-C'),
                                        ('Battery', '6 hours')])

    def test_only_the_rows_taken_off_go(self):
        self._save({'specs': self._on_screen(self.ports),
                    'specs_removed': [self.warranty.id]})
        self.assertEqual(self._rows(), [('Ports', '2x USB-C')])

    def test_a_cleared_name_takes_the_row_off(self):
        screen = self._on_screen(self.warranty, self.ports)
        screen[0]['name'] = '  '
        self._save({'specs': screen, 'specs_removed': []})
        self.assertEqual(self._rows(), [('Ports', '2x USB-C')])

    def test_another_variants_row_is_never_taken_off(self):
        other = self.Product.create({'name': 'Zz Someone Else'}).product_variant_id
        theirs = self.Spec.create({'product_id': other.id, 'name': 'Colour', 'value': 'Red'})
        self._save({'specs': self._on_screen(self.warranty, self.ports),
                    'specs_removed': [theirs.id]})
        self.assertTrue(theirs.exists())
        self.assertEqual(len(self._rows()), 2)

    def test_new_rows_take_the_screen_order(self):
        screen = [{'name': 'CPU', 'value': 'i5'}] + self._on_screen(self.ports, self.warranty)
        self._save({'specs': screen, 'specs_removed': []})
        self.assertEqual([name for name, _value in self._rows()], ['CPU', 'Ports', 'Warranty'])

    def test_a_screen_without_removed_ids_sends_the_whole_table(self):
        """The older screen: a row it does not send goes, as before."""
        self._save({'specs': self._on_screen(self.ports)})
        self.assertEqual(self._rows(), [('Ports', '2x USB-C')])
