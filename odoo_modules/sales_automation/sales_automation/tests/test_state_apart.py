# -*- coding: utf-8 -*-
"""A send does not collide with the saving of its own state (Ref 1GG, 24 Nov
2026). Real connections: the first try of the tests could not see it."""
from datetime import timedelta
from unittest.mock import patch

from odoo import api, fields
from odoo.addons.whatsapp_gateway.models import whatsapp_session as ws
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestStateApart(TransactionCase):

    def setUp(self):
        super().setUp()
        with self.registry.cursor() as cr:
            session = api.Environment(cr, self.uid, {})['whatsapp.session'].create({
                'name': 'Zz apart', 'gateway_api_key': 'zz-apart', 'gateway_url': 'http://127.0.0.1:9', 'instance_name': 'zz-apart',
                'status': 'disconnected', 'state_checked': fields.Datetime.now() - timedelta(hours=1)})
            self.sid = session.id
        self.addCleanup(self._clean)
        self.posted, self.asked, self.state = [], [], 'open'
        ws._STATE_MEMO.clear()
        self.addCleanup(ws._STATE_MEMO.clear)
        box = self

        def call(rec, method, path, payload=None, **kw):
            if method == 'GET':
                box.asked.append(path)
                return {'instance': {'state': box.state}}
            box.posted.append(payload)
            return {'key': {'id': 'ZZAPART%s' % len(box.posted)}}
        p = patch.object(self.registry['whatsapp.session'], '_gateway_call', call)
        p.start()
        self.addCleanup(p.stop)

    def _clean(self):
        with self.registry.cursor() as cr:
            cr.execute('DELETE FROM whatsapp_message WHERE session_id = %s', [self.sid])
            cr.execute('DELETE FROM whatsapp_session WHERE id = %s', [self.sid])

    def _session(self, cr):
        return api.Environment(cr, self.uid, {'wa_own_cursor': True})['whatsapp.session'].browse(self.sid)

    def _row(self):
        with self.registry.cursor() as cr:
            cr.execute('SELECT status, state_checked FROM whatsapp_session WHERE id = %s', [self.sid])
            return cr.fetchone()

    def _messages(self):
        with self.registry.cursor() as cr:
            cr.execute('SELECT count(*) FROM whatsapp_message WHERE session_id = %s', [self.sid])
            return cr.fetchone()[0]

    def test_send_and_go_on(self):
        with self.registry.cursor() as cr:
            session = self._session(cr)
            cr.execute('SELECT 1')                       # the picture of the database is taken here
            session.send_message('919800000001', 'hello')
            cr.execute('SELECT 1')
            self.assertEqual(self._row()[0], 'disconnected', 'not while the transaction runs')
            self.assertEqual(session.status, 'connected')
        self.assertEqual((self._row()[0], self._messages(), len(self.posted)), ('connected', 1, 1))

    def test_saved_after_a_rollback_too(self):
        with self.registry.cursor() as cr:
            self._session(cr)._refresh_state()
            cr.rollback()
        self.assertEqual(self._row()[0], 'connected')

    def test_somebody_else_wrote_the_number_meanwhile(self):
        with self.registry.cursor() as cr:
            session = self._session(cr)
            session._refresh_state()
            session.name
            with self.registry.cursor() as other:
                other.execute("UPDATE whatsapp_session SET status = 'connected', state_checked = now() at time zone 'utc' WHERE id = %s", [self.sid])
            session.send_message('919800000002', 'hello')
            cr.execute('SELECT 1')                       # the transaction is still good
        self.assertEqual((self._messages(), len(self.posted)), (1, 1))

    def test_asked_once_a_minute_and_written_when_it_changes(self):
        for _n in range(3):
            with self.registry.cursor() as cr:
                self._session(cr)._refresh_state()
        self.assertEqual(len(self.asked), 1)
        checked = self._row()[1]
        with self.registry.cursor() as cr:
            self._session(cr)._refresh_state(force=True)
        self.assertEqual((len(self.asked), self._row()[1]), (2, checked), 'the same state is not written again')
        self.state = 'close'
        with self.registry.cursor() as cr:
            self._session(cr)._refresh_state(force=True)
        self.assertEqual(self._row()[0], 'disconnected')

    def test_a_write_beats_what_was_remembered(self):
        with self.registry.cursor() as cr:
            self._session(cr)._refresh_state()
        with self.registry.cursor() as cr:
            self._session(cr).write({'status': 'disconnected', 'state_checked': fields.Datetime.now() - timedelta(hours=1)})
        with self.registry.cursor() as cr:
            self._session(cr)._refresh_state()
        self.assertEqual(len(self.asked), 2)
