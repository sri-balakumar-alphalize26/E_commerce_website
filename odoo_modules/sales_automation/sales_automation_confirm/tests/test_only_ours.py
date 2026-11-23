# -*- coding: utf-8 -*-
"""A model typed after "Not listed", and a size typed in the customer's own
words, are looked up in the shop's database and never shown or asked of a
vendor when it does not have them (owner, 23 Nov 2026)."""
import json
from unittest.mock import patch

from odoo import fields
from odoo.addons.sales_automation.tests.test_only_listed import ListedCase
from odoo.tests import tagged


@tagged('post_install', '-at_install')
class TestOnlyOurs(ListedCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        registry = cls.env.registry
        box = cls

        def ask(self, body, buttons):
            box.said.append('%s || %s' % (body, ' | '.join(b['title'] for b in buttons)))
            return True
        for p in (patch.object(registry['sa.outbox.guard'], 'claim', lambda self, key, seconds=60: True),
                  patch.object(registry['sa.group.request'], '_ask', ask)):
            p.start()
            cls.addClassCleanup(p.stop)
        cls.env['sa.ai.settings'].sudo().get_settings().confirm_enabled = True

    def _links(self, req):
        return self.env['sa.confirm.link'].sudo().search([('request_id', '=', req.id)])

    def _refused(self, req):
        self.assertEqual((req.state, req.drop_reason), ('dropped', 'not_stocked'))
        self.assertTrue(any("don't have" in s for s in self.said), self.said)
        self.assertFalse(self._links(req), 'no page')
        self.assertEqual(self.asked, [], 'no picture, no vendor')

    # ------------------------------------------------------------ "Not listed", then a model
    def _finding(self, **vals):
        return self._req('zzthing', **dict({'state': 'finding', 'finder_step': 'model_text', 'finder_seed': 'zzthing',
                                            'finder_asked_on': fields.Datetime.now()}, **vals))

    def test_a_typed_model_we_do_not_have(self):
        req = self._finding()
        self.assertTrue(req._finder_confirm({'kind': 'market', 'name': 'Zzkeyz 0660'}))
        self._refused(req)

    def test_a_typed_model_we_have(self):
        req = self._finding()
        req._finder_confirm({'kind': 'market', 'name': 'Zzboard Q77660'})
        self.assertEqual(req.product_id, self.product)
        self.assertNotEqual(req.state, 'dropped')

    def test_a_typed_model_several_of_ours_have(self):
        other = self.product.copy({'name': 'Laptop Zzboard Toshiba Q-77660 Black'})
        req = self._finding()
        req._finder_confirm({'kind': 'market', 'name': 'Zzboard Q77660'})
        self.assertEqual(req.candidate_product_ids, self.product | other)
        self.assertFalse(self._links(req), 'they choose first')

    def test_a_tapped_product_of_ours_still_works(self):
        req = self._finding()
        req._finder_confirm({'kind': 'ours', 'product_id': self.product.id, 'name': self.product.name})
        self.assertEqual(req.candidate_product_ids, self.product)
        self.assertEqual((req.state, req.finder_kind), ('finding', 'ours'))

    # ------------------------------------------------------------ a size we do not have
    def _with_sizes(self):
        attribute = self.env['product.attribute'].create({'name': 'Zz Capacity', 'create_variant': 'always'})
        values = self.env['product.attribute.value'].create(
            [{'name': n, 'attribute_id': attribute.id} for n in ('8GB', '16GB')])
        product = self.env['product.template'].create({
            'name': 'Zz Memory', 'type': 'consu', 'sale_ok': True,
            'attribute_line_ids': [(0, 0, {'attribute_id': attribute.id, 'value_ids': [(6, 0, values.ids)]})]})
        req = self._req('zz memory', product_id=product.id, state='awaiting_confirm',
                        sa_attr_typing=json.dumps({'attr': attribute.id, 'chosen': [], 'skipped': [], 'noted': []}))
        return req

    def test_a_typed_size_we_do_not_have(self):
        req = self._with_sizes()
        req._sa_attr_typed('64GB')
        self.assertFalse(req.sa_attr_notes, 'never in the name')
        self.assertTrue(any("don't have" in s and '64GB' in s for s in self.said), self.said)
        self.assertTrue(any('8GB' in s.split('||')[-1] and '16GB' in s.split('||')[-1] for s in self.said if '||' in s),
                        'the real ones are offered again')
        self.assertFalse(self._links(req))

    def test_a_typed_word_that_is_no_size(self):
        req = self._with_sizes()
        req._sa_attr_typed('the big red one')
        self.assertFalse(req.sa_attr_notes)
        self.assertTrue(any("don't have" in s for s in self.said))

    def test_a_typed_size_we_have(self):
        req = self._with_sizes()
        req._sa_attr_typed('16gb')
        self.assertFalse(any("don't have" in s for s in self.said), self.said)
        self.assertFalse(req.sa_attr_notes)
        self.assertIn('16GB', req.sa_variant_id.display_name)

    # ------------------------------------------------------------ as before
    def test_our_own_out_of_stock_product_still_goes_to_the_vendors(self):
        req = self._req('zzboard q77660', product_id=self.product.id, state='awaiting_confirm')
        started = []
        with patch.object(self.env.registry['sa.group.request'], '_start_sourcing', lambda self, vendors: started.append(self.id) or True):
            req.with_context(sa_confirm_accepted=True)._on_confirmed()
        self.assertFalse(any("don't have" in s for s in self.said), self.said)
        self.assertNotEqual(req.state, 'dropped')
