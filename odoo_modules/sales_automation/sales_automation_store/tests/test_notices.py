# -*- coding: utf-8 -*-
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.addons.sales_automation.tests.test_only_listed import ListedCase
from odoo.exceptions import AccessError
from odoo.tests import new_test_user, tagged


@tagged('post_install', '-at_install')
class TestNotices(ListedCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.Notice = env['sa.notice']
        env['sa.ai.settings'].sudo().get_settings().notice_on = True
        cls.manager = new_test_user(env, 'zz-note-manager', groups='base.group_user,sales_automation.group_sa_manager')
        cls.clerk = new_test_user(env, 'zz-note-clerk', groups='base.group_user,sales_automation.group_sa_user')
        cls.other = new_test_user(env, 'zz-note-other', groups='base.group_user,sales_automation.group_sa_user')
        cls.outsider = new_test_user(env, 'zz-note-out', groups='base.group_user')
        cls.employee.user_id = cls.clerk
        cls.sent = []
        box = cls

        def bus_send(rec, kind, message, **kw):
            if kind == 'sa_notice/new':
                box.sent.append((rec.user_ids[:1].login, message))
        p = patch.object(env.registry['res.partner'], '_bus_send', bus_send)
        p.start()
        cls.addClassCleanup(p.stop)

    def setUp(self):
        super().setUp()
        self.sent.clear()

    def _ask(self, **vals):
        return self._req('zzboard', **dict({'product_id': self.product.id, 'state': 'sourcing', 'requester_name': 'Zz Ravi',
                                            'currency_id': self.env.company.currency_id.id}, **vals))

    def _price(self, req, vendor, price, **vals):
        partner = self.env['res.partner'].create({'name': vendor, 'phone': '+97150000%04d' % int(price)})
        return self.env['sa.vendor.quote'].create(dict({
            'request_id': req.id, 'partner_id': partner.id, 'vendor_name': vendor, 'price': price,
            'currency_id': self.env.company.currency_id.id}, **vals))

    def _order(self):
        return self.env['sale.order'].create({
            'partner_id': self.env['res.partner'].create({'name': 'Zz Ravi'}).id,
            'order_line': [(0, 0, {'product_id': self.product.product_variant_id.id, 'product_uom_qty': 1,
                                   'price_unit': 100.0, 'tax_ids': [(6, 0, [])]})]})

    def _notes(self, kind, req=None):
        return self.Notice.search([('kind', '=', kind)] + ([('request_id', '=', req.id)] if req else []))

    def _told(self):
        return {login for login, _m in self.sent}

    # ------------------------------------------------------------ prices
    def test_prices_of_one_enquiry_are_one_note(self):
        req = self._ask()
        self._price(req, 'Zz A', 80.0)
        self._price(req, 'Zz B', 75.0)
        note = self._notes('price', req)
        self.assertEqual(len(note), 1)
        self.assertIn('2 prices', note.title)
        self.assertIn('Zz B', note.body)
        self.assertIn('75.00', note.body)
        self.assertTrue({'zz-note-manager', 'zz-note-clerk'} <= self._told())
        self.assertFalse({'zz-note-other', 'zz-note-out'} & self._told(), "another group's clerk is not told")

    def test_a_price_set_by_hand_is_no_news(self):
        req = self._ask()
        self._price(req, 'Zz A', 80.0, matched_by='manual')
        self.assertFalse(self._notes('price', req))

    def test_a_cheaper_vendor_is_for_managers(self):
        req = self._ask()
        best = self._price(req, 'Zz A', 80.0)
        req.write({'state': 'quoted', 'best_quote_id': best.id, 'sa_evaluated_on': fields.Datetime.now()})
        self.sent.clear()
        self._price(req, 'Zz E', 60.0)
        note = self._notes('cheaper', req)
        self.assertEqual(len(note), 1)
        self.assertIn('20.00', note.body)
        told = [login for login, m in self.sent if m['kind'] == 'cheaper']
        self.assertIn('zz-note-manager', told)
        self.assertNotIn('zz-note-clerk', told)
        self.assertEqual({m['level'] for _l, m in self.sent if m['kind'] == 'cheaper'}, {'red'})
        self._price(req, 'Zz F', 90.0)
        self.assertEqual(len(self._notes('cheaper', req)), 1, 'a dearer one is no news')

    # ------------------------------------------------------------ orders and money
    def test_a_new_order_once(self):
        req = self._ask(state='awaiting_order_confirm')
        order = self._order()
        Request = self.env.registry['sa.group.request']
        note = self.Notice._tell('order', 'New order', 'x', 'order|%s' % order.id, request=req, order=order)
        self.assertEqual(self.Notice._tell('order', 'New order', 'x', 'order|%s' % order.id, request=req, order=order), note)
        self.assertEqual(len([m for _l, m in self.sent if m['kind'] == 'order']), len(note.user_ids))
        self.assertTrue(hasattr(Request, '_sa_notice_who'))

    def test_the_payment(self):
        order = self._order()
        req = self._ask(state='order_created', order_id=order.id)
        Request = self.env.registry['sa.group.request']
        with patch.object(Request, '_sa_paid_invoice', lambda self, o: o.invoice_ids), \
                patch.object(Request, '_sa_paid_send_invoice', lambda self, inv: True), \
                patch.object(Request, '_sa_paid_after', lambda self, o: True), \
                patch.object(Request, '_sa_pay_mail', lambda self, o: True):
            req.with_context(sa_after_now=True)._sa_group_confirmed(order)
        note = self._notes('paid', req)
        self.assertEqual(len(note), 1)
        self.assertIn('Zz Ravi', note.body)

    # ------------------------------------------------------------ the number
    def test_a_number_that_goes_off(self):
        self.session.status = 'connected'
        self.session.status = 'disconnected'
        note = self._notes('whatsapp').filtered(lambda n: n.session_id == self.session)
        self.assertEqual(len(note), 1)
        self.assertEqual(note.user_ids & (self.manager | self.clerk), self.manager)
        self.session.status = 'error'
        self.assertEqual(len(self._notes('whatsapp').filtered(lambda n: n.session_id == self.session)), 1)

    # ------------------------------------------------------------ never in the way
    def test_a_note_that_fails_stops_nothing(self):
        req = self._ask()
        with patch.object(self.env.registry['sa.notice'], '_tell_now', side_effect=RuntimeError('zz')), \
                self.assertLogs('odoo.addons.sales_automation_store', 'ERROR'):
            quote = self._price(req, 'Zz A', 80.0)
        self.assertTrue(quote.exists())
        self.assertFalse(self._notes('price', req))

    def test_switched_off(self):
        self.env['sa.ai.settings'].sudo().get_settings().notice_on = False
        req = self._ask()
        self._price(req, 'Zz A', 80.0)
        self.assertFalse(self._notes('price', req))
        self.assertEqual(self.sent, [])
        self.assertEqual(self.Notice.with_user(self.manager).sa_notices(), {'allowed': False, 'unread': 0, 'rows': [], 'waiting': []},
                         'no panel, no bell')
        self.env['sa.ai.settings'].sudo().get_settings().notice_on = True
        self._price(req, 'Zz B', 70.0)
        self.assertTrue(self._notes('price', req), 'on again')
        self.assertTrue(self.Notice.with_user(self.manager).sa_notices()['allowed'])

    def test_it_changes_and_sends_nothing(self):
        req = self._ask()
        before = (req.state, req.best_quote_id, req.quoted_price)
        self._price(req, 'Zz A', 80.0)
        self.assertEqual(before, (req.state, req.best_quote_id, req.quoted_price))
        self.assertFalse(self.said or self.asked)

    # ------------------------------------------------------------ the bell
    def test_the_bell(self):
        req = self._ask()
        self._price(req, 'Zz A', 80.0)
        note = self._notes('price', req)
        mine = self.Notice.with_user(self.clerk)
        data = mine.sa_notices()
        row = [r for r in data['rows'] if r['id'] == note.id][0]
        self.assertEqual((data['allowed'], row['seen'], row['level']), (True, False, 'green'))
        self.assertGreaterEqual(data['unread'], 1)
        self.assertEqual(mine.sa_notice_seen()['unread'], 0)
        self.assertGreaterEqual(self.Notice.with_user(self.manager).sa_notices()['unread'], 1, "another's stay unread")
        self._price(req, 'Zz B', 70.0)
        self.assertEqual(mine.sa_notices()['unread'], 1, 'news again')

    def test_who_may(self):
        req = self._ask()
        self._price(req, 'Zz A', 80.0)
        note = self._notes('price', req)
        self.assertEqual(self.Notice.with_user(self.outsider).sa_notices(), {'allowed': False, 'unread': 0, 'rows': [], 'waiting': []})
        with self.assertRaises(AccessError):
            self.Notice.with_user(self.outsider).sa_notice_seen()
        self.assertNotIn(note.id, [r['id'] for r in self.Notice.with_user(self.other).sa_notices()['rows']])
        self.assertFalse(self.Notice.with_user(self.other).sa_notice_open(note.id))
        with self.assertRaises(AccessError):
            note.with_user(self.clerk).write({'title': 'x'})

    def test_opening(self):
        req = self._ask()
        self._price(req, 'Zz A', 80.0)
        note = self._notes('price', req)
        target = self.Notice.with_user(self.clerk).sa_notice_open(note.id)
        self.assertEqual((target['res_model'], target['res_id']), ('sa.group.request', req.id))
        self.assertIn(self.clerk, note.seen_ids)
        order = self._order()
        paid = self.Notice._tell('paid', 'Payment received', 'x', 'paid|%s' % order.id, request=req, order=order)
        self.assertEqual(self.Notice.with_user(self.clerk).sa_notice_open(paid.id),
                         'sales_automation_store.action_sa_store_screen', 'no right to sales orders: the Store screen')

    def test_each_waiting_enquiry_on_its_own(self):
        pick, pick2 = self._ask(state='awaiting_vendor_pick'), self._ask(state='awaiting_vendor_pick')
        stalled = self._ask(sa_price_stalled=True)
        self._ask(state='quoted')
        mine = self.Notice.with_user(self.clerk)
        rows = {r['id']: r for r in mine.sa_notices()['waiting']}
        self.assertEqual({i: r['kind'] for i, r in rows.items()},
                         {pick.id: 'pick', pick2.id: 'pick', stalled.id: 'stalled'})
        self.assertEqual((rows[pick.id]['ref'], rows[pick.id]['customer']), (pick.ref_code, 'Zz Ravi'))
        self.assertFalse({pick.id, stalled.id} & {r['id'] for r in self.Notice.with_user(self.other).sa_notices()['waiting']})
        self.assertEqual(mine.sa_notice_enquiry(pick.id)['res_id'], pick.id)
        self.assertEqual(self.Notice.with_user(self.other).sa_notice_enquiry(pick.id),
                         'sales_automation_store.action_sa_enquiry_screen')

    def test_old_ones_go(self):
        note = self.Notice._tell('order', 'x', 'y', 'order|zz', request=self._ask())
        note.told_on = fields.Datetime.now() - timedelta(days=15)
        self.Notice._gc_notices()
        self.assertFalse(note.exists())
