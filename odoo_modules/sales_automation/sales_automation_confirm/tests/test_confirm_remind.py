# -*- coding: utf-8 -*-
"""The "still waiting for you" reminder of the product page (23 Nov 2026): not
for a product the customer has left for another, and at most once."""
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.addons.sales_automation.tests.test_only_listed import ListedCase
from odoo.tests import tagged

RAVI = '919800066701'


@tagged('post_install', '-at_install')
class TestConfirmRemind(ListedCase):

    def setUp(self):
        super().setUp()
        self.env['sa.confirm.link'].sudo().search([('kind', '=', 'customer'), ('reminded_on', '=', False)]).write(
            {'reminded_on': fields.Datetime.now()})

    def _waiting(self, phone=RAVI):
        req = self._req('zzboard', requester_phone=phone, product_id=self.product.id, state='awaiting_confirm')
        link = self.env['sa.confirm.link'].sudo().create({
            'request_id': req.id, 'kind': 'customer', 'sent_on': fields.Datetime.now() - timedelta(hours=1)})
        return req, link

    def _remind(self):
        self.said.clear()
        self.env['sa.confirm.link']._cron_confirm_remind()
        return [s for s in self.said if 'Still waiting' in s]

    def test_once(self):
        _req, link = self._waiting()
        self.assertEqual(len(self._remind()), 1)
        self.assertTrue(link.reminded_on)
        self.assertEqual(self._remind(), [])

    def test_not_for_one_they_left_for_another(self):
        self._waiting()
        self._req('zz another', requester_phone=RAVI, state='awaiting_confirm')
        self.assertEqual(self._remind(), [])
        self.assertEqual(self._remind(), [], 'nor later')

    def test_not_after_hi(self):
        self._waiting()
        self._req('hi', requester_phone=RAVI, state='dropped', drop_reason='not_product')
        self.assertEqual(self._remind(), [])

    def test_another_customers_enquiry_changes_nothing(self):
        self._waiting()
        self._req('zz another', requester_phone='919800066702', state='awaiting_confirm')
        self.assertEqual(len(self._remind()), 1)

    def test_not_for_a_closed_one(self):
        req, _link = self._waiting()
        req._drop('stale')
        self.assertEqual(self._remind(), [])

    def test_kept_before_it_is_sent(self):
        """What was sent is never sent again, even when the sending fails."""
        _req, link = self._waiting()
        seen = []
        with patch.object(self.env.registry['sa.group.request'], '_say',
                          lambda rec, body, addressed=True: seen.append(bool(link.reminded_on)) or (_ for _ in ()).throw(RuntimeError('zz'))):
            self.env['sa.confirm.link']._cron_confirm_remind()
        self.assertEqual(seen, [True])
        self.assertEqual(self._remind(), [])
