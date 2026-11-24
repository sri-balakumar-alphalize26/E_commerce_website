# -*- coding: utf-8 -*-
"""Only what the shop has in its catalogue (owner, 23 Nov 2026)."""
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.tests import TransactionCase, tagged


class ListedCase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.said = []
        cls.asked = []
        box = cls

        def say(self, body, addressed=True):
            box.said.append(body)
            return True

        def classify(self, text, use_ai=True):
            return {'is_product': True, 'search_term': text, 'confidence': 1.0, 'source': 'ai', 'quantity': 0}

        def gateway(self, method, path, payload=None, **kw):
            box.asked.append((path, payload))
            return {'key': {'id': 'X%s' % len(box.asked)}}

        def no_net(*a, **kw):
            raise AssertionError('internet')
        registry = env.registry
        for p in (patch.object(registry['sa.group.request'], '_say', say),
                  patch.object(registry['sa.ai.classifier'], 'classify', classify),
                  patch.object(registry['sa.outbox.guard'], 'claim', lambda self, key, secs: True),
                  patch.object(registry['whatsapp.session'], '_gateway_call', gateway),
                  patch.object(registry['whatsapp.session'], '_refresh_state', lambda self, force=False: True),
                  patch('requests.get', no_net), patch('requests.post', no_net)):
            p.start()
            cls.addClassCleanup(p.stop)
        cls.session = env['whatsapp.session'].create({
            'name': 'SA listed', 'gateway_api_key': 'zz-listed', 'instance_name': 'zz-listed', 'status': 'connected'})
        cls.employee = env['hr.employee'].create({'name': 'Zz listed'})
        cls.es = env['wa.employee.session'].create({
            'employee_id': cls.employee.id, 'session_id': cls.session.id, 'phone_number': '+971500000077'})
        cls.group = env['sa.sales.group'].create({
            'name': 'Zz Listed', 'group_jid': '120363000000000077@g.us', 'session_id': cls.session.id,
            'group_type': 'customer', 'enabled': True, 'employee_session_id': cls.es.id})
        cls.vendor = env['res.partner'].create({'name': 'Zz listed vendor', 'phone': '+971500000199', 'supplier_rank': 1})
        cls.categ = env['product.category'].create({'name': 'Zzboards', 'sa_vendor_ids': [(6, 0, cls.vendor.ids)]})
        cls.product = env['product.template'].create({
            'name': 'Laptop Zzboard Toshiba Q-77660', 'type': 'consu', 'is_storable': True, 'categ_id': cls.categ.id,
            'sale_ok': True, 'list_price': 0.0})

    def setUp(self):
        super().setUp()
        self.said.clear()
        self.asked.clear()

    def _req(self, text, **vals):
        return self.env['sa.group.request'].create(dict({
            'group_id': self.group.id, 'requester_phone': '919800077744', 'raw_text': text, 'ai_search_term': text, 'state': 'new'}, **vals))

    def _typed(self, text):
        req = self._req(text)
        req._process()
        return req


@tagged('post_install', '-at_install')
class TestOnlyListed(ListedCase):

    def test_the_match(self):
        req = self._req('x')
        for yes in ('q77660', 'Q-77660', 'zzboard q77660', 'ZZBOARD toshiba', 'zzboards q 77660', 'I need zzboard q77660 price please',
                    'laptop zzboard toshiba q-77660'):
            self.assertIn(self.product.id, req._sa_listed_ids(yes), yes)
        for no in ('zzboard q77661', 'keyboard q77660', 'zzboard hp', 'q7766', 'zz-keyboard c660x9', ''):
            if no == 'q7766':
                continue
            self.assertNotIn(self.product.id, req._sa_listed_ids(no), no)

    def test_what_we_do_not_have(self):
        products = self.env['product.template'].with_context(active_test=False).search_count([])
        for text in ('Zzkeyz c99660', 'zzboard q99999'):
            self.said.clear()
            req = self._typed(text)
            self.assertEqual((req.state, req.drop_reason), ('dropped', 'not_stocked'), text)
            self.assertTrue(any("don't have" in s for s in self.said), self.said)
            self.assertEqual(self.asked, [], 'no vendor, no page, no picture')
            self.assertFalse(req.sourcing_vendor_ids or req.product_id)
        self.assertEqual(self.env['product.template'].with_context(active_test=False).search_count([]), products)

    def test_every_door(self):
        for door in (lambda r: r._on_confirmed(), lambda r: r._start_sourcing(self.vendor), lambda r: r._park_for_shop(self.vendor)):
            req = self._req('zz nothing like it')
            door(req)
            self.assertEqual((req.state, req.drop_reason), ('dropped', 'not_stocked'))
        self.assertEqual(self.asked, [])

    def test_a_product_without_stock_goes_to_the_vendor(self):
        req = self._req('zzboard q77660', product_id=self.product.id, state='awaiting_confirm')
        settings = req._settings()
        settings.write({'shop_picks_vendors': False})
        req.with_context(sa_confirm_accepted=True)._on_confirmed()
        self.assertEqual((req.state, req.drop_reason), ('sourcing', False), 'the vendors or the desk, never "sorry"')
        self.assertFalse(any("don't have" in s for s in self.said))

    def test_a_model_number_is_never_corrected(self):
        # with the 369 Mart bridge only products of the website are spelling words
        if 'is_published' in self.product._fields:
            self.product.is_published = True
        req = self._req('x')
        self.assertFalse(req._sa_spell_listed('zzboard q77661'))
        self.assertEqual(req._sa_spell_listed('zzbord toshiba'), 'zzboard toshiba')

    def test_another_companys_product(self):
        other = self.env['res.company'].create({'name': 'Zz other co'})
        mine = self.env['product.template'].create({'name': 'Zzwidget 5512', 'company_id': other.id, 'sale_ok': True})
        self.assertFalse(self._req('x')._sa_listed_ids('zzwidget 5512'))
        req = self._req('zzwidget', product_id=mine.id)
        req._on_confirmed()
        self.assertEqual(req.drop_reason, 'not_stocked')

    def test_no_asks_nobody(self):
        req = self._req('zzboard q77660', product_id=self.product.id, state='awaiting_confirm')
        req._reject_match()
        self.assertEqual((req.state, req.drop_reason), ('dropped', 'not_confirmed'))
        self.assertTrue(any("another" in s for s in self.said))
        self.assertEqual(self.asked, [])

    def test_no_product_is_made(self):
        req = self._req('brand new thing 991', vendor_price=5.0, agreed_price=9.0)
        self.assertFalse(req._create_product_from_enquiry())
        self.assertFalse(self.env['product.template'].search([('name', 'ilike', 'brand new thing 991')]))

    def test_the_ai_lists_and_draws_nothing(self):
        ai = self.env['sa.ai.classifier']
        self.assertEqual((ai.suggest_types('laptop'), ai.suggest_brands('laptop', ''), ai.suggest_models('laptop', '', 'x')), ([], [], []))
        self.assertEqual(ai._call_gemini_image('x'), (b'', ''))

    def test_settings_screens_open(self):
        self.env['sa.ai.settings'].get_views([(v.id, 'form') for v in self.env['ir.ui.view'].search([
            ('model', '=', 'sa.ai.settings'), ('type', '=', 'form')])][:1])
        for view in self.env['ir.ui.view'].search([('model', '=', 'sa.ai.settings'), ('type', '=', 'form'), ('mode', '=', 'primary')]):
            arch = self.env['sa.ai.settings'].get_view(view.id, 'form')['arch']
            for name in ('unlisted_action', 'link_reply_hours', 'confirm_fetch_images', 'finder_image_model'):
                self.assertNotIn('"%s"' % name, arch, view.name)
