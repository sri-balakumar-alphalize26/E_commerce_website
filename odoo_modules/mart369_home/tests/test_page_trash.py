"""Removing a saved page puts it in the Trash.

Every band on a page already waits thirty days before it is destroyed. The
page holding them did not, and a page is weeks of somebody's work sitting
behind a button next to Duplicate.

Three things are worth pinning, and they are the three that would not announce
themselves when they break.

**A page in the Trash is not served.** `_mart369_live()` is what decides what
shoppers get. If a trashed page can still win that choice, "deleting" a page
changes nothing a customer sees and the operator has no way to tell.

**The last page still cannot go.** Trashing has to refuse the same two things
unlinking refuses, or the shop ends up with no home page at all.

**The purge can actually empty the Trash.** The "only saved page" guard counts
kept pages on purpose: counting trashed ones too would make the nightly cron
raise every night instead of doing its job, and nothing would ever be cleared.
"""

from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestPageTrash(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Version = self.env['mart369.home.version']
        self.everyday = self.Version.search([('is_current', '=', True)], limit=1)
        self.assertTrue(self.everyday, 'the module ships an everyday page')
        self.spare = self.everyday.copy({'name': 'Diwali'})

    # ------------------------------------------------------------ the rules

    def test_the_everyday_page_cannot_be_trashed(self):
        with self.assertRaises(UserError):
            self.everyday.action_trash()
        self.assertFalse(self.everyday.deleted_at)

    def test_the_last_kept_page_cannot_be_trashed(self):
        """Trashing refuses what unlinking refuses - otherwise the shop is
        left with nothing to serve and only the Trash to serve it from."""
        others = self.Version.search([('id', '!=', self.everyday.id)])
        others.action_trash()
        with self.assertRaises(UserError):
            self.everyday.action_trash()

    def test_a_spare_page_goes_to_the_trash_and_comes_back(self):
        self.spare.action_trash()
        self.assertTrue(self.spare.deleted_at)
        self.assertIn(self.spare, self.Version.search([])._trashed())
        self.assertNotIn(self.spare, self.Version.search([])._kept())

        self.spare.action_restore()
        self.assertFalse(self.spare.deleted_at)
        self.assertIn(self.spare, self.Version.search([])._kept())

    # ----------------------------------------------------- what shoppers get

    def test_a_trashed_page_is_never_what_the_app_serves(self):
        """The one way this feature could do real damage."""
        self.spare.write({'starts_on': fields.Datetime.now() - timedelta(hours=1)})
        self.assertEqual(self.Version._mart369_live(), self.spare,
                         'an open window takes over, as it always did')

        self.spare.action_trash()
        self.spare.invalidate_recordset()
        live = self.Version._mart369_live()
        self.assertNotEqual(live, self.spare)
        self.assertFalse(live.deleted_at)
        self.assertTrue(live, 'and something is still served')

    def test_the_everyday_page_is_never_picked_from_the_trash(self):
        """`is_current` survives a trip to the Trash, so the fallback has to
        skip it rather than trust the flag."""
        spare = self.spare
        spare.action_mart369_make_current()
        self.everyday.invalidate_recordset()
        self.assertTrue(spare.is_current)

        # Switch back so the copy can be trashed at all.
        self.everyday.action_mart369_make_current()
        spare.invalidate_recordset()
        spare.action_trash()
        self.assertFalse(self.Version._mart369_live().deleted_at)

    # ----------------------------------------------------------- the screens

    def test_the_pages_screen_gets_kept_and_trashed_apart(self):
        self.spare.action_trash()
        data = self.Version.pages_load()
        names = [p['name'] for p in data['pages']]
        trashed = [p['name'] for p in data['trash']]
        self.assertNotIn('Diwali', names)
        self.assertIn('Diwali', trashed)
        self.assertEqual(data['trash_days'], 30)

    def test_a_trashed_card_says_how_long_it_has_left(self):
        self.spare.action_trash()
        card = self.spare._serialize_card()
        self.assertTrue(card['deletedAt'])
        self.assertEqual(card['daysLeft'], 30)

    # ------------------------------------------------------------- the purge

    def test_the_purge_empties_a_page_past_its_retention(self):
        self.spare.action_trash()
        self.spare.deleted_at = fields.Datetime.now() - timedelta(days=31)
        gone = self.env['mart369.config']._cron_purge_trash()
        self.assertTrue(gone)
        self.assertFalse(self.spare.exists())

    def test_the_purge_leaves_a_page_still_inside_its_window(self):
        self.spare.action_trash()
        self.env['mart369.config']._cron_purge_trash()
        self.assertTrue(self.spare.exists())

    def test_the_purge_is_not_blocked_by_the_only_page_guard(self):
        """The guard counts kept pages. If it counted trashed ones too, the
        cron would raise every night and the Trash would never empty.

        Driven down to one kept page rather than asserting a count: this runs
        against whatever database it is pointed at, and a shop that has been
        used has more pages than a fresh one.
        """
        spares = self.Version.search([('id', '!=', self.everyday.id)])
        spares.action_trash()
        spares.deleted_at = fields.Datetime.now() - timedelta(days=31)
        self.assertEqual(
            self.Version.search_count([('deleted_at', '=', False)]), 1,
            'only the everyday page is left out of the Trash')

        self.env['mart369.config']._cron_purge_trash()
        self.assertFalse(spares.exists())
        self.assertTrue(self.everyday.exists(), 'and the shop still has one')

    def test_a_kept_page_is_still_guarded_from_unlink(self):
        """The old rules, unchanged, for anything not in the Trash."""
        with self.assertRaises(UserError):
            self.everyday.unlink()
