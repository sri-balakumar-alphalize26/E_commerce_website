"""The slot list on the Delivery settings page (17 Nov 2026, "slots in one place").

The page shows and saves the list customers are offered - the website's own,
or the WhatsApp Quick / Express one when that module runs - with the page's
one Save all: all or nothing, a wrong value named under its field, and a slot
switched off rather than deleted. These tests read the list through the page,
so they hold for either.
"""

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


def row(**kw):
    out = {'id': None, 'key': 'new-1', 'mode': 'quick', 'kind': 'window', 'heading': 'Zz Today',
           'detail': '6 - 8 PM', 'dayOffset': '0', 'fromHour': '18', 'toHour': '20',
           'orderBefore': '24', 'fee': '0', 'capacity': '0', 'active': True}
    out.update(kw)
    return out


@tagged('post_install', '-at_install')
class TestDeliverySettingsSlots(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Page = self.env['mart369.delivery.settings.page']

    def _rows(self):
        return self.Page.mart369_settings_get()['slots']['rows']

    def _find(self, heading):
        return next((r for r in self._rows() if r['heading'] == heading), None)

    def test_the_page_lists_the_slots_with_their_choices(self):
        slots = self.Page.mart369_settings_get()['slots']
        for key in ('on', 'count', 'names', 'rows', 'detail', 'modes', 'kinds'):
            self.assertIn(key, slots)
        self.assertEqual({m['key'] for m in slots['modes']}, {'quick', 'all'})
        self.assertEqual({k['key'] for k in slots['kinds']}, {'now', 'window', 'days'})

    def test_a_new_slot_is_added_with_save_all(self):
        before = len(self._rows())
        result = self.Page.mart369_settings_save({'slots': self._rows() + [row()]})
        self.assertTrue(result['ok'], result)
        added = self._find('Zz Today')
        self.assertTrue(added)
        self.assertEqual((added['fromHour'], added['toHour'], added['active']), (18.0, 20.0, True))
        self.assertEqual(len(self._rows()), before + 1)

    def test_a_slot_is_changed_and_switched_off_never_deleted(self):
        self.Page.mart369_settings_save({'slots': self._rows() + [row()]})
        rows = self._rows()
        mine = next(r for r in rows if r['heading'] == 'Zz Today')
        mine.update(heading='Zz Evening', fromHour='17.5', toHour='19', capacity='4', active=False)
        result = self.Page.mart369_settings_save({'slots': rows})
        self.assertTrue(result['ok'], result)
        saved = self._find('Zz Evening')
        self.assertEqual((saved['fromHour'], saved['toHour'], saved['capacity'], saved['active']),
                         (17.5, 19.0, 4, False))
        record = self.Page._page_slot_records().filtered(lambda s: s.id == saved['id'])
        self.assertTrue(record.exists(), 'switched off, still there')
        self.assertFalse(record.active)

    def test_a_wrong_value_saves_nothing_and_names_it(self):
        self.Page.mart369_settings_save({'slots': self._rows() + [row()]})
        rows = self._rows()
        mine = next(r for r in rows if r['heading'] == 'Zz Today')
        mine.update(heading='Zz Changed', fromHour='20', toHour='18')
        result = self.Page.mart369_settings_save({'slots': rows})
        self.assertFalse(result['ok'])
        self.assertIn({'section': 'slots', 'row': mine['id'], 'field': 'toHour'},
                      [{k: e[k] for k in ('section', 'row', 'field')} for e in result['errors']])
        self.assertTrue(self._find('Zz Today'), 'nothing was written')
        self.assertFalse(self._find('Zz Changed'))

    def test_a_new_slot_needs_words_and_good_hours(self):
        result = self.Page.mart369_settings_save({'slots': [row(heading=' ', fromHour='25')]})
        self.assertFalse(result['ok'])
        fields = {(e['row'], e['field']) for e in result['errors']}
        self.assertIn(('new-1', 'heading'), fields)
        self.assertIn(('new-1', 'fromHour'), fields)

    def test_unchanged_rows_write_nothing(self):
        self.Page.mart369_settings_save({'slots': self._rows() + [row()]})
        record = self.Page._page_slot_records().filtered(lambda s: s.id == self._find('Zz Today')['id'])
        stamp = record.write_date
        self.env.flush_all()
        result = self.Page.mart369_settings_save({'slots': self._rows()})
        self.assertTrue(result['ok'], result)
        self.assertEqual(record.write_date, stamp)

    def test_a_website_slot_moved_to_express_gets_a_free_key(self):
        records = self.Page._page_slot_records()
        if records._name != 'mart369.delivery.slot':
            self.skipTest('the WhatsApp Quick / Express slot list is in use here')
        Slot = self.env['mart369.delivery.slot']
        Slot.create({'mode': 'all', 'kind': 'window', 'key': 'zz-same', 'top': 'Zz Express one'})
        quick = Slot.create({'mode': 'quick', 'kind': 'window', 'key': 'zz-same', 'top': 'Zz Quick one'})
        rows = self._rows()
        mine = next(r for r in rows if r['id'] == quick.id)
        mine['mode'] = 'all'
        result = self.Page.mart369_settings_save({'slots': rows})
        self.assertTrue(result['ok'], result)
        self.assertEqual(quick.mode, 'all')
        self.assertNotEqual(quick.key, 'zz-same')
