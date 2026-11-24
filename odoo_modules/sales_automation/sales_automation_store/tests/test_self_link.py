# -*- coding: utf-8 -*-
"""Hand over: store pickup, and home delivery by a link (24 Nov 2026)."""
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import HttpCase, tagged
from odoo.addons.sales_automation.controllers.wa_link_entry import ALLOWED_TARGETS

from . import test_self_delivery


class LinkCase(test_self_delivery.ListedCase):
    _order = test_self_delivery.TestSelfDelivery._order
    _price = test_self_delivery.TestSelfDelivery._price
    _act = test_self_delivery.TestSelfDelivery._act
    _code = test_self_delivery.TestSelfDelivery._code
    _tx = test_self_delivery.TestSelfDelivery._tx

    def setUp(self):
        super().setUp()
        self.kumar, self.alpha, self.third, self.fourth = self.env['res.partner'].create(
            [{'name': 'Zz S%s' % n, 'phone': '+97150000410%s' % n} for n in range(4)])
        self.customer = self.env['res.partner'].create({'name': 'Zz buyer', 'phone': '+971500006001'})
        Picking, Session = self.env.registry['stock.picking'], self.env.registry['whatsapp.session']
        self.sent, self.refused = [], False

        def send(rec, phone, body):
            return False if self.refused else (self.sent.append((phone, body)) or True)
        for p in (patch.object(Picking, '_sa_store_notify', lambda rec, *a, **k: True),
                  patch.object(Picking, '_sa_session', lambda rec: self.session), patch.object(Session, 'send_message', send)):
            p.start()
            self.addCleanup(p.stop)
        self.req, self.order, self.job = self._order()
        self.env['stock.quant']._update_available_quantity(self.product.product_variant_id, self.job.location_id, 1)
        self.job.write({'sa_delivery_state': 'preparing', 'sa_cod_amount': 24.0})
        self.job.action_assign()
        self.rider = self.env['sa.delivery.partner'].create({'name': 'Zz Ravi', 'phone': '+971501234567'})

    def _link(self, **kw):
        return self._act('self_link', **(kw or {'carrier': 'rider-%s' % self.rider.id}))

    def _steps(self, *names):
        for name in names:
            self.job._sa_self_step(name)


@tagged('post_install', '-at_install')
class TestSelfLink(LinkCase):

    def test_pickup(self):
        self._act('self_collect')
        self.assertEqual((self.job.sa_self_way, [p for p, _b in self.sent]), ('collect', [self.customer.phone]))
        self.assertIn('Store pickup', self.job.sa_stage_text)
        self.assertFalse(self._act('self_code', code=self._code(), cash=True)['self_told'])
        self.assertEqual(self.job.sa_delivery_state, 'delivered')

    def test_not_picked_up(self):
        self._act('self_collect')
        self._act('self_back')
        self.assertEqual((self.job.sa_delivery_state, self.job.sa_self_way), ('ready', False))

    def test_only_riders_and_staff(self):
        staff = self.env['hr.employee'].create({'name': 'Zz Anu', 'mobile_phone': '+971509876543'})
        rows = self.env['stock.picking'].sa_store_carriers()
        keys = {r['key'] for r in rows}
        self.assertTrue({'rider-%s' % self.rider.id, 'staff-%s' % staff.id} <= keys)
        self.assertEqual({r['kind'] for r in rows} - {'rider', 'staff'}, set())
        self.assertNotIn('971500006001', {r['phone'] for r in rows}, 'no customer')

    def test_the_whole_way(self):
        self._link()
        self.assertEqual((self.sent[0][0], self.job.sa_delivery_state, len(self.sent)), ('971501234567', 'accepted', 1))
        self.assertIn('24.00', self.sent[0][1])
        with self.assertRaises(UserError):
            self._steps('parcel')
        self._steps('accept', 'parcel')
        with self.assertRaises(UserError):
            self._steps('reached')
        self._steps('start')
        told = [b for _p, b in self.sent[1:]] + self.said        # a group order is told in its group
        self.assertTrue(any('Zz Ravi' in b and 'on the way' in b for b in told), ascii(told))
        self.assertTrue(self.job._sa_self_finish('123456', True), 'no code before Reached')
        before = len(self.sent)
        self._steps('reached', 'reached')
        self.assertEqual((self.sent[-1][0], len(self.sent)), (self.customer.phone, before + 1), 'one code')
        self.assertTrue(self.job._sa_self_finish(self._code(), False), 'not paid: the tick')
        self.assertFalse(self.job.with_context(sa_by_link=True)._sa_self_finish(self._code(), True))
        self.assertEqual((self.job.sa_delivery_state, self.job.state, self.job.sa_cash_by), ('delivered', 'done', 'Zz Ravi'))
        self.assertFalse(self.job.sa_cash_user_id)
        self.assertFalse(self.job._sa_self_token_ok(self.job.sa_self_token or 'x'))

    def test_a_typed_number(self):
        india = self.env.ref('base.in')
        with self.assertRaises(UserError):
            self._link(country_id=india.id, number='12')
        self.assertFalse(self.sent)
        before = self.env['res.partner'].search_count([])
        self._link(country_id=india.id, number='9811122233', name='Kumar')
        self.assertEqual((self.sent[0][0], self.job.sa_self_name), ('919811122233', 'Kumar'))
        self.assertEqual(self.env['res.partner'].search_count([]), before, 'no contact is made')

    def test_not_sent_changes_nothing(self):
        self.refused = True
        with self.assertRaises(UserError):
            self._link()
        self.assertEqual((self.job.sa_delivery_state, self.job.sa_self_delivery), ('preparing', False))

    def test_another_person(self):
        self._link()
        old = self.job.sa_self_token
        self._link(country_id=self.env.ref('base.in').id, number='9811122233')
        self.assertFalse(self.job._sa_self_token_ok(old))
        self.assertTrue(self.job._sa_self_token_ok(self.job.sa_self_token))
        self._steps('accept', 'parcel')
        with self.assertRaises(UserError):
            self._link()

    def test_again(self):
        self._link()
        with self.assertRaises(UserError):
            self._act('self_link_again')
        self.job.sa_self_link_on = fields.Datetime.now() - timedelta(minutes=2)
        self._act('self_link_again')
        self.assertEqual(len(self.sent), 2)

    def test_cannot_deliver(self):
        self._link()
        self._steps('accept', 'parcel', 'start')
        token = self.job.sa_self_token
        self.job._sa_self_back('nobody at home')
        self.assertEqual((self.job.sa_delivery_state, self.job.sa_self_delivery), ('ready', False))
        self.assertIn('nobody at home', self.job._sa_board_extra()['self_failed'])
        self.assertFalse(self.job._sa_self_token_ok(token))

    def test_the_counter_helps(self):
        self._link()
        self._act('self_step')
        self.assertEqual(self.job.sa_delivery_state, 'out_for_delivery')
        self.assertFalse(self._act('self_code', code=self._code(), cash=True)['self_told'])
        self.assertEqual(self.job.sa_delivery_state, 'delivered')

    def test_no_rider_meanwhile(self):
        self._link()
        self.assertFalse(self.job._sa_board_extra()['self_can'])
        with self.assertRaises(UserError):
            self.job.sa_action_call_rider()
        with self.assertRaises(UserError):
            self._act('self_collect')

    def test_cancelled(self):
        self._link()
        token = self.job.sa_self_token
        self.job.sa_action_cancel('changed')
        self.assertFalse(self.job._sa_self_token_ok(token))

    def test_the_doorway_lets_it_in(self):
        self.assertTrue(any(r.match('/wa/staff/12') for r in ALLOWED_TARGETS))


@tagged('post_install', '-at_install')
class TestSelfLinkPage(HttpCase, LinkCase):

    def _url(self, step='', token=None):
        return '/wa/staff/%s%s?token=%s' % (self.job.id, step and '/' + step, token or self.job.sa_self_token)

    def test_looking_changes_nothing(self):
        self._link()
        page = self.url_open(self._url())
        self.assertIn('Accept', page.text)
        self.assertEqual(page.headers['Referrer-Policy'], 'no-referrer')
        self.assertGreaterEqual(self.url_open(self._url('accept')).status_code, 400)
        self.env.invalidate_all()
        self.assertFalse(self.job.sa_self_accepted_on)

    def test_a_wrong_link(self):
        self._link()
        self.assertIn('ended', self.url_open(self._url(token='wrong')).text)
        self.assertIn('ended', self.url_open('/wa/staff/%s/accept' % self.job.id, data={'token': 'wrong'}).text)
        self.env.invalidate_all()
        self.assertFalse(self.job.sa_self_accepted_on)

    def test_the_steps(self):
        self._link()
        token = self.job.sa_self_token
        for step in ('accept', 'parcel', 'start', 'reached'):
            page = self.url_open('/wa/staff/%s/%s' % (self.job.id, step), data={'token': token})
            self.assertEqual(page.status_code, 200, step)
        self.assertIn('6 digits', page.text)
        page = self.url_open('/wa/staff/%s/done' % self.job.id, data={'token': token, 'code': self._code()})
        self.assertIn('cash was received', page.text)
        page = self.url_open('/wa/staff/%s/done' % self.job.id, data={'token': token, 'code': self._code(), 'cash': '1'})
        self.assertIn('ended', page.text)
        self.env.invalidate_all()
        self.assertEqual(self.job.sa_delivery_state, 'delivered')


@tagged('post_install', '-at_install')
class TestPayLinkAgain(LinkCase):

    def test_not_sent_is_not_stamped(self):
        Request = self.env.registry['sa.group.request']
        with patch.object(Request, '_say', lambda rec, *a, **k: False):
            self.assertFalse(self.req._sa_accept_pay_link(self.job))
        self.assertFalse(self.req.sa_pay_link_sent_on)
        self.assertIn('not sent', self.job.sa_last_error)

    def test_the_shorter_window(self):
        windows = []
        Request = self.env.registry['sa.group.request']
        with patch.object(Request, '_say', lambda rec, *a, **k: windows.append(rec.env.context.get('sa_private_window')) or True):
            self.req._sa_accept_pay_link(self.job)
        self.assertEqual(windows, [60])
        self.assertTrue(self.req.sa_pay_link_sent_on)
