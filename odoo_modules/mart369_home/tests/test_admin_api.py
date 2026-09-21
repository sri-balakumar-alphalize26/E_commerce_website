"""The staff side of the home page: which page it edits, and who may edit it.

Two kinds of thing are worth a test here, and they are the two that do not
announce themselves when they break.

The first is *which page*. Since home pages are saved under a name there is one
`quick` per saved page, and a lookup that matches on the key alone returns an
arbitrary one. That does not raise: it quietly opens a festival page's bands
while the shop is serving the everyday one, and every edit lands on the wrong
page.

The second is *whether anything is missing*. A band left out of the payload
cannot be edited, restored or even seen - and nothing on the screen says it is
there. A switched-off banner and an empty row are both easy to drop by
accident, so both are pinned here.
"""

import json

from odoo.tests import TransactionCase, tagged
from odoo.tests.common import HttpCase


@tagged('post_install', '-at_install')
class TestWhichPageIsEdited(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Mode = self.env['mart369.home.mode']
        self.Version = self.env['mart369.home.version']
        self.everyday = self.Version.search([('is_current', '=', True)], limit=1)
        self.assertTrue(self.everyday, 'the module ships an everyday page')

    def test_get_returns_the_live_pages_mode(self):
        mode = self.Mode._get('quick')
        self.assertEqual(mode.version_id, self.everyday)

    def test_get_follows_the_switch(self):
        """The bug this exists for: a copy must not capture the lookup."""
        copy = self.everyday.copy({'name': 'Festival'})
        self.assertEqual(self.Mode._get('quick').version_id, self.everyday,
                         'making a copy must not change what is edited')
        copy.action_mart369_make_current()
        self.assertEqual(self.Mode._get('quick').version_id, copy)

    def test_get_can_be_asked_for_one_page(self):
        copy = self.everyday.copy({'name': 'Festival'})
        self.assertEqual(self.Mode._get('quick', version=copy).version_id, copy)
        self.assertEqual(self.Mode._get('quick').version_id, self.everyday)

    def test_builder_offers_only_this_pages_tabs(self):
        """Six modes across three saved pages must not become six choices."""
        self.everyday.copy({'name': 'Festival'})
        data = self.Mode.builder_load('quick')
        self.assertEqual({m['key'] for m in data['modes']}, {'quick', 'all'})
        self.assertEqual(len(data['modes']), 2)


@tagged('post_install', '-at_install')
class TestThePreviewIsComplete(HttpCase):
    """Everything the editor draws the page from.

    Driven through the route rather than by calling `_preview` directly: it
    reads `request.env`, so outside a real request it is not bound to anything
    - and testing the thing the browser actually receives is the point anyway.

    The editor filters this list itself to show what shoppers see, so anything
    missing here is missing from the screen with no way to bring it back.
    """

    def setUp(self):
        super().setUp()
        self.Version = self.env['mart369.home.version']
        live = self.Version.search([('is_current', '=', True)], limit=1)
        # A copy, like TestAdminRoutes and for the same reason: these hide a
        # banner and add a row, and neither belongs in the real shop.
        self.page = live.copy({'name': 'Preview test page'})
        self.addCleanup(self._drop_test_page)
        self.mode = self.env['mart369.home.mode'].with_context(
            active_test=False)._get('quick', version=self.page)
        self.authenticate('admin', 'admin')

    def _drop_test_page(self):
        page = self.page.exists()
        if page and not page.is_current:
            page.mode_ids.unlink()
            page.unlink()

    def _preview(self):
        response = self.url_open(
            '/369mart/admin/home/pages/%s/builder?mode=quick' % self.page.id)
        self.assertEqual(response.status_code, 200)
        return response.json()['preview']

    def test_every_kept_banner_is_there_with_its_id_and_state(self):
        banner = self.mode.banner_ids._kept()[:1]
        self.assertTrue(banner, 'the seed data ships banners')
        banner.active = False
        self.env.flush_all()
        rows = self._preview()['banners']
        hit = [r for r in rows if r['rid'] == banner.id]
        self.assertEqual(len(hit), 1, 'a switched-off banner still has to be '
                                      'listed, or it can never be switched on')
        self.assertFalse(hit[0]['active'])

    def test_an_empty_row_still_appears(self):
        """`_serialize` returns None for a row with nothing in it, because the
        app should not draw a bare heading. The editor still has to show it."""
        empty = self.env['mart369.home.section'].create({
            'mode_id': self.mode.id,
            'name': 'Nothing in here',
            'source': 'manual',
        })
        self.env.flush_all()
        rows = self._preview()['sections']
        hit = [r for r in rows if r['rid'] == empty.id]
        self.assertEqual(len(hit), 1, 'an invisible row is an unfixable row')
        self.assertTrue(hit[0].get('empty'))
        self.assertEqual(hit[0]['title'], 'Nothing in here')

    def test_the_preview_carries_every_kind(self):
        preview = self._preview()
        self.assertEqual(
            set(preview),
            {'tabs', 'banners', 'categories', 'sections', 'freeDeliveryAt'})
        for key in ('tabs', 'banners', 'categories'):
            self.assertTrue(preview[key], '%s should not be empty' % key)
            for row in preview[key]:
                self.assertIn('rid', row)
                self.assertIn('active', row)


@tagged('post_install', '-at_install')
class TestAdminRoutes(HttpCase):
    """The lock, and the writes the editor makes.

    **Every write here goes to a throwaway copy, never to the live page.**

    These drive real HTTP requests, and a request is not the test's
    transaction: writes made through one can outlive the rollback at the end of
    the test. They did - an earlier version of this file added and removed
    bands on whichever page was live, and left three "New banner" records and a
    removed row sitting in the real shop's Trash. Nothing failed; the debris
    was only found by looking.

    So the page is made in setUp, used for everything, and deleted in
    tearDown - and `self.live` is only ever read, to assert it was left alone.
    """

    def setUp(self):
        super().setUp()
        self.Version = self.env['mart369.home.version']
        self.live = self.Version.search([('is_current', '=', True)], limit=1)
        self.assertTrue(self.live, 'the module ships an everyday page')
        self.page = self.live.copy({'name': 'Admin API test page'})
        self.addCleanup(self._drop_test_page)
        self.mode = self.env['mart369.home.mode'].with_context(
            active_test=False)._get('quick', version=self.page)
        self.shopper = self.env['res.users'].create({
            'name': 'A Shopper',
            'login': 'mart369_test_shopper',
            'password': 'mart369_test_shopper',
            'group_ids': [(6, 0, [self.env.ref('base.group_portal').id])],
        })

    def _drop_test_page(self):
        """Take the copy with us, whatever the transaction does."""
        page = self.page.exists()
        if page and not page.is_current:
            page.mode_ids.unlink()
            page.unlink()

    def _live_banner_ids(self):
        """What the real page holds, Trash included."""
        mode = self.env['mart369.home.mode'].with_context(
            active_test=False)._get('quick', version=self.live)
        return set(mode.banner_ids.with_context(active_test=False).ids)

    def _post(self, path, payload):
        return self.url_open(
            path, data=json.dumps(payload),
            headers={'Content-Type': 'application/json'})

    # ------------------------------------------------------------- the lock

    def test_a_shopper_is_refused_every_admin_route(self):
        """Refused, not filtered. A shopper must not learn this exists."""
        self.authenticate('mart369_test_shopper', 'mart369_test_shopper')
        for path in (
            '/369mart/admin/dashboard',
            '/369mart/admin/home/pages',
            '/369mart/admin/home/pages/%s/bands' % self.page.id,
            '/369mart/admin/home/pages/%s/builder?mode=quick' % self.page.id,
        ):
            response = self.url_open(path)
            self.assertEqual(response.status_code, 403, path)

    def test_a_designer_is_let_in(self):
        self.authenticate('admin', 'admin')
        response = self.url_open(
            '/369mart/admin/home/pages/%s/builder?mode=quick' % self.page.id)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body['ok'])
        self.assertIn('preview', body)

    # ---------------------------------------------------------- the reorder

    def test_reorder_writes_the_order_it_was_given(self):
        self.authenticate('admin', 'admin')
        banners = self.mode.banner_ids._kept().sorted('sequence')
        self.assertTrue(len(banners) > 1, 'needs two banners to reorder')
        wanted = list(reversed(banners.ids))
        response = self._post(
            '/369mart/admin/home/bands/banner/reorder', {'ids': wanted})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['ok'])
        after = self.mode.banner_ids._kept().sorted('sequence').ids
        self.assertEqual(after, wanted)

    def test_reorder_refuses_bands_from_two_different_tabs(self):
        """Otherwise a drag on Quick rewrites the sequence of Express."""
        self.authenticate('admin', 'admin')
        other = self.env['mart369.home.mode'].with_context(
            active_test=False)._get('all', version=self.page)
        mine = self.mode.banner_ids._kept()[:1]
        theirs = other.banner_ids._kept()[:1]
        self.assertTrue(mine and theirs)
        response = self._post('/369mart/admin/home/bands/banner/reorder',
                              {'ids': [mine.id, theirs.id]})
        self.assertEqual(response.status_code, 409)

    def test_reorder_refuses_something_that_is_gone(self):
        self.authenticate('admin', 'admin')
        mine = self.mode.banner_ids._kept()[:1]
        response = self._post('/369mart/admin/home/bands/banner/reorder',
                              {'ids': [mine.id, 0x7FFFFFF]})
        self.assertEqual(response.status_code, 409)

    # ------------------------------------------------------------ the patch

    def test_only_the_listed_fields_can_be_written(self):
        """`key` is what the app matches on. A form that can set any field can
        set that one, and the app would stop finding the banner."""
        self.authenticate('admin', 'admin')
        banner = self.mode.banner_ids._kept()[:1]
        before = banner.key
        response = self.url_open(
            '/369mart/admin/home/bands/banner/%s' % banner.id,
            data=json.dumps({'key': 'hacked'}),
            headers={'Content-Type': 'application/json'}, method='PATCH')
        self.assertEqual(response.status_code, 400)
        banner.invalidate_recordset()
        self.assertEqual(banner.key, before)

    # ------------------------------------------------------------ adding

    def test_a_new_band_lands_on_the_page_it_was_asked_for(self):
        """The whole reason this route names the page in its URL.

        Odoo's own builder infers the page - it always edits the live one - so
        adding a banner while a switched-off festival page was on screen put
        the banner on the everyday page instead, silently.
        """
        self.authenticate('admin', 'admin')
        self.assertFalse(self.page.is_current, 'the test page is not live')
        before = self._live_banner_ids()

        response = self._post(
            '/369mart/admin/home/pages/%s/bands/banner' % self.page.id,
            {'mode': 'quick'})
        self.assertEqual(response.status_code, 201)
        new_id = int(response.json()['band']['id'])

        banner = self.env['mart369.home.banner'].browse(new_id)
        self.assertEqual(banner.mode_id, self.mode)
        self.assertEqual(self._live_banner_ids(), before,
                         'the live page must not have gained a banner')

    def test_a_new_band_goes_after_the_ones_already_there(self):
        self.authenticate('admin', 'admin')
        highest = max(self.mode.banner_ids._kept().mapped('sequence') or [0])
        response = self._post(
            '/369mart/admin/home/pages/%s/bands/banner' % self.page.id,
            {'mode': 'quick'})
        self.assertEqual(response.status_code, 201)
        self.assertGreater(response.json()['band']['sequence'], highest)

    def test_adding_something_that_is_not_a_band_is_refused(self):
        self.authenticate('admin', 'admin')
        response = self._post(
            '/369mart/admin/home/pages/%s/bands/widget' % self.page.id,
            {'mode': 'quick'})
        self.assertEqual(response.status_code, 404)

    def test_a_shopper_cannot_add_or_remove(self):
        self.authenticate('mart369_test_shopper', 'mart369_test_shopper')
        banner = self.mode.banner_ids._kept()[:1]
        self.assertEqual(
            self._post('/369mart/admin/home/pages/%s/bands/banner' % self.page.id,
                       {'mode': 'quick'}).status_code, 403)
        self.assertEqual(
            self.url_open('/369mart/admin/home/bands/banner/%s' % banner.id,
                          method='DELETE').status_code, 403)

    # ---------------------------------------------------------- removing

    def test_removing_puts_it_in_the_trash_rather_than_destroying_it(self):
        """Removing starts a clock; it does not delete. The band has to still
        be there to be put back, and `active` has to be left alone so it comes
        back the way the operator left it."""
        self.authenticate('admin', 'admin')
        banner = self.mode.banner_ids._kept()[:1]
        was_active = banner.active

        response = self.url_open(
            '/369mart/admin/home/bands/banner/%s' % banner.id, method='DELETE')
        self.assertEqual(response.status_code, 200)

        banner.invalidate_recordset()
        self.assertTrue(banner.exists(), 'removing must not destroy it')
        self.assertTrue(banner.deleted_at)
        self.assertEqual(banner.active, was_active,
                         'hiding is a switch; removing starts a clock')
        self.assertNotIn(banner, self.mode.banner_ids._kept())
        banner.action_restore()
        self.assertIn(banner, self.mode.banner_ids._kept())

    def test_the_live_page_is_never_touched_by_these_tests(self):
        """A guard on the suite itself.

        These drive real HTTP requests, which do not necessarily unwind with
        the test transaction. An earlier version of this file wrote to whichever
        page was live and left "New banner" records in the real shop's Trash.
        Adding, removing and restoring all run here against the copy; the live
        page must come out of it exactly as it went in.
        """
        self.authenticate('admin', 'admin')
        before = self._live_banner_ids()

        created = self._post(
            '/369mart/admin/home/pages/%s/bands/banner' % self.page.id,
            {'mode': 'quick'})
        self.assertEqual(created.status_code, 201)
        new_id = created.json()['band']['id']
        self.url_open('/369mart/admin/home/bands/banner/%s' % new_id,
                      method='DELETE')
        self._post('/369mart/admin/home/bands/banner/%s/restore' % new_id, {})

        self.assertEqual(self._live_banner_ids(), before,
                         'these tests changed the live home page')

    # -------------------------------------------------------- the tab's words

    def test_the_promise_can_be_changed_and_reaches_the_app(self):
        """The reason these fields exist.

        "in minutes" and "2-5 day delivery" are what the shop tells a customer
        it will do, and they were written into the storefront's source until
        now. Changing one must not need a deploy.
        """
        self.authenticate('admin', 'admin')
        response = self.url_open(
            '/369mart/admin/home/pages/%s/modes/all' % self.page.id,
            data=json.dumps({'tagline': 'Delivered in 2 to 5 days'}),
            headers={'Content-Type': 'application/json'}, method='PATCH')
        self.assertEqual(response.status_code, 200)

        mode = self.env['mart369.home.mode'].with_context(
            active_test=False)._get('all', version=self.page)
        mode.invalidate_recordset()
        self.assertEqual(mode._serialize()['tagline'], 'Delivered in 2 to 5 days')

    def test_a_blank_promise_falls_back_rather_than_showing_nothing(self):
        """An empty promise is worse than the app's own wording."""
        self.authenticate('admin', 'admin')
        self.url_open(
            '/369mart/admin/home/pages/%s/modes/quick' % self.page.id,
            data=json.dumps({'label': '', 'tagline': ''}),
            headers={'Content-Type': 'application/json'}, method='PATCH')
        mode = self.env['mart369.home.mode'].with_context(
            active_test=False)._get('quick', version=self.page)
        mode.invalidate_recordset()
        vals = mode._copy_vals()
        self.assertEqual(vals['label'], 'Quick')
        self.assertTrue(vals['tagline'])
        self.assertEqual(vals['icon'], 'bolt', 'Quick has always had a bolt')

    def test_the_tab_route_refuses_a_tab_that_does_not_exist(self):
        self.authenticate('admin', 'admin')
        response = self.url_open(
            '/369mart/admin/home/pages/%s/modes/weekend' % self.page.id,
            data=json.dumps({'tagline': 'x'}),
            headers={'Content-Type': 'application/json'}, method='PATCH')
        self.assertEqual(response.status_code, 404)

    def test_the_tab_route_will_not_write_the_key(self):
        """`key` is what the app matches a tab on."""
        self.authenticate('admin', 'admin')
        mode = self.env['mart369.home.mode'].with_context(
            active_test=False)._get('quick', version=self.page)
        response = self.url_open(
            '/369mart/admin/home/pages/%s/modes/quick' % self.page.id,
            data=json.dumps({'key': 'all'}),
            headers={'Content-Type': 'application/json'}, method='PATCH')
        self.assertEqual(response.status_code, 400)
        mode.invalidate_recordset()
        self.assertEqual(mode.key, 'quick')

    def test_a_shopper_cannot_change_what_the_shop_promises(self):
        self.authenticate('mart369_test_shopper', 'mart369_test_shopper')
        response = self.url_open(
            '/369mart/admin/home/pages/%s/modes/quick' % self.page.id,
            data=json.dumps({'tagline': 'Instant, guaranteed'}),
            headers={'Content-Type': 'application/json'}, method='PATCH')
        self.assertEqual(response.status_code, 403)
