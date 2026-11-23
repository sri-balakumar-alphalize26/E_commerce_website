# -*- coding: utf-8 -*-
"""A request Odoo repeats sends nothing again (23 Nov 2026)."""
from types import SimpleNamespace
from unittest.mock import patch

from odoo.addons.whatsapp_gateway.models import send_memo
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestSendOnce(TransactionCase):

    def setUp(self):
        super().setUp()
        self.environ = {}
        fake = SimpleNamespace(httprequest=SimpleNamespace(environ=self.environ), env=self.env)
        p = patch.object(send_memo, 'request', fake)
        p.start()
        self.addCleanup(p.stop)
        self.calls = []
        box = self

        class Answer:
            status_code = 200
            headers = {}
            text = ''

            def json(self):
                return {'key': {'id': 'ID%s' % len(box.calls)}}

        def post(method, url, **kw):
            box.calls.append((url, kw.get('json')))
            return Answer()
        p = patch('odoo.addons.whatsapp_gateway.models.whatsapp_session.requests.request', post)
        p.start()
        self.addCleanup(p.stop)
        self.session = self.env['whatsapp.session'].create({
            'name': 'Zz once', 'gateway_api_key': 'zz-once', 'gateway_url': 'http://127.0.0.1:9', 'instance_name': 'zz-once', 'status': 'connected'})
        self.calls.clear()

    def _send(self, text='hello', path='/message/sendText/zz-once'):
        return self.session._gateway_call('POST', path, {'number': '1', 'text': text})

    def _again(self):
        self.environ[send_memo.KEY].again()

    def test_the_repeat_sends_nothing_and_has_the_same_answer(self):
        first = [self._send('a'), self._send('b')]
        self._again()
        self.assertEqual([self._send('a'), self._send('b')], first)
        self.assertEqual(len(self.calls), 2)
        self._send('c')
        self.assertEqual(len(self.calls), 3, 'what the first try had not sent yet goes out')

    def test_the_same_words_twice_in_one_try_are_two_messages(self):
        self._send('a')
        self._send('a')
        self.assertEqual(len(self.calls), 2)
        self._again()
        self._send('a')
        self._send('a')
        self._send('a')
        self.assertEqual(len(self.calls), 3)

    def test_reading_is_never_remembered(self):
        self.session._gateway_call('GET', '/instance/connectionState/zz-once')
        self._again() if send_memo.KEY in self.environ else None
        self.session._gateway_call('GET', '/instance/connectionState/zz-once')
        self.assertEqual(len(self.calls), 2)

    def test_the_rollback_itself_tells_it(self):
        self._send('a')
        memo = self.environ[send_memo.KEY]
        self.assertIn(memo.again, self.env.cr.postrollback._funcs)

    def test_code_token_and_number_are_taken_over(self):
        group = self.env['sa.sales.group'].create({'name': 'Zz once', 'group_jid': '120363000000000088@g.us', 'session_id': self.session.id})
        product = self.env['product.template'].create({'name': 'Zz once product'})
        sequence = self.env['ir.sequence'].create({'name': 'Zz once', 'code': 'zz.once', 'prefix': 'Z'})
        no_gap = self.env['ir.sequence'].create({'name': 'Zz gap', 'code': 'zz.gap', 'implementation': 'no_gap'})
        partner = self.env['res.partner'].create({'name': 'Zz once'})

        def tried():
            request = self.env['sa.group.request'].create({'group_id': group.id, 'requester_phone': '919800011122', 'raw_text': 'x',
                                                           'product_id': product.id})
            link = self.env['sa.confirm.link'].create({'request_id': request.id, 'kind': 'customer', 'channel': 'whatsapp',
                                                       'phone': '919800011122'})
            order = self.env['sale.order'].create({'partner_id': partner.id})
            order._portal_ensure_token()
            return request.ref_code, link.token, sequence.next_by_id(), order.access_token, order.name, request.id
        one = tried()
        self._again()
        two = tried()
        self.assertEqual(one[:5], two[:5])
        self.assertNotEqual(one[5], two[5])
        self.assertNotEqual(tried()[:3], one[:3], 'a second one in the same try is its own')
        a = no_gap.next_by_id()
        self._again()
        self.assertNotEqual(no_gap.next_by_id(), a, 'a number that is given back is not taken over')

    def test_without_a_web_request_nothing_is_remembered(self):
        with patch.object(send_memo, 'request', None):
            self._send('a')
            self._send('a')
        self.assertEqual(len(self.calls), 2)

    def test_the_state_is_not_in_the_messages_transaction(self):
        """The row both the status job and every message wrote."""
        self.env.flush_all()
        self.session._fields
        with patch.object(self.env.registry['whatsapp.session'], 'write', side_effect=AssertionError('written with the message')):
            with patch.object(self.env.registry, 'cursor', side_effect=Exception('busy')):
                self.session.with_context(wa_own_cursor=True)._save_state({'status': 'connecting'})
        self.assertEqual(self.session.status, 'connecting', 'known here, whoever holds the row')

    def test_counters_are_not_written_with_a_message(self):
        employee = self.env['hr.employee'].create({'name': 'Zz once'})
        es = self.env['wa.employee.session'].create({'employee_id': employee.id, 'session_id': self.session.id, 'phone_number': '+971500000066'})
        self.env.flush_all()
        with patch.object(self.env.registry['wa.employee.session'], '_compute_stats', side_effect=AssertionError('counted with the message')):
            self.env['whatsapp.message'].create({'session_id': self.session.id, 'phone': '919800011122', 'message': 'x',
                                                 'direction': 'incoming', 'status': 'received'})
        self.env['wa.communication.log']._cron_sync_messages()
        self.assertEqual(es.total_messages, 1)
