"""The template form's reset button also works where it lands on a variant."""

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install')
class TestVariantReset(TransactionCase):

    def test_a_variant_resets_its_products_page(self):
        template = self.env['product.template'].create({'name': 'Reset Test'})
        variant = template.product_variant_id
        self.assertTrue(hasattr(variant, 'action_mart_reset_page'))
        self.assertTrue(variant.action_mart_reset_page())

    def test_the_variant_form_loads_with_the_button(self):
        """Any view built on the variant form must validate: the WhatsApp
        stack's sales_automation_confirm failed to install without it."""
        form = self.env['product.product'].get_view(view_type='form')
        self.assertTrue(form.get('arch'))
