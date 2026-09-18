from datetime import timedelta

from odoo import fields
from odoo.tests import tagged
from odoo.tests.common import HttpCase, TransactionCase

BUILDER_KEYS = {'mode', 'modes', 'vocab', 'bands', 'banners', 'tiles', 'tabs',
                'categories', 'tags', 'trash', 'trash_days'}
BAND_KEYS = {'id', 'kind', 'active', 'sequence', 'name', 'key', 'subtitle',
             'view_all_route', 'source', 'public_categ_id', 'public_categ_name',
             'include_child_categs', 'product_tag_id', 'product_tag_name',
             'rule', 'rule_days', 'limit', 'product_count', 'picked', 'lines',
             'preview'}


@tagged('post_install', '-at_install')
class TestBuilderLoad(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Mode = self.env['mart369.home.mode']
        self.mode = self.Mode._get('quick')

    def test_shape(self):
        """The one call the builder makes returns everything it draws from."""
        data = self.Mode.builder_load('quick')
        self.assertEqual(set(data), BUILDER_KEYS)
        self.assertEqual(data['mode']['key'], 'quick')
        self.assertEqual({m['key'] for m in data['modes']}, {'quick', 'all'})
        self.assertEqual(set(data['vocab']), {'art', 'icons', 'tones'})
        self.assertTrue(data['bands'], 'The seed data should ship bands.')
        for band in data['bands']:
            self.assertEqual(set(band), BAND_KEYS)

    def test_hidden_band_is_included_with_a_preview(self):
        """Hidden bands stay in the list, greyed, so they can be switched back on."""
        band = self.env.ref('mart369_home.section_q_strip')
        band.active = False
        try:
            data = self.Mode.builder_load('quick')
            hit = [b for b in data['bands'] if b['id'] == band.id]
            self.assertEqual(len(hit), 1)
            self.assertFalse(hit[0]['active'])
            self.assertIsNotNone(hit[0]['preview'])
        finally:
            band.active = True

    def test_previews_match_what_the_app_receives(self):
        """The mock and the app must draw from the same computation."""
        data = self.Mode.builder_load('quick')
        api = self.mode._serialize()
        previews = [b['preview'] for b in data['bands'] if b['active'] and b['preview']]
        self.assertEqual(previews, api['sections'])

    def test_resequence_reorders_bands(self):
        """Drag-and-drop persists through web_resequence, in the order given."""
        Section = self.env['mart369.home.section']
        ids = [b['id'] for b in self.Mode.builder_load('quick')['bands']]
        Section.browse(list(reversed(ids))).web_resequence({}, field_name='sequence')
        after = [b['id'] for b in self.Mode.builder_load('quick')['bands']]
        self.assertEqual(after, list(reversed(ids)))

    def test_unknown_mode(self):
        from odoo.exceptions import UserError
        with self.assertRaises(UserError):
            self.Mode.builder_load('nope')

    def test_website_designer_can_use_the_builder(self):
        """An operator who is not an admin can load and edit."""
        designer = self.env['res.users'].create({
            'name': 'Ops Designer',
            'login': 'ops_designer_mart369',
            'group_ids': [(6, 0, [
                self.env.ref('base.group_user').id,
                self.env.ref('website.group_website_designer').id,
            ])],
        })
        Mode = self.Mode.with_user(designer)
        data = Mode.builder_load('quick')
        self.assertTrue(data['bands'])
        band_id = data['bands'][0]['id']
        section = self.env['mart369.home.section'].with_user(designer).browse(band_id)
        section.write({'name': 'Renamed by ops'})
        self.assertEqual(section.name, 'Renamed by ops')
        self.env['mart369.home.banner'].with_user(designer).create({
            'mode_id': self.mode.id, 'key': 'ops-test', 'name': 'Ops banner', 'tone': 'teal',
        })


@tagged('post_install', '-at_install')
class TestTrash(TransactionCase):
    """Removing something must be recoverable, and invisible to the app."""

    def setUp(self):
        super().setUp()
        self.Mode = self.env['mart369.home.mode']
        self.mode = self.Mode._get('quick')
        self.banner = self.env.ref('mart369_home.banner_b3')

    def test_trash_hides_from_the_app_but_keeps_the_record(self):
        self.banner.action_trash()
        self.assertTrue(self.banner.exists(), 'The record must survive.')
        self.assertTrue(self.banner.deleted_at)

        payload = self.mode._serialize()
        self.assertNotIn('b3', [b['id'] for b in payload['banners']])
        # b3 sits in the seeded mid-page strip; that must drop it too.
        for section in payload['sections']:
            self.assertNotIn('b3', section.get('banner', []))

    def test_trash_leaves_the_builder_lists_and_appears_in_trash(self):
        self.banner.action_trash()
        data = self.Mode.builder_load('quick')
        self.assertNotIn('b3', [b['key'] for b in data['banners']])
        rows = [r for r in data['trash'] if r['model'] == 'mart369.home.banner'
                and r['id'] == self.banner.id]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['what'], 'Banner')
        self.assertEqual(rows[0]['days_left'], data['trash_days'])

    def test_restore_returns_it_exactly_as_it_was(self):
        """A hidden banner comes back hidden, not switched on."""
        self.banner.active = False
        self.banner.action_trash()
        self.banner.action_restore()
        self.assertFalse(self.banner.deleted_at)
        self.assertFalse(self.banner.active, 'Restore must not un-hide it.')
        self.assertIn('b3', [b['key'] for b in
                             self.Mode.builder_load('quick')['banners']])

    def test_days_left_counts_down_and_rounds_up(self):
        config = self.env['mart369.config']._get()
        config.trash_days = 30
        self.banner.action_trash()
        self.assertEqual(self.banner.trash_days_left, 30)
        self.banner.deleted_at = fields.Datetime.now() - timedelta(days=29, hours=22)
        self.banner.invalidate_recordset(['trash_days_left'])
        self.assertEqual(self.banner.trash_days_left, 1,
                         'Two hours left is one day left, not zero.')

    def test_cron_empties_only_what_is_past_its_time(self):
        config = self.env['mart369.config']._get()
        config.trash_days = 30
        fresh = self.env.ref('mart369_home.banner_b4')
        fresh.action_trash()
        self.banner.action_trash()
        self.banner.deleted_at = fields.Datetime.now() - timedelta(days=31)

        gone = self.env['mart369.config']._cron_purge_trash()
        self.assertEqual(gone, 1)
        self.assertFalse(self.banner.exists(), 'The expired one is gone.')
        self.assertTrue(fresh.exists(), 'The fresh one stays.')

    def test_zero_days_keeps_everything(self):
        config = self.env['mart369.config']._get()
        config.trash_days = 0
        self.banner.action_trash()
        self.banner.deleted_at = fields.Datetime.now() - timedelta(days=999)
        self.assertEqual(self.env['mart369.config']._cron_purge_trash(), 0)
        self.assertTrue(self.banner.exists())

    def test_a_trashed_row_leaves_the_page(self):
        band = self.env.ref('mart369_home.section_q_new')
        band.action_trash()
        keys = [s.get('key') for s in self.mode._serialize()['sections']]
        self.assertNotIn('new', keys)
        self.assertNotIn(band.id, [b['id'] for b in
                                   self.Mode.builder_load('quick')['bands']])


@tagged('post_install', '-at_install')
class TestBuilderTour(HttpCase):

    def test_builder_tour(self):
        # A generous timeout: the first request after an upgrade rebuilds the
        # backend asset bundle, which can take minutes on a big database.
        self.start_tour('/odoo/mart-home', 'mart369_home_builder', login='admin',
                        timeout=600)
