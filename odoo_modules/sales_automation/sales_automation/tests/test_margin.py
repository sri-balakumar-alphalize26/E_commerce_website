# -*- coding: utf-8 -*-
"""One margin, or an own one per category or per group (24 Nov 2026)."""
from odoo.exceptions import ValidationError
from odoo.tests import tagged

from . import test_vendor_window
from .test_only_listed import ListedCase


@tagged('post_install', '-at_install')
class TestMargin(ListedCase):
    _asked = test_vendor_window.TestVendorWindow._asked
    _price = test_vendor_window.TestVendorWindow._price

    def setUp(self):
        super().setUp()
        self.settings = self.env['sa.ai.settings'].sudo().get_settings()
        (self.settings.margin_category_ids | self.settings.margin_group_ids).unlink()
        self.settings.write({'sourcing_window_minutes': 3, 'margin_percent': 20.0, 'min_margin_percent': 0.0, 'bargain_enabled': True,
                             'price_approval_enabled': False, 'vendor_choice_mode': 'auto', 'margin_rules_enabled': False,
                             'margin_rules_by': 'category'})
        self.vendors = self.env['res.partner'].create([{'name': 'Zz V%s' % n, 'phone': '+9715000030%02d' % n} for n in range(3)])

    def _rule(self, percent, categ=None, group=None):
        return self.env['sa.margin.rule'].create({
            'percent': percent, 'categ_id': categ.id if categ else False, 'group_id': group.id if group else False,
            ('cat_settings_id' if categ else 'group_settings_id'): self.settings.id})

    def _quoted(self, request):
        self._price(request, 0, 100.0)
        request._close_sourcing()
        return request.quoted_price

    def test_off_is_the_normal_margin(self):
        request = self._asked()
        self._rule(50.0, categ=request.product_id.categ_id)
        self.assertEqual(self._quoted(request), 120.0)

    def test_by_category(self):
        request = self._asked()
        self._rule(50.0, categ=request.product_id.categ_id)
        self._rule(5.0, group=request.group_id)
        self.settings.margin_rules_enabled = True
        self.assertEqual(self._quoted(request), 150.0)

    def test_a_real_zero(self):
        request = self._asked()
        self._rule(0.0, categ=request.product_id.categ_id)
        self.settings.margin_rules_enabled = True
        self.assertEqual(self._quoted(request), 100.0)

    def test_the_category_above(self):
        top = self.env['product.category'].create({'name': 'Zz top'})
        low = self.env['product.category'].create({'name': 'Zz low', 'parent_id': top.id})
        self._rule(15.0, categ=top)
        self.settings.margin_rules_enabled = True
        self.assertEqual(self.settings._sa_margin_for(low), 15.0)
        self._rule(25.0, categ=low)
        self.settings.invalidate_recordset()
        self.assertEqual(self.settings._sa_margin_for(low), 25.0)
        self.assertEqual(self.settings._sa_margin_for(self.env['product.category']), 20.0)

    def test_by_group(self):
        request = self._asked()
        self._rule(50.0, categ=request.product_id.categ_id)
        self._rule(10.0, group=request.group_id)
        self.settings.write({'margin_rules_enabled': True, 'margin_rules_by': 'group'})
        self.assertAlmostEqual(self._quoted(request), 110.0)

    def test_an_evaluated_enquiry_keeps_its_margin(self):
        request = self._asked()
        self._quoted(request)
        self.settings.margin_percent = 70.0
        self.assertEqual((request._sa_margin(), request._sa_margin_live()), (20.0, 70.0))

    def test_what_cannot_work_is_refused(self):
        categ = self.env['product.category'].create({'name': 'Zz categ'})
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self._rule(501.0, categ=categ)
        self._rule(3.0, categ=categ)
        with self.assertRaisesRegex(ValidationError, 'Zz categ'), self.env.cr.savepoint():
            self.settings.web_save({'margin_rules_enabled': True, 'min_margin_percent': 5.0}, {'id': {}})

    def test_the_pages_open_with_their_preview(self):
        for name in ('margin', 'vendor', 'counter', 'payments', 'address', 'links', 'chatter', 'finder', 'takeover'):
            view = self.env.ref('sales_automation.view_sa_settings_%s_form' % name)
            arch = self.env['sa.ai.settings'].get_views([(view.id, 'form')])['views']['form']['arch']
            self.assertIn('sa_live_preview', arch, name)
        group = self.env.ref('sales_automation.view_sa_sales_group_form')
        self.assertIn('sa_live_preview', self.env['sa.sales.group'].get_views([(group.id, 'form')])['views']['form']['arch'])
        self.assertFalse(self.env.ref('sales_automation.menu_sa_settings_bargain').active)
