"""The staff side of notifications, and the kind that could never arrive.

A notice goes into every customer's notification list, so what is worth pinning
here is what decides whether it gets there at all.

**The bug this file exists for.** `TYPE_CHOICES` offers three kinds, and the
delivery query only ever allowed two: a notice saved as `order` was filtered
out for every customer, silently, while the screen went on offering the kind.

**Windowing was never tested.** `publish_at` and `until` decide whether a live
notice is live, and until now nothing asserted either, nor that a retired one
stays gone.

**Retired, not deleted.** Somebody has already read it; deleting the record
does not untell them. So there is no delete route, and that is asserted.
"""

import json
from datetime import timedelta

from odoo import fields
from odoo.tests import tagged

from .common import Mart369AccountCase, Mart369AccountHttpCase

HEADERS = {'Content-Type': 'application/json'}
LIST = '/369mart/admin/notices'


@tagged('post_install', '-at_install')
class TestNoticeDelivery(Mart369AccountCase):
    """Whether a notice reaches a customer at all."""

    def setUp(self):
        super().setUp()
        self.Notice = self.env['mart369.notice']
        self.feed = self.env['mart369.notifications']

    def _notice(self, **over):
        values = {'name': 'Something', 'text': 'Some words', 'kind': 'offer'}
        values.update(over)
        return self.Notice.create(values)

    def _titles(self):
        rows = self.feed._mart369_for(self.partner)['notifications']
        return [r['title'] for r in rows]

    def test_an_order_notice_reaches_the_customer(self):
        """The bug. `order` was in the choices and in no delivery list, so a
        notice saved as one went nowhere and said nothing about it."""
        self._notice(name='Deliveries paused today', kind='order')
        self.assertIn('Deliveries paused today', self._titles())

    def test_an_order_notice_arrives_even_with_offers_switched_off(self):
        """It is operational, not marketing - the order notes beside it are
        already shown to everybody."""
        self.partner._mart369_write_prefs({'offers': False, 'wallet': False})
        self._notice(name='Deliveries paused today', kind='order')
        self.assertIn('Deliveries paused today', self._titles())

    def test_the_two_marketing_kinds_still_obey_the_switch(self):
        self.partner._mart369_write_prefs({'offers': False})
        self._notice(name='Weekend sale', kind='offer')
        self.assertNotIn('Weekend sale', self._titles())

    # -------------------------------------------------------- the window

    def test_a_notice_that_has_not_started_is_not_shown(self):
        self._notice(name='Starts tomorrow',
                     publish_at=fields.Datetime.now() + timedelta(days=1))
        self.assertNotIn('Starts tomorrow', self._titles())

    def test_a_notice_that_has_finished_is_not_shown(self):
        self._notice(name='Ended yesterday',
                     publish_at=fields.Datetime.now() - timedelta(days=2),
                     until=fields.Datetime.now() - timedelta(days=1))
        self.assertNotIn('Ended yesterday', self._titles())

    def test_a_retired_notice_stays_gone(self):
        notice = self._notice(name='Taken down')
        self.assertIn('Taken down', self._titles())
        self.Notice.mart369_admin_retire(notice.id)
        self.assertNotIn('Taken down', self._titles())


@tagged('post_install', '-at_install')
class TestNoticeAdminModel(Mart369AccountCase):

    def setUp(self):
        super().setUp()
        self.Notice = self.env['mart369.notice']

    def test_the_state_is_worked_out_from_the_dates(self):
        """There is no status column, and there should not be one: live,
        scheduled and expired all fall out of the two dates and `active`."""
        now = fields.Datetime.now()
        live = self.Notice.create({'name': 'A', 'text': 'x'})
        later = self.Notice.create({'name': 'B', 'text': 'x',
                                    'publish_at': now + timedelta(days=1)})
        done = self.Notice.create({'name': 'C', 'text': 'x',
                                   'publish_at': now - timedelta(days=2),
                                   'until': now - timedelta(days=1)})
        off = self.Notice.create({'name': 'D', 'text': 'x', 'active': False})

        self.assertEqual(live._mart369_state(), 'live')
        self.assertEqual(later._mart369_state(), 'scheduled')
        self.assertEqual(done._mart369_state(), 'expired')
        self.assertEqual(off._mart369_state(), 'off')

    def test_each_tab_asks_for_what_it_says(self):
        now = fields.Datetime.now()
        later = self.Notice.create({'name': 'Scheduled one', 'text': 'x',
                                    'publish_at': now + timedelta(days=1)})
        ids = lambda **kw: [n['id'] for n
                            in self.Notice.mart369_admin_list(**kw)['notices']]
        self.assertIn(later.id, ids(tab='scheduled'))
        self.assertNotIn(later.id, ids(tab='live'))
        self.assertIn(later.id, ids(tab='all'))

    def test_the_tiles_count_everything_not_the_filtered_rows(self):
        self.Notice.create({'name': 'Findable one', 'text': 'x'})
        wide = self.Notice.mart369_admin_list(tab='all')
        narrow = self.Notice.mart369_admin_list(tab='all', q='Findable')
        self.assertEqual(wide['counts'], narrow['counts'])
        self.assertLess(len(narrow['notices']), len(wide['notices']))

    # ------------------------------------------------------------ writing

    def test_writing_one_and_changing_it(self):
        row = self.Notice.mart369_admin_save(values={
            'name': 'Fresh picks', 'text': 'Up to 40% off.', 'kind': 'offer'})
        self.assertEqual(row['state'], 'live')

        again = self.Notice.mart369_admin_save(row['id'], {'title': 'ignored',
                                                           'text': 'Changed.'})
        self.assertEqual(again['text'], 'Changed.')
        self.assertEqual(again['title'], 'Fresh picks',
                         'a key outside the allow-list changes nothing')

    def test_a_notice_without_words_is_refused(self):
        with self.assertRaises(Exception):
            self.Notice.mart369_admin_save(values={'name': 'Title only', 'text': '  '})

    def test_a_window_that_ends_before_it_starts_is_refused(self):
        now = fields.Datetime.now()
        with self.assertRaises(Exception):
            self.Notice.mart369_admin_save(values={
                'name': 'Backwards', 'text': 'x',
                'publish_at': fields.Datetime.to_string(now),
                'until': fields.Datetime.to_string(now - timedelta(days=1))})

    def test_an_invented_kind_is_refused(self):
        with self.assertRaises(Exception):
            self.Notice.mart369_admin_save(values={
                'name': 'Odd', 'text': 'x', 'kind': 'telepathy'})

    def test_retiring_and_putting_it_back(self):
        row = self.Notice.mart369_admin_save(values={'name': 'On', 'text': 'x'})
        self.assertEqual(
            self.Notice.mart369_admin_retire(row['id'])['state'], 'off')
        self.assertEqual(
            self.Notice.mart369_admin_retire(row['id'], False)['state'], 'live')

    def test_the_staff_shape_does_not_leak_into_the_shopper_one(self):
        notice = self.Notice.create({'name': 'A', 'text': 'x'})
        shopper = notice._mart369_serialize()
        self.assertNotIn('state', shopper)
        self.assertNotIn('until', shopper)
        self.assertIn('title', shopper)


@tagged('post_install', '-at_install')
class TestNoticeAdminRoutes(Mart369AccountHttpCase):

    def setUp(self):
        super().setUp()
        self.notice = self.env['mart369.notice'].create(
            {'name': 'Route test', 'text': 'x'})
        self.shopper = self.env['res.users'].sudo().create({
            'name': 'A Shopper',
            'login': 'mart369_notice_shopper',
            'password': 'mart369_notice_shopper',
            'group_ids': [(6, 0, [self.env.ref('base.group_portal').id])],
        })

    def _send(self, method, path, payload=None):
        return self.url_open(path, data=json.dumps(payload or {}),
                             headers=HEADERS, method=method)

    def test_a_shopper_is_refused_every_route(self):
        self.authenticate('mart369_notice_shopper', 'mart369_notice_shopper')
        self.assertEqual(self.url_open(LIST).status_code, 403)
        self.assertEqual(self.url_open(LIST + '/counts').status_code, 403)
        self.assertEqual(
            self._send('POST', LIST, {'name': 'x', 'text': 'y'}).status_code, 403)
        self.assertEqual(
            self._send('PATCH', '%s/%s' % (LIST, self.notice.id),
                       {'retired': True}).status_code, 403)
        self.assertTrue(self.notice.active, 'and nothing moved')

    def test_staff_write_and_retire_one(self):
        self.authenticate('admin', 'admin')
        made = self._send('POST', LIST, {
            'name': 'From the console', 'text': 'Hello everybody.',
            'kind': 'order'})
        self.assertEqual(made.status_code, 201)
        notice_id = made.json()['notice']['id']

        gone = self._send('PATCH', '%s/%s' % (LIST, notice_id), {'retired': True})
        self.assertEqual(gone.status_code, 200)
        self.assertEqual(gone.json()['notice']['state'], 'off')

    def test_there_is_no_way_to_delete_a_notice(self):
        """Somebody has already read it. Deleting does not untell them."""
        self.authenticate('admin', 'admin')
        response = self._send('DELETE', '%s/%s' % (LIST, self.notice.id))
        self.assertNotEqual(response.status_code, 200)
        self.assertTrue(
            self.env['mart369.notice'].with_context(active_test=False)
            .browse(self.notice.id).exists())

    def test_an_empty_notice_says_so(self):
        self.authenticate('admin', 'admin')
        response = self._send('POST', LIST, {'name': 'Title', 'text': ''})
        self.assertEqual(response.status_code, 400)

    def test_counts_is_not_read_as_an_id(self):
        self.authenticate('admin', 'admin')
        payload = self.url_open(LIST + '/counts').json()
        self.assertTrue(payload['ok'])
        self.assertIn('live', payload['counts'])
        self.assertNotIn('notices', payload)
