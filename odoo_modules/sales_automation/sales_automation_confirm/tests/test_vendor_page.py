# -*- coding: utf-8 -*-
"""Used links show only the result; the vendor's price on the page; reminders;
a week (23 Nov 2026). WhatsApp and WeChat alike. Nothing is sent."""
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.tests import HttpCase, tagged

INDIA = '919812345688'


class VendorCase(HttpCase):

    def setUp(self):
        super().setUp()
        env = self.env
        self.sent, self.down = [], []
        Session, Req = env.registry['whatsapp.session'], env.registry['sa.group.request']
        box = self

        def send(rec, phone, message):
            if box.down:
                raise RuntimeError('gateway down')
            box.sent.append((phone, message))
            return True
        for p in (patch.object(Session, '_refresh_state', lambda rec, force=False: None),
                  patch.object(Session, 'send_message', send),
                  patch.object(Req, '_say', lambda rec, body, addressed=True: box.sent.append(('group', body)) or True),
                  patch.object(env.registry['sa.sales.group'], '_sa_fetch_invite_url', lambda rec: '')):
            p.start()
            self.addCleanup(p.stop)
        self.settings = env['sa.ai.settings'].sudo().get_settings()
        self.settings.write({'vendor_remind_minutes': 5, 'vendor_remind_max': 2, 'confirm_vendor_enabled': True,
                             'vendor_money': 'country',
                             'sourcing_window_minutes': 10, 'wechat_enabled': True,
                             'wechat_last_seen': fields.Datetime.now()})
        self.session = env['whatsapp.session'].sudo().create({
            'name': 'Vendor page', 'gateway_api_key': 'vendor-page', 'phone_number': '919811122299'})
        self.session.status = 'connected'
        self.group = env['sa.sales.group'].sudo().create({
            'name': 'Vendor Page Group', 'group_jid': 'vendor-page@g.us', 'session_id': self.session.id,
            'group_type': 'customer'})
        self.inr = env['res.currency'].with_context(active_test=False).search([('name', '=', 'INR')])
        self.inr.active = True
        self.vendor = env['res.partner'].create({
            'name': 'Zz Page Vendor', 'phone': '+' + INDIA, 'country_id': env.ref('base.in').id,
            'sa_via_whatsapp': True})
        self.product = env['product.template'].sudo().create({'name': 'Zz Page Jack', 'type': 'consu'})
        self.req = self._request()
        self.link = self._link(self.req, self.vendor)

    def _request(self, **vals):
        return self.env['sa.group.request'].sudo().create(dict({
            'group_id': self.group.id, 'requester_phone': '+96890000088', 'raw_text': 'jack',
            'product_id': self.product.id, 'state': 'sourcing', 'currency_id': self.inr.id,
            'sourcing_deadline': fields.Datetime.now() + timedelta(minutes=1),
            'sourcing_vendor_ids': [(6, 0, self.vendor.ids)]}, **vals))

    def _link(self, req, vendor, channel='whatsapp', **vals):
        return self.env['sa.confirm.link'].sudo().create(dict({
            'request_id': req.id, 'kind': 'vendor', 'channel': channel, 'partner_id': vendor.id,
            'phone': INDIA if channel == 'whatsapp' else False,
            'wechat_name': vendor.sa_wechat_name if channel == 'wechat' else False,
            'sent_on': fields.Datetime.now()}, **vals))

    def _customer(self, **vals):
        req = self._request(state='awaiting_confirm')
        return self.env['sa.confirm.link'].sudo().create(dict({
            'request_id': req.id, 'kind': 'customer', 'sent_on': fields.Datetime.now()}, **vals))

    def _html(self, link=None, query=''):
        return self.url_open('/wa/confirm/%s%s' % ((link or self.link).token, query)).text

    def _press(self, what, link=None):
        res = self.url_open('/wa/confirm/%s/%s' % ((link or self.link).token, what), data={'x': '1'})
        self.env.invalidate_all()
        return res

    def _price(self, amount, link=None):
        res = self.url_open('/wa/confirm/%s/price' % (link or self.link).token, data={'amount': amount},
                            headers={'X-Requested-With': 'fetch'})
        self.env.invalidate_all()
        return res

    def _ago(self, **kw):
        return fields.Datetime.now() - timedelta(**kw)


@tagged('post_install', '-at_install')
class TestUsedLink(VendorCase):

    def test_customer_sees_the_result_only(self):
        link = self._customer()
        self.assertIn('/accept', self._html(link))
        self._press('accept', link)
        html = self._html(link)
        self.assertIn('You accepted this product', html)
        self.assertIn('Zz Page Jack', html)
        for gone in ('class="picbox"', 'class="dt"', '/accept"', '/reject"', '/price"', 'id="amount"'):
            self.assertNotIn(gone, html)

    def test_rejected_shows_rejected(self):
        link = self._customer()
        self._press('reject', link)
        html = self._html(link)
        self.assertIn('You rejected this product', html)
        self.assertNotIn('/accept"', html)

    def test_accept_answers_first_and_works_after(self):
        link = self._customer()
        self.sent.clear()
        Req = self.env.registry['sa.group.request']
        with patch.object(Req, '_on_confirmed', lambda rec: self.sent.append(('work', rec.id)) or True):
            self._press('accept', link)
            self.assertFalse(self.sent, 'the page waits for nothing')
            self.assertTrue(link.request_id.sa_confirm_accepted_on)
            task = self.env['sa.after.task'].search([('request_id', '=', link.request_id.id)])
            self.assertEqual((task.step, task.mode, task.ref, task.state), ('accepted', 'accept', link.id, 'todo'))
            self.assertTrue(task._run())
            self.assertEqual([k for k, _v in self.sent], ['group', 'work'])
            self.assertFalse(task._run())
            self.assertEqual(len(self.sent), 2, 'once')

    def test_not_connected_waits(self):
        link = self._customer()
        self._press('accept', link)
        self.session.status = 'disconnected'
        self.sent.clear()
        task = self.env['sa.after.task'].search([('request_id', '=', link.request_id.id)])
        self.assertFalse(task._run())
        self.assertEqual((task.state, task.tries), ('todo', 0))
        self.assertFalse(self.sent)

    def test_a_second_link_of_the_same_enquiry_has_its_own_task(self):
        link = self._customer()
        self._press('reject', link)
        task = self.env['sa.after.task'].search([('request_id', '=', link.request_id.id)])
        task.write({'state': 'done'})
        other = self.env['sa.confirm.link'].sudo().create({
            'request_id': link.request_id.id, 'kind': 'customer', 'phone': '1', 'sent_on': fields.Datetime.now()})
        self._press('accept', other)
        self.assertEqual(self.env['sa.after.task'].search_count([('request_id', '=', link.request_id.id)]), 2)

    def test_expiry(self):
        link = self._customer(sent_on=self._ago(days=7, minutes=-1))
        self.assertNotIn('expired', self._html(link))
        link.sent_on = self._ago(days=7, minutes=1)
        self.assertIn('This link has expired', self._html(link))
        self._press('accept', link)
        self.assertFalse(link.decided)
        # used: the result for a week after the answer
        link.write({'decided': 'accept', 'decided_on': self._ago(days=6)})
        self.assertIn('You accepted', self._html(link))
        link.decided_on = self._ago(days=8)
        self.assertIn('This link has expired', self._html(link))

    def test_clean_up_keeps_the_proof(self):
        self.link.write({'decided': 'accept', 'decided_on': self._ago(days=8), 'decided_ua': 'phone',
                         'price_on': self._ago(days=8), 'price_amount': 100, 'price_currency': 'INR'})
        self.link._record_click('open')
        self.env.cr.execute("UPDATE sa_confirm_link SET create_date = %s WHERE id = %s", (self._ago(days=9), self.link.id))
        self.env.invalidate_all()
        young = self._link(self._request(), self.vendor, decided='accept', decided_on=fields.Datetime.now())
        young._record_click('open')
        self.env['sa.confirm.link']._cron_links_clean()
        self.assertFalse(self.link.click_ids)
        self.assertFalse(self.link.decided_ua)
        self.assertIn('accepted', self.link.proof)
        self.assertIn('INR 100.00', self.link.proof)
        self.assertTrue(young.click_ids)
        self.assertFalse(young.proof)


@tagged('post_install', '-at_install')
class TestVendorPage(VendorCase):

    def test_the_form_only_after_accept(self):
        self.assertNotIn('id="amount"', self._html())
        self.assertFalse(self._price('100').json()['ok'])
        self.assertFalse(self.req.quote_ids)
        self._press('accept')
        html = self._html()
        self.assertIn('what is your best price for <b>Zz Page Jack</b>', html)
        self.assertIn('TYPE YOUR AMOUNT IN INR', html)
        self.assertFalse(self.sent, 'nothing is asked in the chat')
        self.assertIn(self.vendor, self.req.sa_vendor_yes_ids)

    def test_the_order_companys_currency(self):
        self.settings.vendor_money = 'company'
        cur = self.group and self.req._company_for(self.group).currency_id
        self.req.currency_id = cur
        self._press('accept')
        html = self._html()
        self.assertIn('TYPE YOUR AMOUNT IN %s' % cur.name, html)
        self.assertNotIn('INR', html)
        self.assertTrue(self._price('12.5').json()['ok'])
        self.assertEqual((self.req.quote_ids.price, self.req.quote_ids.currency_id, self.req.quote_ids.sa_typed_currency),
                         (12.5, cur, cur.name))

    def test_accept_leaves_the_window_as_it_is(self):
        before = self.req.sourcing_deadline
        self._press('accept')
        self.assertEqual(self.req.sourcing_deadline, before, 'the window is what the setting says (23 Nov 2026)')

    def test_one_price(self):
        self._press('accept')
        self.assertTrue(self._price('1,450.50').json()['ok'])
        quote = self.req.quote_ids
        self.assertEqual((len(quote), quote.price, quote.sa_typed_currency, quote.partner_id), (1, 1450.5, 'INR', self.vendor))
        self._price('999')
        self.assertEqual(len(self.req.quote_ids), 1)
        self.assertEqual(self.req.quote_ids.price, 1450.5)
        html = self._html()
        self.assertIn('INR 1450.50', html)
        self.assertNotIn('id="amount"', html)

    def test_not_a_number(self):
        self._press('accept')
        for bad in ('', 'abc', '0', '-5', '1e9', '12 days', '99999999999'):
            self.assertFalse(self._price(bad).json()['ok'], bad)
        self.assertFalse(self.req.quote_ids)

    def test_a_customer_link_takes_no_price(self):
        link = self._customer()
        self._press('accept', link)
        self.assertEqual(self._price('100', link).status_code, 404)
        self.assertFalse(link.request_id.quote_ids)

    def test_rejected_is_final(self):
        self._press('reject')
        self.assertFalse(self._price('100').json()['ok'])
        self.assertIn('You rejected this product', self._html())

    def test_a_price_typed_in_the_chat_closes_the_form(self):
        self._press('accept')
        self.env['sa.vendor.quote'].sudo()._sa_take_price(self.req, 70.0, 'INR', {
            'partner_id': self.vendor.id, 'vendor_phone': INDIA, 'vendor_name': 'V', 'matched_by': 'direct'})
        self.assertIn('INR 70.00', self._html())

    def test_closed_when_the_customer_cancelled(self):
        self._press('accept')
        self.req.state = 'cancelled' if 'cancelled' in dict(self.req._fields['state'].selection) else 'dropped'
        self.assertIn('already closed', self._html())
        self.assertFalse(self._price('100').json()['ok'])

    def test_late_but_still_wanted(self):
        self._press('accept')
        self.req.write({'sa_price_stalled': True, 'sourcing_deadline': False})
        self.assertTrue(self._price('80').json()['ok'])
        self.assertTrue(self.req.sourcing_deadline, 'closes on it at the next run')

    def test_no_rate_is_held_and_still_answered(self):
        omr = self.env['res.currency'].with_context(active_test=False).search([('name', '=', 'OMR')])
        omr.active = True
        self.env['res.currency.rate'].search([('currency_id', 'in', (omr | self.inr).ids)]).unlink()
        self.req.currency_id = omr
        self._press('accept')
        self.assertTrue(self._price('100').json()['ok'])
        self.assertFalse(self.req.quote_ids)
        self.assertEqual(self.req._sa_held_of(self.vendor.id)['code'], 'INR')
        self.assertIn('INR 100.00', self._html())

    def test_expired(self):
        self._press('accept')
        self.link.write({'decided_on': self._ago(days=8)})
        self.assertEqual(self._price('100').status_code, 410)
        self.assertFalse(self.req.quote_ids)

    def test_a_repeated_request_makes_the_link_again(self):
        token = self.link.token
        self.link.unlink()
        self.req._sa_vendor_asked_before(self.vendor)
        again = self.env['sa.confirm.link'].sudo().search([('request_id', '=', self.req.id), ('kind', '=', 'vendor')])
        self.assertEqual(again.token, token)


@tagged('post_install', '-at_install')
class TestVendorRemind(VendorCase):

    def _run(self):
        self.sent.clear()
        self.env['sa.confirm.link']._cron_vendor_remind()
        return [m for _p, m in self.sent]

    def test_no_answer_after_five_and_ten_minutes(self):
        self.link.sent_on = self._ago(minutes=4)
        self.assertFalse(self._run())
        self.link.sent_on = self._ago(minutes=5)
        first = self._run()
        self.assertEqual(len(first), 1)
        self.assertIn('Reminder 1 of 2', first[0])
        self.assertIn('ACCEPT or REJECT', first[0])
        self.assertIn(self.link.token, first[0])
        self.assertFalse(self._run(), 'not again at once')
        self.link.write({'sent_on': self._ago(minutes=10), 'vendor_reminded_on': self._ago(minutes=5)})
        self.assertIn('Reminder 2 of 2', self._run()[0])
        self.link.write({'sent_on': self._ago(minutes=20), 'vendor_reminded_on': self._ago(minutes=10)})
        self.assertFalse(self._run(), 'two at most')

    def test_accepted_without_a_price_counts_for_itself(self):
        self.link.write({'sent_on': self._ago(minutes=30), 'remind_ask_count': 2, 'decided': 'accept',
                         'decided_on': self._ago(minutes=5)})
        first = self._run()
        self.assertEqual(len(first), 1)
        self.assertIn('type your price', first[0])
        self.assertIn('INR', first[0])
        self.assertEqual((self.link.remind_price_count, self.link.remind_ask_count), (1, 2))

    def test_goes_on_after_the_desk_alarm(self):
        self.link.sent_on = self._ago(minutes=6)
        self.req.write({'sa_price_stalled': True, 'sourcing_deadline': False})
        self.assertEqual(len(self._run()), 1)

    def test_stops(self):
        self.link.sent_on = self._ago(minutes=6)
        for vals in ({'sa_vendor_no_ids': [(4, self.vendor.id)]}, {'state': 'dropped'}, {'state': 'quoted'}):
            before = {k: (self.req[k] if k == 'state' else [(3, self.vendor.id)]) for k in vals}
            self.req.write(vals)
            self.assertFalse(self._run(), vals)
            self.req.write(before)
        self.link.decided = 'reject'
        self.assertFalse(self._run())
        self.link.write({'decided': 'accept', 'decided_on': self._ago(minutes=6)})
        self.env['sa.vendor.quote'].sudo().create({
            'request_id': self.req.id, 'price': 5, 'partner_id': self.vendor.id, 'matched_by': 'manual'})
        self.env.invalidate_all()
        self.assertFalse(self._run(), 'the shop typed a price')

    def test_a_held_price_is_an_answer(self):
        self.link.write({'decided': 'accept', 'decided_on': self._ago(minutes=6)})
        self.req._sa_hold_price(self.vendor.id, INDIA, 'V', 100, 'USD')
        self.assertFalse(self._run())

    def test_off_or_not_connected(self):
        self.link.sent_on = self._ago(minutes=6)
        self.settings.vendor_remind_minutes = 0
        self.assertFalse(self._run())
        self.settings.write({'vendor_remind_minutes': 5, 'vendor_remind_max': 0})
        self.assertFalse(self._run())
        self.settings.vendor_remind_max = 2
        self.session.status = 'disconnected'
        self.assertFalse(self._run())
        self.session.status = 'connected'
        self.down.append(1)
        self.assertFalse(self._run())
        self.assertFalse(self.link.remind_ask_count, 'not counted, not queued')
        self.down.clear()
        self.assertEqual(len(self._run()), 1)

    def test_one_at_a_time_oldest_first(self):
        self.link.sent_on = self._ago(minutes=7)
        other = self._link(self._request(), self.vendor, sent_on=self._ago(minutes=7))
        self.assertIn(self.link.token, self._run()[0])
        self.assertFalse(self._run())
        self.link.write({'remind_ask_count': 2, 'vendor_reminded_on': self._ago(minutes=5)})
        self.assertIn(other.token, self._run()[0])

    def test_old_ones_are_left_alone(self):
        self.link.sent_on = self._ago(hours=5)
        self.assertFalse(self._run())

    def test_yes_in_the_chat_is_reminded_of_the_price(self):
        self.link.sent_on = self._ago(minutes=30)
        self.req.write({'sa_vendor_yes_ids': [(4, self.vendor.id)]})
        with patch.object(self.env.registry['sa.outbox.guard'], 'claim', lambda rec, key, seconds=60: True):
            self.req._sa_ask_vendor_price(self.session, INDIA)
        self.assertTrue(self.link.chat_yes_on)
        self.assertFalse(self._run())
        self.link.chat_yes_on = self._ago(minutes=6)
        self.assertIn('type your price', self._run()[0])


@tagged('post_install', '-at_install')
class TestVendorWeChat(VendorCase):

    def setUp(self):
        super().setUp()
        self.vendor.write({'sa_via_wechat': True, 'sa_wechat_name': 'zz-page-remark'})
        self.wx = self._link(self.req, self.vendor, channel='wechat')
        self.Msg = self.env['sa.wechat.message'].sudo()
        self.ask = self.Msg.create({
            'direction': 'out', 'state': 'sent', 'sent_on': fields.Datetime.now(), 'partner_id': self.vendor.id,
            'wechat_name': 'zz-page-remark', 'text': 'ask', 'request_id': self.req.id, 'wx_step': 'ask',
            'wx_confirm_link_id': self.wx.id})

    def _out(self):
        return self.Msg.search([('direction', '=', 'out'), ('request_id', '=', self.req.id), ('id', '!=', self.ask.id)])

    def test_price_on_the_page(self):
        self._press('accept', self.wx)
        self.assertFalse(self._out(), 'nothing more is asked in the chat')
        self.assertIn('TYPE YOUR AMOUNT IN INR', self._html(self.wx))
        self.assertTrue(self._price('45', self.wx).json()['ok'])
        self.assertEqual((self.req.quote_ids.price, self.req.quote_ids.matched_by), (45.0, 'wechat'))
        self.assertFalse(self._out())

    def test_asked_on_both_answers_once(self):
        self._press('accept', self.wx)
        self.assertIn('id="amount"', self._html(self.link), 'the WhatsApp page asks the price too')
        self._price('45', self.wx)
        self.assertIn('INR 45.00', self._html(self.link))
        self._price('99', self.link)
        self.assertEqual(self.req.quote_ids.mapped('price'), [45.0])
        self.sent.clear()
        self.link.sent_on = self._ago(minutes=6)
        self.env['sa.confirm.link']._cron_vendor_remind()
        self.assertFalse(self.sent or self._out())

    def test_rejected_on_one_is_rejected_on_both(self):
        self._press('reject', self.wx)
        self.assertIn('You rejected this product', self._html(self.link))
        self._press('accept', self.link)
        self.assertFalse(self.link.decided)

    def test_a_number_typed_after_accept_is_the_price(self):
        self._press('accept', self.wx)
        res = self.Msg._sa_ingest('zz-page-remark', '7', wx_id='zz-page-1')
        self.assertEqual(res['result'], 'quoted')
        self.assertEqual(self.req.quote_ids.price, 7.0)

    def test_yuan_is_not_the_enquirys_money(self):
        res = self.Msg._sa_ingest('zz-page-remark', '45\u5143', wx_id='zz-page-2')
        self.assertEqual(res['result'], 'quoted')
        self.assertFalse(self.req.quote_ids, 'CNY has no rate here: held')
        self.assertEqual(self.req._sa_held_of(self.vendor.id)['code'], 'CNY')

    def test_a_wechat_only_vendor_prices_in_cny(self):
        only = self.env['res.partner'].create({
            'name': 'Zz WX only', 'sa_via_wechat': True, 'sa_via_whatsapp': False, 'sa_wechat_name': 'zz-only'})
        only.country_id = False
        self.assertEqual(self.req._sa_vendor_currency(False, only), 'CNY')

    def test_reminded_through_the_bridge(self):
        self.link.write({'remind_ask_count': 2, 'sent_on': self._ago(hours=5)})
        cron = self.env['sa.confirm.link']._cron_vendor_remind
        self.ask.sent_on = self._ago(minutes=6)
        self.settings.wechat_last_seen = self._ago(minutes=30)
        cron()
        self.assertFalse(self._out(), 'bridge down: nothing queued')
        self.settings.wechat_last_seen = fields.Datetime.now()
        self.ask.state = 'queued'
        cron()
        self.assertFalse(self._out(), 'the price check itself has not gone out')
        self.ask.state = 'sent'
        cron()
        self.assertEqual(len(self._out()), 1)
        self.assertIn(self.wx.token, self._out().text)
        self.assertEqual(self._out().wx_step, 'ask')
        cron()
        self.assertEqual(len(self._out()), 1)
        self.wx.write({'decided': 'accept', 'decided_on': self._ago(minutes=6), 'vendor_reminded_on': self._ago(minutes=6)})
        cron()
        self.assertEqual(self._out()[0].wx_step, 'price')

    def test_a_repeated_request_asks_again_only_when_undone(self):
        guard = self.env['sa.outbox.guard'].sudo()
        self.req._sa_ask_via_wechat(self.vendor, 'x', guard, 't')
        self.assertFalse(self._out(), 'asked a moment ago')
        self.ask.unlink()
        self.req._sa_ask_via_wechat(self.vendor, 'x', guard, 't')
        self.assertEqual(self.Msg.search_count([('direction', '=', 'out'), ('request_id', '=', self.req.id)]), 1)
