# -*- coding: utf-8 -*-
"""A tap on an old poll does nothing (owner, 23 Nov 2026)."""
import itertools
from unittest.mock import patch

from odoo import fields
from odoo.tests import tagged

from .test_only_listed import ListedCase

RAVI = '919800055501'
MEENA = '919800055502'
_SEQ = itertools.count(1)


@tagged('post_install', '-at_install')
class TestPollRule(ListedCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._patch('sa.outbox.guard', 'claim', lambda self, key, seconds=60: True)
        cls.placed, cls.cancelled, cls.answers, cls.core = [], [], [], []

    @classmethod
    def _patch(cls, model, name, value):
        p = patch.object(cls.env.registry[model], name, value)
        p.start()
        cls.addClassCleanup(p.stop)

    def setUp(self):
        super().setUp()
        for box in (self.placed, self.cancelled, self.answers, self.core):
            box.clear()

    # ------------------------------------------------------------ what happens
    def _message(self, text, phone=RAVI, group=None):
        group = group or self.group
        return self.env['whatsapp.message'].sudo().create({
            'session_id': self.session.id, 'phone': group.group_jid, 'message': text, 'direction': 'incoming', 'status': 'received',
            'wa_message_id': 'IN%s' % next(_SEQ), 'group_jid': group.group_jid, 'participant_phone': phone})

    def _tap(self, ref, label, phone=RAVI, **context):
        ctx = dict({'sa_poll_ref': ref, 'sa_is_poll_vote': True}, **context)
        return self.env['sa.group.request'].with_context(**ctx)._on_group_message(self._message(label, phone))

    def _request(self, phone=RAVI, **vals):
        return self._req('zzboard', **dict({'requester_phone': phone, 'product_id': self.product.id, 'state': 'quoted',
                                            'quoted_price': 100.0, 'agreed_price': 100.0, 'qty': 1}, **vals))

    def _poll(self, req, *labels, turn=None):
        """A poll of this enquiry, sent in its own turn. Its WhatsApp id."""
        req = req.with_context(sa_trigger_msg=turn or 'T%s' % next(_SEQ))
        req._ask('zz question %s' % next(_SEQ), [{'id': 'x%s' % i, 'title': label} for i, label in enumerate(labels)])
        req.invalidate_recordset()
        return req.poll_wa_id

    def _recording(self):
        """Which enquiry's answer a tap reached, without acting on it."""
        return patch.object(self.env.registry['sa.group.request'], '_sa_answer_poll',
                            lambda rec, text: self.answers.append((rec.id, text)) or True)

    def _silent(self, before):
        self.assertEqual(len(self.said), before[0], self.said)
        self.assertEqual(len(self.asked), before[1], self.asked)

    def _now(self):
        return len(self.said), len(self.asked)

    # ------------------------------------------------------------ the danger
    def test_an_old_quantity_does_not_place_the_order(self):
        req = self._request(state='awaiting_qty')
        old = self._poll(req, '1', '2', '3')
        new = self._poll(req, 'YES', 'NO')
        req.state = 'awaiting_order_confirm'
        with patch.object(self.env.registry['sa.group.request'], '_place_order', lambda rec: self.placed.append(rec.id) or True):
            before = self._now()
            self._tap(old, '1')
            self.assertEqual((self.placed, req.state, req.qty), ([], 'awaiting_order_confirm', 1.0))
            self._silent(before)
            self._tap(new, 'YES')
            self.assertEqual(self.placed, [req.id], 'the newest one works')

    def test_an_old_cancel_cancels_nothing(self):
        first = self._request()
        old = self._poll(first, 'ACCEPT', 'CANCEL')
        self._poll(first, '1', '2')
        second = self._request(state='quoted')
        self._poll(second, 'ACCEPT', 'CANCEL')
        with patch.object(self.env.registry['sa.group.request'], '_sa_cancel_deal', lambda rec: self.cancelled.append(rec.id) or True):
            before = self._now()
            self._tap(old, 'CANCEL')
        self.assertEqual(self.cancelled, [])
        self._silent(before)

    def test_an_old_accept_accepts_nothing(self):
        req = self._request(state='quoted')
        old = self._poll(req, 'ACCEPT', 'BETTER PRICE', 'CANCEL')
        self._poll(req, 'ACCEPT', 'CANCEL')
        before = self._now()
        self._tap(old, 'ACCEPT')
        self.assertEqual(req.state, 'quoted')
        self._silent(before)

    # ------------------------------------------------------------ what still works
    def test_the_newest_poll_of_each_order(self):
        a, b = self._request(state='awaiting_qty'), self._request(state='quoted')
        old_a = self._poll(a, '1', '2')
        new_a = self._poll(a, '3', '4')
        new_b = self._poll(b, 'ACCEPT', 'CANCEL')      # arrives while A is being answered
        with self._recording():
            self._tap(old_a, '1')
            self._tap(new_a, '3')
            self._tap(new_b, 'ACCEPT')
        self.assertEqual(self.answers, [(a.id, '3'), (b.id, 'ACCEPT')])

    def test_a_tap_twice_on_the_same_poll(self):
        req = self._request(state='awaiting_qty')
        ref = self._poll(req, '1', '2')
        with self._recording():
            self._tap(ref, '1')
            before = self._now()
            self._tap(ref, '2')
        self.assertEqual(self.answers, [(req.id, '1')])
        self._silent(before)

    def test_open_until_it_is_answered(self):
        req = self._request(state='awaiting_qty')
        ref = self._poll(req, '1', '2')
        self.assertFalse(req._sa_poll_is_old(ref))
        req._sa_mark_poll_answered(ref)
        self.assertTrue(req._sa_poll_is_old(ref))

    def test_typing_is_not_touched(self):
        req = self._request(state='awaiting_order_confirm')
        self._poll(req, '1', '2')
        self._poll(req, 'YES', 'NO')
        with patch.object(self.env.registry['sa.group.request'], '_place_order', lambda rec: self.placed.append(rec.id) or True):
            self.env['sa.group.request']._on_group_message(self._message('yes'))
        self.assertEqual(self.placed, [req.id])

    # ------------------------------------------------------------ something new
    def test_a_new_search_closes_the_older_ones(self):
        old = self._request(state='quoted')
        ref = self._poll(old, 'ACCEPT', 'CANCEL')
        other = self._request(phone=MEENA, state='quoted')
        hers = self._poll(other, 'ACCEPT', 'CANCEL')
        self.env['sa.group.request'].with_context(sa_trigger_msg='NEW1').create({
            'group_id': self.group.id, 'requester_phone': RAVI, 'raw_text': 'zz new', 'state': 'new'})
        with self._recording():
            before = self._now()
            self._tap(ref, 'ACCEPT')
            self._silent(before)
            self._tap(hers, 'ACCEPT', phone=MEENA)
        self.assertEqual(self.answers, [(other.id, 'ACCEPT')], "another customer's is not affected")

    def test_two_enquiries_of_one_message_keep_both_polls(self):
        first = self._request(state='quoted')
        ref = self._poll(first, 'ACCEPT', 'CANCEL', turn='SAME')
        second = self.env['sa.group.request'].with_context(sa_trigger_msg='SAME').create({
            'group_id': self.group.id, 'requester_phone': RAVI, 'raw_text': 'zz second', 'state': 'new'})
        ref2 = self._poll(second, 'YES', 'NO', turn='SAME')
        with self._recording():
            self._tap(ref, 'ACCEPT')
            self._tap(ref2, 'YES')
        self.assertEqual(self.answers, [(first.id, 'ACCEPT'), (second.id, 'YES')])

    def test_hi_closes_the_older_ones(self):
        req = self._request(state='quoted')
        ref = self._poll(req, 'ACCEPT', 'CANCEL')
        with patch.object(self.env.registry['sa.group.request'], '_sa_returning_menu', lambda rec, message, group: True):
            self.env['sa.group.request']._on_group_message(self._message('hi'))
        with self._recording():
            before = self._now()
            self._tap(ref, 'ACCEPT')
        self.assertEqual(self.answers, [])
        self._silent(before)

    # ------------------------------------------------------------ over
    def test_a_closed_enquirys_polls(self):
        req = self._request(state='quoted')
        ref = self._poll(req, 'ACCEPT', 'CANCEL')
        req.with_context(sa_trigger_msg='DROP')._drop('stale')
        with self._recording():
            before = self._now()
            self._tap(ref, 'ACCEPT')
        self.assertEqual(self.answers, [])
        self._silent(before)

    def test_the_poll_that_goes_out_with_the_end_stays(self):
        req = self._request(state='quoted')
        ref = self._poll(req, 'ZZ WHAT NEXT', 'ZZ MENU', turn='END')
        req.with_context(sa_trigger_msg='END')._drop('stale')
        with self._recording():
            self._tap(ref, 'ZZ WHAT NEXT')
        self.assertEqual(self.answers, [(req.id, 'ZZ WHAT NEXT')])

    def test_paid(self):
        order = self.env['sale.order'].create({'partner_id': self.env['res.partner'].create({'name': 'Zz poll'}).id})
        req = self._request(state='order_created', order_id=order.id)
        ref = self._poll(req, 'YES', 'NO')
        self.env['sa.poll'].search([('wa_id', '=', ref)]).create_date = fields.Datetime.now()
        self.env.cr.execute("UPDATE sa_poll SET create_date = create_date - interval '1 hour' WHERE wa_id = %s", [ref])
        self.env.invalidate_all()
        req._sa_group_confirmed(order)
        with self._recording():
            self._tap(ref, 'YES')
        self.assertEqual(self.answers, [])

    # ------------------------------------------------------------ ids that are missing
    def test_a_poll_whose_id_was_lost_still_answers(self):
        req = self._request(state='awaiting_qty')
        self._poll(req, '1', '2')
        req.with_context(sa_trigger_msg='LOST')._sa_poll_sent('', ['3', '4'])
        with patch.object(self.env.registry['sa.group.request'], '_active_deal',
                          lambda rec, group, message: self.core.append(message.message) or rec.browse()):
            self._tap('UNKNOWN-1', '3')
            self._tap('UNKNOWN-2', '9')
            self._tap('', '4')
            self._tap('', '9')
        self.assertEqual(self.core, ['3', '4'])

    def test_a_poll_of_nobodys(self):
        before = self._now()
        count = self.env['sa.group.request'].search_count([])
        self._tap('LUNCH', 'Pizza')
        self.assertEqual(self.env['sa.group.request'].search_count([]), count, 'not an enquiry')
        self._silent(before)

    def test_polls_sent_before_this_rule(self):
        req = self._request(state='awaiting_qty', poll_wa_id='OLD2', poll_wa_ids='OLD2,OLD1')
        with self._recording():
            before = self._now()
            self._tap('OLD1', '1')
            self._silent(before)
            self._tap('OLD2', '2')
        self.assertEqual(self.answers, [(req.id, '2')])

    # ------------------------------------------------------------ other people
    def test_a_bystander(self):
        req = self._request(state='quoted')
        old = self._poll(req, 'ACCEPT', 'CANCEL')
        new = self._poll(req, 'ACCEPT', 'CANCEL')
        told = []
        with patch.object(self.env.registry['sa.group.request'], '_sa_tell_bystander', lambda rec, message: told.append(rec.id)):
            self._tap(old, 'ACCEPT', phone=MEENA)
            self.assertEqual(told, [], 'an old one: nothing')
            self._tap(new, 'ACCEPT', phone=MEENA)
        self.assertEqual(told, [req.id], 'the newest one: as before')

    def test_a_vendor_group(self):
        self.group.sudo().write({'group_type': 'vendor'})
        with patch.object(self.env.registry['sa.vendor.quote'], '_capture', lambda rec, message, group: self.core.append('vendor') or True):
            self._tap('ANY', 'YES')
        self.assertEqual(self.core, ['vendor'])

    # ------------------------------------------------------------ private chat
    def test_old_by_its_id(self):
        req = self._request(state='finding')
        old = self._poll(req, 'Dell', 'HP')
        new = self._poll(req, '15', '16')
        Request = self.env['sa.group.request']
        self.assertTrue(Request._sa_poll_is_old(old))
        self.assertFalse(Request._sa_poll_is_old(new))
        self.assertFalse(Request._sa_poll_is_old('A-TRACKER-POLL'))
        self.assertFalse(Request._sa_poll_is_old(''))

    def test_a_failed_send_closes_the_older_poll_only(self):
        req = self._request(state='awaiting_qty')
        ref = self._poll(req, '1', '2')
        with patch.object(self.env.registry['whatsapp.session'], 'sa_send_poll', side_effect=RuntimeError('zz')):
            req.with_context(sa_trigger_msg='TEXT')._ask('zz text', [{'id': 'a', 'title': 'YES'}])
        self.assertTrue(self.env['sa.group.request']._sa_poll_is_old(ref), 'a newer question went out as text')
        self.assertFalse(self.env['sa.poll'].search([('request_id', '=', req.id), ('closed', '=', False)]))
