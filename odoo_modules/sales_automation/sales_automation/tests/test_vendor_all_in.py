# -*- coding: utf-8 -*-
"""The price goes out once every vendor asked has answered (23 Nov 2026)."""
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestVendorAllIn(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        for p in (patch.object(env.registry['sa.group.request'], '_say', lambda self, body, addressed=True: True),):
            p.start()
            cls.addClassCleanup(p.stop)
        session = env['whatsapp.session'].create({
            'name': 'SA all in', 'gateway_api_key': 'x', 'instance_name': 'sa-all-in'})
        cls.group = env['sa.sales.group'].create({
            'name': 'Zz All In', 'group_jid': '120363000000000033@g.us',
            'session_id': session.id, 'group_type': 'customer'})
        cls.a, cls.b = (env['res.partner'].create({'name': 'Zz Vendor %s' % n, 'phone': '+97150000010%s' % n}) for n in (1, 2))
        cls.product = env['product.template'].create({'name': 'Zz all in jack', 'type': 'consu'})

    def _req(self, vendors=None, **vals):
        return self.env['sa.group.request'].create(dict({
            'group_id': self.group.id, 'requester_phone': '919800099944', 'raw_text': 'jack',
            'product_id': self.product.id, 'state': 'sourcing',
            'sourcing_deadline': fields.Datetime.now() + timedelta(minutes=10),
            'sourcing_vendor_ids': [(6, 0, (vendors or (self.a | self.b)).ids)]}, **vals))

    def _quote(self, req, vendor, price=5.0, **vals):
        return self.env['sa.vendor.quote'].create(dict({
            'request_id': req.id, 'partner_id': vendor.id, 'price': price, 'matched_by': 'direct'}, **vals))

    def _closing(self, req):
        return bool(req.sourcing_deadline and req.sourcing_deadline <= fields.Datetime.now())

    def test_the_only_vendor_answered(self):
        req = self._req(self.a)
        self._quote(req, self.a)
        self.assertTrue(self._closing(req))

    def test_one_is_still_to_answer(self):
        req = self._req()
        self._quote(req, self.a)
        self.assertFalse(self._closing(req))
        self._quote(req, self.b, 4.0)
        self.assertTrue(self._closing(req))

    def test_a_no_is_an_answer(self):
        req = self._req()
        self._quote(req, self.a)
        req.write({'sa_vendor_no_ids': [(4, self.b.id)]})
        self.assertTrue(self._closing(req))

    def test_accepted_without_a_price_is_waited_for(self):
        req = self._req()
        self._quote(req, self.a)
        req.write({'sa_vendor_yes_ids': [(4, self.b.id)]})
        self.assertFalse(self._closing(req))

    def test_all_said_no_goes_to_the_desk_at_once(self):
        req = self._req(self.a)
        req.write({'sa_vendor_no_ids': [(4, self.a.id)]})
        self.assertTrue(self._closing(req))

    def test_a_held_price_is_an_answer(self):
        req = self._req(self.a)
        req._sa_hold_price(self.a.id, self.a.phone, 'A', 100.0, 'INR')
        self.assertTrue(self._closing(req))

    def test_a_vendor_group_keeps_the_window(self):
        req = self._req(self.a, sourcing_group_id=self.group.id)
        self._quote(req, self.a)
        self.assertFalse(self._closing(req))

    def test_somebody_elses_price_does_not_count_for_them(self):
        req = self._req(self.a)
        self._quote(req, self.b)
        self.assertFalse(self._closing(req))

    def test_the_shops_own_price_changes_nothing_here(self):
        req = self._req(self.a)
        self._quote(req, self.a, matched_by='manual')
        self.assertFalse(self._closing(req))

    def test_not_after_it_moved_on(self):
        for vals in ({'state': 'quoted'}, {'state': 'dropped'}, {'sa_price_choice_pending': True}):
            req = self._req(self.a, **vals)
            before = req.sourcing_deadline
            self._quote(req, self.a)
            self.assertEqual(req.sourcing_deadline, before, vals)

    def test_the_closing_job_is_called_now(self):
        cron = self.env.ref('sales_automation.cron_sa_close_sourcing')
        before = self.env['ir.cron.trigger'].sudo().search_count([('cron_id', '=', cron.id)])
        req = self._req(self.a)
        self._quote(req, self.a)
        self.assertGreater(self.env['ir.cron.trigger'].sudo().search_count([('cron_id', '=', cron.id)]), before)

    def test_the_cheapest_wins(self):
        req = self._req()
        self._quote(req, self.a, 9.0)
        cheap = self._quote(req, self.b, 4.0)
        won = []
        with patch.object(self.env.registry['sa.group.request'], '_apply_winning_quote',
                          lambda rec, quote: won.append(quote.id) or True):
            self.env['sa.group.request']._cron_close_sourcing()
        self.assertIn(cheap.id, won)
