# -*- coding: utf-8 -*-
"""What the Orders and Enquiries screens get (23 Nov 2026)."""
import time
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.addons.sales_automation.tests.test_only_listed import ListedCase
from odoo.exceptions import UserError
from odoo.tests import new_test_user, tagged


@tagged('post_install', '-at_install')
class TestBoards(ListedCase):

    def _done(self, n=1, **vals):
        return self.env['sa.group.request'].create([dict({
            'group_id': self.group.id, 'requester_phone': '919800077744', 'requester_name': 'Zz Maya', 'raw_text': 'zz thing %s' % i,
            'product_id': self.product.id, 'state': 'order_created'}, **vals) for i in range(n)])

    def test_enquiry_pages(self):
        self._done(60)
        self._done(2, state='dropped', drop_reason='not_stocked', requester_name='Zz Omar')
        Request = self.env['sa.group.request']
        one = Request.sa_enquiry_board('ordered', 'Zz Maya', 30, 0)
        self.assertEqual((len(one['rows']), one['more']), (50, True))
        two = Request.sa_enquiry_board('ordered', 'Zz Maya', 30, 50)
        self.assertEqual((len(two['rows']), two['more']), (10, False))
        self.assertFalse({r['id'] for r in one['rows']} & {r['id'] for r in two['rows']})
        closed = Request.sa_enquiry_board('closed', 'Zz Omar', 30, 0)
        self.assertEqual([r['reason'] for r in closed['rows']], ['We Do Not Sell It'] * 2)
        self.assertGreaterEqual(one['counts']['ordered'], 60)
        row = one['rows'][0]
        self.assertTrue(row['at'].endswith('Z') and row['product'] and row['ref'])
        self.assertEqual(Request.sa_enquiry_board('ordered', '#' + row['ref'], 30, 0)['rows'][0]['id'], row['id'])
        old = self._done(1, requester_name='Zz Old')
        self.env.flush_all()
        self.env.cr.execute("UPDATE sa_group_request SET create_date = now() - interval '40 days' WHERE id = %s", [old.id])
        self.env.invalidate_all()
        self.assertFalse(Request.sa_enquiry_board('ordered', 'Zz Old', 30, 0)['rows'])
        self.assertTrue(Request.sa_enquiry_board('ordered', 'Zz Old', 90, 0)['rows'])

    def test_enough_at_once(self):
        self._done(500)
        started = time.time()
        self.env['sa.group.request'].sa_enquiry_board('ordered', '', 30, 0)
        self.assertLess(time.time() - started, 1.5)

    def test_queue_rows_have_what_the_list_shows(self):
        req = self._req('zzboard q77660', product_id=self.product.id, state='sourcing', sourcing_vendor_ids=[(6, 0, self.vendor.ids)],
                        sourcing_deadline=fields.Datetime.now() + timedelta(minutes=2), quoted_price=0.0)
        data = self.env['sa.group.request'].sa_enquiry_queue()
        row = [r for r in data['tracking'] if r['id'] == req.id][0]
        self.assertEqual((row['group'], row['better'], row['asked'], row['closed']), ('Zz Listed', False, 1, False))
        self.assertTrue(row['at'])
        self.assertIn('ordered', data['counts'])

    def test_detail_ranks_the_vendors(self):
        vendors = self.env['res.partner'].create([{'name': 'Zz D%s' % n, 'phone': '+9715000030%02d' % n} for n in range(4)])
        self.env['sa.ai.settings'].sudo().get_settings().write({'margin_percent': 20.0, 'price_approval_enabled': False})
        req = self._req('zzboard q77660', product_id=self.product.id, state='sourcing', sourcing_vendor_ids=[(6, 0, vendors.ids)],
                        sourcing_deadline=fields.Datetime.now(), sa_vendor_no_ids=[(6, 0, vendors[3].ids)])
        quote = lambda n, price: self.env['sa.vendor.quote'].create({  # noqa: E731
            'request_id': req.id, 'partner_id': vendors[n].id, 'price': price, 'matched_by': 'direct'})
        quote(1, 22.0)
        quote(0, 20.0)
        req._close_sourcing()
        late = quote(2, 19.0)
        detail = self.env['sa.group.request'].sa_enquiry_detail(req.id)
        self.assertEqual([(v['name'], v['rank'], v['late'], v['said_no']) for v in detail['vendors']],
                         [('Zz D0', 1, False, False), ('Zz D1', 2, False, False), ('Zz D2', 0, True, False), ('Zz D3', 0, False, True)])
        self.assertEqual((detail['best_cost'], detail['margin'], detail['quoted_price']), (20.0, 20.0, 24.0))
        self.assertEqual((detail['better']['quote_id'], detail['better']['less']), (late.id, 1.0))
        row = [r for r in self.env['sa.group.request'].sa_enquiry_queue()['tracking'] if r['id'] == req.id][0]
        self.assertEqual((row['better'], row['sell']), (True, 24.0))
        self.env['sa.group.request'].sa_enquiry_use_late(req.id, late.id)
        self.assertEqual(round(req.quoted_price, 2), 22.8)
        with self.assertRaises(UserError):
            self.env['sa.group.request'].sa_enquiry_use_late(self._done().id, late.id)

    def test_orders_rows_and_done(self):
        data = self.env['stock.picking'].sa_store_queue()
        self.assertIn('done', data)
        for row in data['rows']:
            self.assertTrue({'at', 'total', 'in_stock', 'pay_link', 'can_send_pay_link'} <= set(row))
        job = self.env['stock.picking'].sudo().search([('sa_delivery_state', '!=', False), ('picking_type_code', '=', 'outgoing')], limit=1)
        if job:
            job.write({'sa_delivery_state': 'delivered', 'sa_delivered_on': fields.Datetime.now()})
            done = [r for r in self.env['stock.picking'].sa_store_queue()['done'] if r['id'] == job.id]
            self.assertEqual(done[0]['state'], 'delivered')

    def test_send_pay_link_from_the_counter(self):
        job = self.env['stock.picking'].sudo().search([('picking_type_code', '=', 'outgoing')], limit=1)
        if not job:
            self.skipTest('no delivery here')
        with patch.object(self.env.registry['sale.order'], '_sa_group_enquiry', lambda rec: rec.env['sa.group.request']):
            with self.assertRaises(UserError):
                self.env['stock.picking'].sa_store_act(job.id, 'send_pay_link')

    def test_the_browsers_time_zone(self):
        user = new_test_user(self.env, 'zz-tz', groups='base.group_user')
        Users = self.env['res.users'].with_user(user)
        self.assertTrue(getattr(type(Users).sa_set_browser_tz, '_api_model', False) or Users.sa_set_browser_tz('Asia/Dubai'))
        from odoo.service.model import call_kw
        self.assertTrue(call_kw(Users, 'sa_set_browser_tz', ['Asia/Dubai'], {}), 'as the browser calls it')
        self.assertEqual(user.tz, 'Asia/Dubai')
