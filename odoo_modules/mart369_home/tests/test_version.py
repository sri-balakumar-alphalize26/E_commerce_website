"""Saved home pages: the switch that changes the whole shop.

The tests worth having here are the ones about *which page is served*, because
getting that wrong does not raise an error - it quietly shows every shopper
the wrong home page, or none at all.
"""

from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestMart369HomeVersion(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Version = self.env['mart369.home.version']
        self.everyday = self.Version.search([('is_current', '=', True)], limit=1)
        self.assertTrue(self.everyday, 'the module ships an everyday page')

    def _copy(self, **values):
        return self.everyday.copy(dict({'name': 'Festival'}, **values))

    # ------------------------------------------------------- what is served

    def test_the_everyday_page_is_what_the_app_gets(self):
        self.assertEqual(self.Version._mart369_live(), self.everyday)

    def test_a_saved_page_changes_nothing_until_it_is_live(self):
        """Building next month's page must not touch this month's shop."""
        self._copy()
        self.assertEqual(self.Version._mart369_live(), self.everyday)

    def test_a_copy_brings_the_whole_page_with_it(self):
        """Odoo does not copy one-to-many fields by default, so a duplicate
        arrived as two empty tabs until the fields said otherwise."""
        source = self.env['mart369.home.mode'].search(
            [('version_id', '=', self.everyday.id), ('key', '=', 'quick')], limit=1)
        self.assertTrue(source.banner_ids, 'the everyday page has banners')
        copy = self._copy()
        copied = copy.mode_ids.filtered(lambda m: m.key == 'quick')
        self.assertEqual(len(copy.mode_ids), 2, 'both tabs come across')
        self.assertEqual(len(copied.banner_ids), len(source.banner_ids))
        self.assertEqual(len(copied.tile_ids), len(source.tile_ids))
        self.assertEqual(len(copied.section_ids), len(source.section_ids))

    def test_switching_one_on_switches_the_others_off(self):
        copy = self._copy()
        copy.action_mart369_make_current()
        self.assertEqual(self.Version._mart369_live(), copy)
        self.everyday.invalidate_recordset()
        self.assertFalse(self.everyday.is_current)
        self.assertEqual(
            self.Version.search_count([('is_current', '=', True)]), 1,
            'never two everyday pages, and never none')

    # --------------------------------------------------------- the schedule

    def test_an_open_window_takes_over_from_the_everyday_page(self):
        now = fields.Datetime.now()
        self._copy(starts_on=now - timedelta(minutes=5),
                   ends_on=now + timedelta(hours=1))
        self.assertEqual(self.Version._mart369_live().name, 'Festival')

    def test_a_closed_window_hands_back_on_its_own(self):
        """The whole point. Nobody is awake when a sale ends."""
        now = fields.Datetime.now()
        self._copy(starts_on=now - timedelta(hours=2),
                   ends_on=now - timedelta(minutes=1))
        self.assertEqual(self.Version._mart369_live(), self.everyday)

    def test_a_window_that_has_not_opened_yet_changes_nothing(self):
        now = fields.Datetime.now()
        self._copy(starts_on=now + timedelta(days=2))
        self.assertEqual(self.Version._mart369_live(), self.everyday)

    def test_the_state_says_which_and_why(self):
        now = fields.Datetime.now()
        soon = self._copy(name='Soon', starts_on=now + timedelta(days=1))
        over = self._copy(name='Over', ends_on=now - timedelta(days=1))
        self.assertEqual(self.everyday.state, 'live')
        self.assertEqual(soon.state, 'scheduled')
        self.assertEqual(over.state, 'ended')
        self.assertEqual(self._copy(name='Idle').state, 'off')

    # ------------------------------------------------------------ the feed

    def test_the_app_is_served_the_live_page(self):
        copy = self._copy()
        banner = copy.mode_ids.filtered(lambda m: m.key == 'quick').banner_ids[:1]
        banner.name = 'FESTIVAL BANNER'
        copy.action_mart369_make_current()
        payload = self.env['mart369.config']._get()._serialize_modes()
        titles = [b.get('title') or b.get('name')
                  for b in payload['quick']['banners']]
        self.assertIn('FESTIVAL BANNER', titles)

    def test_the_shop_is_never_served_an_empty_home_page(self):
        """A page with no tabs can only happen mid-upgrade, and a blank shop
        is never the right answer to it."""
        empty = self.Version.create({'name': 'Empty'})
        empty.action_mart369_make_current()
        payload = self.env['mart369.config']._get()._serialize_modes()
        self.assertTrue(payload, 'fell back rather than serving nothing')

    # ------------------------------------------------------------ the rules

    def test_the_live_page_cannot_be_deleted(self):
        with self.assertRaises(UserError):
            self.everyday.unlink()

    def test_the_last_page_cannot_be_deleted(self):
        others = self.Version.search([('id', '!=', self.everyday.id)])
        others.unlink()
        with self.assertRaises(UserError):
            self.everyday.unlink()
