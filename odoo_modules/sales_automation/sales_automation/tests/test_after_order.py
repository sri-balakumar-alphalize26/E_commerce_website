# -*- coding: utf-8 -*-
"""After a signature or a payment (23 Nov 2026): the customer waits for
nothing the backend can do later; every part goes out once. Nothing is sent."""
from unittest.mock import patch

from odoo import fields
from odoo.tests import HttpCase, tagged

from ..models.sa_after_order import RETRY_MINUTES

SIGNATURE = ('iVBORw0KGgoAAAANSUhEUgAAAAQAAAAECAIAAAAmkwkpAAAAFElEQVR4nGP8//8/AwwwMSAB3BwAlm4DBfIlvvkAAAAASUVORK5CYII=')


@tagged('post_install', '-at_install')
class TestAfterOrder(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env
        cls.log, cls.fail, cls.pdfs = [], [], []
        Request, Session = env.registry['sa.group.request'], env.registry['whatsapp.session']
        Report, Order = env.registry['ir.actions.report'], env.registry['sale.order']

        def say(self, body, addressed=True):
            if 'say' in cls.fail:
                self.env['whatsapp.message'].sudo().create({
                    'session_id': self.group_id.session_id.id, 'phone': 'x', 'message': body,
                    'direction': 'outgoing', 'status': 'pending'})
                return False
            cls.log.append(('say', body))
            return True

        def doc(self, send, note=''):
            if 'doc' in cls.fail:
                raise RuntimeError('gateway down')
            cls.log.append(('doc', note))
            return 'group'

        def render(self, ref, ids, *a, **kw):
            cls.pdfs.append(ref)
            return (b'%PDF-1.4 test', 'pdf')
        for p in (patch.object(Request, '_say', say), patch.object(Request, '_sa_send_doc', doc),
                  patch.object(Request, '_ask', lambda self, body, buttons: cls.log.append(('ask', body)) or True),
                  patch.object(Request, '_sa_flow_end', lambda self: cls.flow),
                  patch.object(Session, '_refresh_state', lambda self, force=False: None),
                  patch.object(Report, '_render_qweb_pdf', render),
                  patch.object(Order, '_send_order_notification_mail',
                               lambda self, tmpl, allow_deferred_sending=True: cls.log.append(('mail', self.name)))):
            p.start()
            cls.addClassCleanup(p.stop)
        cls.flow = 'delivery'
        cls.session = env['whatsapp.session'].sudo().create({
            'name': 'SA after', 'gateway_api_key': 'x', 'instance_name': 'sa-after'})
        cls.session.status = 'connected'
        cls.group = env['sa.sales.group'].create({
            'name': 'Zz After', 'group_jid': '120363000000000009@g.us', 'session_id': cls.session.id,
            'group_type': 'customer'})
        cls.product = env['product.product'].create({
            'name': 'Zz After Speaker', 'list_price': 5.0, 'is_storable': True, 'invoice_policy': 'order'})
        cls.customer = env['res.partner'].create({
            'name': 'Karthick', 'phone': '+919800099922', 'street': '13a, beach road'})
        cls.warehouse = env['stock.warehouse'].search([('company_id', '=', env.company.id)], limit=1)

    def setUp(self):
        super().setUp()
        type(self).flow = 'delivery'
        for box in (self.log, self.fail, self.pdfs):
            box.clear()
        self.session.status = 'connected'

    def _stock(self, qty):
        self.env['stock.quant']._update_available_quantity(self.product, self.warehouse.lot_stock_id, qty)

    def _order(self, qty=3, **vals):
        order = self.env['sale.order'].create({
            'partner_id': self.customer.id, 'require_signature': True, 'require_payment': False,
            'order_line': [(0, 0, {'product_id': self.product.id, 'product_uom_qty': qty, 'price_unit': 5.0,
                                   'tax_ids': [(6, 0, [])]})]})
        order._portal_ensure_token()
        base = {'group_id': self.group.id, 'requester_phone': '919800099922', 'requester_name': 'Karthick',
                'raw_text': 'speaker', 'state': 'order_created', 'order_id': order.id,
                'sa_sign_link_sent_on': fields.Datetime.now()}
        base.update(vals)
        return order, self.env['sa.group.request'].create(base)

    def _task(self, req, step):
        return self.env['sa.after.task'].search([('request_id', '=', req.id), ('step', '=', step)])

    def _sign(self, order):
        order.write({'signed_by': 'Karthick', 'signed_on': fields.Datetime.now(), 'signature': SIGNATURE})
        order.with_context(send_email=True).action_confirm()

    def _kinds(self):
        return [k for k, _v in self.log]

    # ------------------------------------------------------------ stock
    def test_what_the_order_reserved_for_itself_is_in_stock(self):
        self._stock(8)
        other, _r = self._order(5)
        self._sign(other)
        order, req = self._order(3)
        self.assertTrue(req._sa_lines_in_stock(order), 'before: 3 are free')
        self._sign(order)
        self.assertEqual(self.product.with_company(order.company_id).free_qty, 0)
        self.assertTrue(req._sa_lines_in_stock(order))
        self.assertTrue(req.sa_pay_link_sent_on, 'straight to Pay')
        self.assertEqual(self._task(req, 'signed').mode, 'pay')

    def test_one_short_is_arranged(self):
        self._stock(8)
        other, _r = self._order(6)
        self._sign(other)
        order, req = self._order(3)
        self._sign(order)
        self.assertFalse(req._sa_lines_in_stock(order), 'only 2 of 3, the other 6 are not ours')
        self.assertFalse(req.sa_pay_link_sent_on)
        self._task(req, 'signed')._run()
        self.assertTrue([b for k, b in self.log if k == 'say' and 'arranging the goods' in b])

    # ------------------------------------------------------------ sign
    def test_signing_sends_and_prints_nothing_while_they_wait(self):
        self._stock(8)
        order, req = self._order()
        self._sign(order)
        self.assertFalse(self.log or self.pdfs, (self.log, self.pdfs))
        task = self._task(req, 'signed')
        self.assertEqual(task.state, 'todo')
        self.assertTrue(task._run())
        self.assertEqual(self._kinds(), ['doc', 'say', 'mail'])
        self.assertEqual(len(self.pdfs), 1, 'one PDF for the order and for WhatsApp')
        self.assertIn('Signed - thank you', self.log[1][1])
        self.assertTrue(order.message_attachment_count)
        self.assertFalse(task._run())
        self.assertEqual(len(self.log), 3, 'once')

    def test_the_sign_request_opens_on_pay(self):
        self._stock(8)
        order, req = self._order()
        res = self.make_jsonrpc_request('/my/orders/%s/accept' % order.id, {
            'access_token': order.access_token, 'name': 'Karthick', 'signature': SIGNATURE})
        self.env.invalidate_all()
        self.assertTrue(res.get('force_refresh'))
        self.assertIn('payment_amount=15', res['redirect_url'])
        self.assertEqual(order.state, 'sale')
        self.assertTrue(order.signature)
        self.assertFalse(self.log or self.pdfs)
        self.assertEqual(self._task(req, 'signed').state, 'todo')

    def test_signing_again_is_refused_as_before(self):
        self._stock(8)
        order, req = self._order()
        args = {'access_token': order.access_token, 'name': 'Karthick', 'signature': SIGNATURE}
        self.make_jsonrpc_request('/my/orders/%s/accept' % order.id, args)
        self.assertIn('error', self.make_jsonrpc_request('/my/orders/%s/accept' % order.id, args))
        args['access_token'] = 'wrong'
        self.assertIn('error', self.make_jsonrpc_request('/my/orders/%s/accept' % order.id, args))
        self.assertEqual(len(self._task(req, 'signed')), 1)

    def test_an_order_not_from_a_group_is_odoos_own(self):
        order, req = self._order()
        req.order_id = False
        self._stock(8)
        self.make_jsonrpc_request('/my/orders/%s/accept' % order.id, {
            'access_token': order.access_token, 'name': 'Karthick', 'signature': SIGNATURE})
        self.assertTrue(self.pdfs, 'Odoo makes its PDF in the request')
        self.assertFalse(self._task(req, 'signed'))

    # ------------------------------------------------------------ pay
    def _paid(self):
        self._stock(8)
        order, req = self._order()
        self._sign(order)
        self.assertTrue(self._task(req, 'signed')._run())
        self.log.clear()
        self.pdfs.clear()
        req._sa_group_paid(order)
        return order, req

    def test_paying_waits_for_nothing_and_the_task_makes_one_invoice(self):
        order, req = self._paid()
        self.assertFalse(self.log or self.pdfs or order.invoice_ids)
        self.assertTrue(req.sa_paid_on)
        req._sa_group_paid(order)
        task = self._task(req, 'paid')
        self.assertEqual(len(task), 1)
        self.assertTrue(task._run())
        self.assertEqual(len(order.invoice_ids), 1)
        self.assertEqual(order.invoice_ids.state, 'posted')
        self.assertEqual(self._kinds()[:2], ['doc', 'say'])
        self.assertIn('Done! Your order', self.log[1][1])
        self.assertEqual(self._kinds().count('say'), 1)
        self.assertTrue(req.sa_paid_told_on)
        self.assertFalse(task._run())
        self.assertEqual(len(order.invoice_ids), 1)

    def test_a_failed_message_is_retried_without_a_second_invoice_or_pdf(self):
        order, req = self._paid()
        task = self._task(req, 'paid')
        self.fail.append('say')
        self.assertFalse(task._run())
        self.assertEqual((task.state, task.tries), ('todo', 1))
        self.assertFalse(self.env['whatsapp.message'].sudo().search([
            ('session_id', '=', self.session.id), ('status', '=', 'pending')]), 'nothing waits in the outbox')
        self.assertEqual(self._kinds(), ['doc'])
        self.assertFalse(task._run(), 'not before its time')
        self.fail.clear()
        task.next_on = False
        self.assertTrue(task._run())
        self.assertEqual(self._kinds().count('doc'), 1, 'the PDF went out once')
        self.assertEqual(self._kinds().count('say'), 1)
        self.assertEqual(len(order.invoice_ids), 1)

    def test_a_failed_invoice_is_tried_again(self):
        order, req = self._paid()
        task = self._task(req, 'paid')
        Order = self.env.registry['sale.order']
        with patch.object(Order, '_create_invoices', side_effect=RuntimeError('no')):
            self.assertFalse(task._run())
        self.assertFalse(order.invoice_ids or self.log)
        task.next_on = False
        self.assertTrue(task._run())
        self.assertEqual(len(order.invoice_ids), 1)

    def test_not_connected_waits_and_the_invoice_is_made(self):
        order, req = self._paid()
        self.session.status = 'disconnected'
        task = self._task(req, 'paid')
        self.assertFalse(task._run())
        self.assertEqual((task.state, task.tries), ('todo', 0), 'waiting is not a failed try')
        self.session.status = 'connected'
        task.next_on = False
        self.assertTrue(task._run())
        self.assertEqual(len(order.invoice_ids), 1)
        self.assertEqual(self._kinds().count('say'), 1)

    def test_after_the_last_try_a_person_is_told(self):
        order, req = self._paid()
        task = self._task(req, 'paid')
        Order = self.env.registry['sale.order']
        with patch.object(Order, '_create_invoices', side_effect=RuntimeError('no')):
            for _i in range(len(RETRY_MINUTES) + 1):
                task.next_on = False
                task._run()
        self.assertEqual(task.state, 'failed')
        self.assertTrue(order.activity_ids)

    def test_the_sales_order_goes_first_when_they_pay_quickly(self):
        self._stock(8)
        order, req = self._order()
        self._sign(order)
        req._sa_group_paid(order)
        self.assertTrue(self._task(req, 'paid')._run())
        self.assertEqual(self._task(req, 'signed').state, 'done')
        refs = [p for p in self.pdfs]
        self.assertLess(refs.index('sale.action_report_saleorder'), refs.index('account.account_invoices'))
        self.assertFalse([b for k, b in self.log if k == 'say' and 'Signed - thank you' in b], 'paid: no "pay here"')

    def test_the_paid_task_waits_while_the_signed_one_is_not_finished(self):
        self._stock(8)
        order, req = self._order()
        self._sign(order)
        req._sa_group_paid(order)
        self.fail.append('doc')
        self.assertFalse(self._task(req, 'paid')._run())
        self.assertFalse(order.invoice_ids)

    def test_a_flow_that_ends_at_the_order_is_told_by_the_task(self):
        type(self).flow = 'order'
        self._stock(8)
        order, req = self._order()
        self._sign(order)
        self.assertFalse(self.log)
        self._task(req, 'signed')._run()
        self.assertTrue([b for k, b in self.log if k == 'say' and 'is confirmed' in b])
        self.assertFalse(req.sa_pay_link_sent_on)

    # ------------------------------------------------------------ waiting page
    def test_the_waiting_page_is_told_when_to_go_on(self):
        order, req = self._order(99)
        self._sign(order)
        url = '/my/orders/%s/step?access_token=' % order.id
        self.assertEqual(self.url_open(url + order.access_token).json()['step'], 'wait')
        req.sa_pay_link_sent_on = fields.Datetime.now()
        self.env.flush_all()
        self.assertEqual(self.url_open(url + order.access_token).json()['step'], 'go')
        self.assertEqual(self.url_open(url + 'wrong').status_code, 404)

    # ------------------------------------------------------------ 23 Nov, S00018
    def test_a_clash_is_tried_again_at_once_and_not_counted(self):
        from psycopg2 import errors
        from ..models import sa_after_order
        self._stock(8)
        order, req = self._order()
        self._sign(order)
        task = self._task(req, 'signed')
        real, calls = type(req)._sa_after_signed_work, []

        def clash(rec, o, mode):
            calls.append(1)
            if len(calls) < 3:
                raise errors.SerializationFailure('could not serialize access')
            return real(rec, o, mode)
        with patch.object(self.env.registry['sa.group.request'], '_sa_after_signed_work', clash), \
                patch.object(sa_after_order, 'CLASH_SECONDS', (0, 0, 0, 0, 0)), \
                patch.object(self.env.cr, 'rollback', lambda: None), \
                patch.object(self.env.cr, 'commit', lambda: None):
            self.assertTrue(task._run(commit=True))
        self.assertEqual(len(calls), 3)
        self.assertEqual((task.state, task.tries), ('done', 0))
        self.assertEqual(self._kinds(), ['doc', 'say', 'mail'], 'once each')

    def test_clashing_for_ever_waits_like_any_failure(self):
        from psycopg2 import errors
        from ..models import sa_after_order
        self._stock(8)
        order, req = self._order()
        self._sign(order)
        task = self._task(req, 'signed')

        def clash(rec, o, mode):
            raise errors.SerializationFailure('could not serialize access')
        with patch.object(self.env.registry['sa.group.request'], '_sa_after_signed_work', clash), \
                patch.object(sa_after_order, 'CLASH_SECONDS', (0, 0, 0, 0, 0)), \
                patch.object(self.env.cr, 'rollback', lambda: None), \
                patch.object(self.env.cr, 'commit', lambda: None):
            self.assertFalse(task._run(commit=True))
        self.assertEqual((task.state, task.tries), ('todo', 1))
        self.assertTrue(task.next_on)

    def test_the_payment_email_goes_with_the_task(self):
        self._stock(8)
        order, req = self._order()
        self._sign(order)
        self._task(req, 'signed')._run()
        self.log.clear()
        order._send_payment_succeeded_for_order_mail()
        self.assertFalse(self.log, 'not while they wait')
        self.assertTrue(req.sa_pay_mail_on)
        req._sa_group_confirmed(order)
        self.assertFalse([k for k in self._kinds() if k == 'mail'])
        with patch.object(self.env.registry['sa.group.request'], '_sa_paid_invoice', lambda rec, o: None):
            self._task(req, 'paid')._run()
        self.assertEqual(self._kinds().count('mail'), 1)
        self.assertFalse(req.sa_pay_mail_on)

    def test_the_email_of_a_payment_without_a_task_is_not_lost(self):
        self._stock(8)
        order, req = self._order()
        self._sign(order)
        self._task(req, 'signed')._run()
        self.log.clear()
        order._send_payment_succeeded_for_order_mail()
        self.env['sa.after.task'].search([('state', '=', 'todo')]).unlink()
        self.env['sa.after.task']._cron_run()
        self.assertFalse(self.log, 'not yet')
        req.sa_pay_mail_on = fields.Datetime.subtract(fields.Datetime.now(), minutes=31)
        self.env['sa.after.task']._cron_run()
        self.assertEqual(self._kinds(), ['mail'])
        self.env['sa.after.task']._cron_run()
        self.assertEqual(self._kinds(), ['mail'], 'once')

    def test_other_orders_get_their_email_at_once(self):
        order = self.env['sale.order'].create({
            'partner_id': self.customer.id, 'order_line': [(0, 0, {'product_id': self.product.id})]})
        order._send_payment_succeeded_for_order_mail()
        self.assertEqual(self._kinds(), ['mail'])
