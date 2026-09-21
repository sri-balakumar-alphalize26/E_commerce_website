"""The staff side of the home page, for the app's own admin screens.

Everything else under /369mart answers "this shopper's own things" and can
safely run as the system, because the record is always found inside `_me()`
first. Nothing here has that fence, so two rules apply throughout:

* **The group is checked on every route.** Editing the home page is already
  `website.group_website_designer` in this module's access rules - that is who
  may change a banner today, so it is who may change one from the app. No new
  role invented for the same question.
* **Nothing is sudo'd.** Reads and writes run as the person signed in, so
  Odoo's own access rules and, later, multi-company isolation apply on their
  own rather than being re-implemented here badly.
"""

import logging
import uuid

from odoo import http
from odoo.exceptions import AccessError, UserError
from odoo.http import request

_logger = logging.getLogger(__name__)

_GET = {'type': 'http', 'auth': 'user', 'methods': ['GET'],
        'csrf': False, 'sitemap': False}
_POST = {'type': 'http', 'auth': 'user', 'methods': ['POST'],
         'csrf': False, 'sitemap': False}
_PATCH = {'type': 'http', 'auth': 'user', 'methods': ['PATCH'],
          'csrf': False, 'sitemap': False}
_DELETE = {'type': 'http', 'auth': 'user', 'methods': ['DELETE'],
           'csrf': False, 'sitemap': False}

EDITOR_GROUP = 'website.group_website_designer'


class Mart369HomeAdminApi(http.Controller):

    # --------------------------------------------------------------- helpers

    def _json(self, payload, status=200):
        return request.make_json_response(payload, status=status)

    def _fail(self, error, status=400):
        return self._json({'ok': False, 'error': error}, status=status)

    def _body(self):
        try:
            data = request.get_json_data()
        except Exception:  # noqa: BLE001
            data = None
        return data if isinstance(data, dict) else {}

    def _may_edit(self):
        """Refused, not filtered. A shopper must not learn this exists."""
        return request.env.user.has_group(EDITOR_GROUP)

    def _pages(self):
        """Not sudo'd - on purpose. See the module docstring."""
        return request.env['mart369.home.version']

    def _page(self, page_id):
        try:
            page = self._pages().browse(int(page_id)).exists()
        except (TypeError, ValueError):
            return self._pages()
        return page

    def _serialize(self, page):
        """One saved page as a card. Shape lives on the model, so the pages
        screen in Odoo and the console draw the same thing."""
        return page._serialize_card()

    # Which fields of a band the admin may change. A list rather than "write
    # whatever arrived": a form that can set any field can set `key`, which
    # the app matches on, or `sequence` for a band on another page.
    BAND_FIELDS = {
        'banner': ('kicker', 'name', 'note', 'tone', 'href', 'active'),
        'tab': ('name', 'icon', 'active'),
        'tile': ('name', 'route', 'active'),
        'section': ('name', 'subtitle', 'view_all_route', 'active'),
    }
    BAND_MODEL = {
        'banner': 'mart369.home.banner',
        'tab': 'mart369.home.tab',
        'tile': 'mart369.home.tile',
        'section': 'mart369.home.section',
    }

    def _band(self, kind, band_id):
        model = self.BAND_MODEL.get(kind)
        if not model:
            return None
        try:
            return request.env[model].browse(int(band_id)).exists()
        except (TypeError, ValueError):
            return request.env[model]

    def _serialize_band(self, kind, band):
        out = {'id': str(band.id), 'kind': kind, 'sequence': band.sequence,
               'active': band.active, 'name': band.name or ''}
        for field in self.BAND_FIELDS[kind]:
            if field in ('name', 'active'):
                continue
            value = band[field]
            out[field] = value if value else ''
        return out

    # ---------------------------------------------------------------- routes

    @http.route('/369mart/admin/home/pages', **_GET)
    def pages(self, **kwargs):
        """Every saved home page, for the tiles screen."""
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        pages = self._pages().search([])
        return self._json({
            'ok': True,
            'pages': [self._serialize(p) for p in pages],
        })

    @http.route('/369mart/admin/home/pages', **_POST)
    def create_page(self, **kwargs):
        """Make a new saved page by copying one.

        Copying rather than starting empty, because nobody wants to rebuild a
        home page from nothing to run a three-day sale.
        """
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        body = self._body()
        source = self._page(body.get('from'))
        if not source:
            source = self._pages().search([('is_current', '=', True)], limit=1)
        if not source:
            return self._fail('There is no page to copy.', status=404)
        try:
            page = source.copy({'name': (body.get('name') or '').strip()
                                or request.env._('%s (copy)', source.name)})
        except AccessError:
            return self._fail('You do not have access to this.', status=403)
        return self._json({'ok': True, 'page': self._serialize(page)},
                          status=201)

    @http.route('/369mart/admin/home/pages/<int:page_id>/bands', **_GET)
    def bands(self, page_id, **kwargs):
        """Everything inside one saved page, tab by tab.

        The Trash is left out - `_kept()` rather than every row ever - so a
        removed banner does not come back to haunt the editor.
        """
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        page = self._page(page_id)
        if not page:
            return self._fail('No such page.', status=404)
        modes = {}
        for mode in page.mode_ids.sorted('sequence'):
            modes[mode.key] = {
                'name': mode.name or '',
                'active': mode.active,
                'banners': [self._serialize_band('banner', b)
                            for b in mode.banner_ids._kept().sorted('sequence')],
                'tabs': [self._serialize_band('tab', b)
                         for b in mode.tab_ids._kept().sorted('sequence')],
                'tiles': [self._serialize_band('tile', b)
                          for b in mode.tile_ids._kept().sorted('sequence')],
                'sections': [self._serialize_band('section', b)
                             for b in mode.section_ids._kept().sorted('sequence')],
            }
        return self._json({
            'ok': True,
            'page': self._serialize(page),
            'modes': modes,
        })

    @http.route('/369mart/admin/dashboard', **_GET)
    def dashboard(self, **kwargs):
        """The numbers the backend's own boards already compute.

        `mart369_order_dashboard` and `mart369_customer_dashboard` are what the
        strips above Odoo's Orders and Customers lists print, counted with
        `search_count` and one `_read_group` rather than by reading orders into
        memory. The console shows the same numbers from the same call, so the
        two screens can never disagree about how many orders are waiting.

        Each is optional, and absent means absent: a console that invents a
        revenue figure because a module is not installed is worse than one
        that shows nothing.
        """
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        out = {'ok': True}
        blocks = (
            ('orders', 'sale.order', 'mart369_order_dashboard'),
            ('customers', 'res.users', 'mart369_customer_dashboard'),
        )
        for key, model, method in blocks:
            if model not in request.env:
                continue
            target = request.env[model]
            if not hasattr(target, method):
                continue
            try:
                out[key] = getattr(target, method)()
            except (AccessError, UserError) as exc:
                _logger.info('369 Mart console: no %s numbers (%s)', key, exc)
        return self._json(out)

    @http.route('/369mart/admin/home/pages/<int:page_id>/builder', **_GET)
    def builder(self, page_id, mode='quick', **kwargs):
        """Everything the phone editor needs for one tab of one saved page.

        `builder_load` already assembles exactly this for Odoo's own builder -
        bands with their editable fields, the tone and icon vocabulary, the
        categories and tags - so this route resolves the page and hands that
        back rather than growing a second, drifting copy of it.

        What is added is `preview`: the same dict the app is served for this
        tab, so the phone on the left draws the storefront's own components
        from the storefront's own payload. Built from `_kept()` rather than
        `_live()`, with `rid` and `active` on every entry, because a switched
        off banner still needs a row to click and an eye to switch back on.
        """
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        page = self._page(page_id)
        if not page:
            return self._fail('No such page.', status=404)
        if mode not in ('quick', 'all'):
            return self._fail('There is no such tab.', status=404)
        try:
            data = request.env['mart369.home.mode'].builder_load(
                mode, version_id=page.id)
        except (AccessError, UserError) as exc:
            return self._fail(str(exc), status=404)
        # `preview`, `trash_preview`, `page` and each Trash row's `kind` are
        # assembled by `builder_load` itself, so this route and Odoo's own
        # builder cannot answer "what is on this page?" differently.
        data['ok'] = True
        return self._json(data)

    def _drawable(self, mode, pick):
        """Bands serialized the way the app receives them. Lives on the mode -
        see `mart369.home.mode._drawable`, which the Odoo builder reads too."""
        return mode._drawable(pick)

    def _preview(self, page, mode_key):
        """The app's own payload for this tab, hidden bands included."""
        mode = request.env['mart369.home.mode'].with_context(
            active_test=False)._get(mode_key, version=page)
        if not mode:
            return {}
        return mode._preview_payload()

    def _trash_preview(self, page, mode_key):
        """Everything in the Trash, drawn rather than described."""
        mode = request.env['mart369.home.mode'].with_context(
            active_test=False)._get(mode_key, version=page)
        if not mode:
            return {}
        return mode._trash_preview_map()

    # What a brand-new band is, before anybody has typed anything into it.
    #
    # The same values the Odoo builder's own `addBanner`/`addTile`/`addTab`/
    # `addBand` use, on purpose: a banner made from the console and one made
    # from Odoo have to be the same kind of thing, or "it looks different
    # depending on where you made it" becomes a bug nobody can reproduce.
    NEW_BAND = {
        'banner': lambda key: {
            'key': 'b-%s' % key, 'name': 'New banner',
            'kicker': '', 'note': '', 'tone': 'green',
        },
        'tile': lambda key: {
            'key': 'tile-%s' % key, 'name': 'New tile',
            'image_source': 'art', 'art': 'Pack', 'bg': '#f1f4f6',
        },
        'tab': lambda key: {
            'key': 'tab-%s' % key, 'name': 'New tab',
            'icon': 'grid', 'route_view': 'category',
        },
        'section': lambda key: {
            'key': 'sec-%s' % key, 'name': 'New row',
            'kind': 'rail', 'source': 'category',
        },
    }

    @http.route('/369mart/admin/home/pages/<int:page_id>/bands/<string:kind>',
                **_POST)
    def create_band(self, page_id, kind, **kwargs):
        """Add a banner, tile, tab or row to one tab of one saved page.

        The page is named in the URL rather than inferred. Odoo's own builder
        infers it - it always edits whichever page is live - so adding a banner
        while a switched-off festival page was open on screen quietly put the
        banner on the everyday page instead. The console must not be able to do
        that, so the page it is showing is the page it writes to.
        """
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        if kind not in self.BAND_MODEL:
            return self._fail('There is no such thing to add.', status=404)
        page = self._page(page_id)
        if not page:
            return self._fail('No such page.', status=404)

        mode_key = self._body().get('mode') or kwargs.get('mode') or 'quick'
        if mode_key not in ('quick', 'all'):
            return self._fail('There is no such tab.', status=404)
        mode = request.env['mart369.home.mode'].with_context(
            active_test=False)._get(mode_key, version=page)
        if not mode:
            return self._fail('That page has no such tab.', status=404)

        model = request.env[self.BAND_MODEL[kind]]
        field = {'banner': 'banner_ids', 'tile': 'tile_ids',
                 'tab': 'tab_ids', 'section': 'section_ids'}[kind]
        existing = mode[field].with_context(active_test=False)
        values = dict(
            self.NEW_BAND[kind](uuid.uuid4().hex[:5]),
            mode_id=mode.id,
            # After everything already there, so a new band appears at the
            # bottom rather than in the middle of the page.
            sequence=max(existing.mapped('sequence') or [0]) + 10,
        )
        try:
            band = model.create(values)
        except (AccessError, UserError, ValueError) as exc:
            return self._fail(str(exc))
        return self._json({'ok': True, 'band': self._serialize_band(kind, band)},
                          status=201)

    @http.route('/369mart/admin/home/bands/<string:kind>/<int:band_id>',
                **_DELETE)
    def delete_band(self, kind, band_id, **kwargs):
        """Move one band to the Trash.

        Removing is not hiding, and it is not destroying. The band waits in the
        Trash for the number of days set in Home Page Settings and can be put
        back exactly as it was in the meantime - which is why this writes
        `deleted_at` through the model rather than unlinking.
        """
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        band = self._band(kind, band_id)
        if band is None:
            return self._fail('There is no such thing to remove.', status=404)
        if not band:
            return self._fail('No such item.', status=404)
        try:
            band.action_trash()
        except (AccessError, UserError) as exc:
            return self._fail(str(exc))
        return self._json({'ok': True, 'id': str(band_id), 'kind': kind})

    @http.route('/369mart/admin/home/bands/<string:kind>/<int:band_id>/restore',
                **_POST)
    def restore_band(self, kind, band_id, **kwargs):
        """Take one band back out of the Trash, exactly as it was.

        `active` is untouched on the way in and on the way out, so something
        removed while hidden comes back hidden. Hiding is a switch; removing
        started a clock.
        """
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        band = self._band(kind, band_id)
        if band is None:
            return self._fail('There is no such thing to restore.', status=404)
        if not band:
            return self._fail('No such item.', status=404)
        try:
            band.action_restore()
        except (AccessError, UserError) as exc:
            return self._fail(str(exc))
        return self._json({'ok': True, 'band': self._serialize_band(kind, band)})

    # The tab's own settings. `label`, `icon` and `tagline` are what the app
    # tells a shopper this tab is - the words that used to be written into the
    # storefront - and `free_delivery_at` is the nudge amount. Listed, like
    # BAND_FIELDS, so a form cannot reach `key`: the app matches on it.
    MODE_FIELDS = ('label', 'icon', 'tagline', 'free_delivery_at')

    @http.route('/369mart/admin/home/pages/<int:page_id>/modes/<string:mode_key>',
                **_PATCH)
    def update_mode(self, page_id, mode_key, **kwargs):
        """Rename a tab, change its icon, or change what it promises.

        The promise is the one field here that is not decoration: "in minutes"
        and "2-5 day delivery" are what the shop is telling a customer it will
        do. It is editable precisely so it can be corrected without a deploy,
        and for the same reason it is never blanked silently - an empty promise
        falls back to the app's own wording rather than showing nothing.
        """
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        if mode_key not in ('quick', 'all'):
            return self._fail('There is no such tab.', status=404)
        page = self._page(page_id)
        if not page:
            return self._fail('No such page.', status=404)
        mode = request.env['mart369.home.mode'].with_context(
            active_test=False)._get(mode_key, version=page)
        if not mode:
            return self._fail('That page has no such tab.', status=404)

        body = self._body()
        values = {}
        for field in self.MODE_FIELDS:
            if field not in body:
                continue
            if field == 'free_delivery_at':
                try:
                    values[field] = max(0.0, float(body[field] or 0))
                except (TypeError, ValueError):
                    return self._fail('That is not an amount.')
            else:
                values[field] = (body[field] or '').strip()
        if not values:
            return self._fail('Nothing to change.')
        try:
            mode.write(values)
        except (AccessError, UserError, ValueError) as exc:
            return self._fail(str(exc))
        return self._json({
            'ok': True,
            'mode': dict(mode._copy_vals(), key=mode.key,
                         free_delivery_at=mode.free_delivery_at),
        })

    @http.route('/369mart/admin/home/bands/<string:kind>/reorder', **_POST)
    def reorder_bands(self, kind, **kwargs):
        """Put one kind of band in the order the editor dragged them into.

        Writing `sequence` from the list's own position is what Odoo's
        `web_resequence` does for a handle column, and it is the only way the
        order survives a reload: the app sorts by `sequence`, not by id.
        """
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        if kind not in self.BAND_MODEL:
            return self._fail('There is no such thing to reorder.', status=404)
        ids = self._body().get('ids')
        if not isinstance(ids, list) or not ids:
            return self._fail('Nothing to reorder.')
        try:
            ids = [int(i) for i in ids]
        except (TypeError, ValueError):
            return self._fail('Nothing to reorder.')
        bands = request.env[self.BAND_MODEL[kind]].with_context(
            active_test=False).browse(ids).exists()
        if len(bands) != len(ids):
            return self._fail('Some of those are gone. Reload the page.',
                              status=409)
        # All of one tab, or the sequences written here would interleave with
        # another page's bands and reorder a page nobody opened.
        if len(bands.mapped('mode_id')) != 1:
            return self._fail('Those are not all on the same tab.', status=409)
        try:
            for step, band_id in enumerate(ids, start=1):
                bands.browse(band_id).sequence = step * 10
        except (AccessError, UserError, ValueError) as exc:
            return self._fail(str(exc))
        return self._json({'ok': True, 'ids': [str(i) for i in ids]})

    @http.route('/369mart/admin/home/bands/<string:kind>/<int:band_id>', **_PATCH)
    def update_band(self, kind, band_id, **kwargs):
        """Change one banner, tab, tile or row."""
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        band = self._band(kind, band_id)
        if band is None:
            return self._fail('There is no such thing to edit.', status=404)
        if not band:
            return self._fail('No such item.', status=404)
        body = self._body()
        values = {}
        for field in self.BAND_FIELDS[kind]:
            if field not in body:
                continue
            value = body[field]
            values[field] = bool(value) if field == 'active' else (value or '').strip()
        if not values:
            return self._fail('Nothing to change.')
        try:
            band.write(values)
        except (AccessError, UserError, ValueError) as exc:
            return self._fail(str(exc))
        return self._json({'ok': True, 'band': self._serialize_band(kind, band)})

    @http.route('/369mart/admin/home/pages/<int:page_id>', **_PATCH)
    def update_page(self, page_id, **kwargs):
        """Rename a page, or give it a window."""
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        page = self._page(page_id)
        if not page:
            return self._fail('No such page.', status=404)
        body = self._body()
        values = {}
        for key, field in (('name', 'name'), ('note', 'note')):
            if key in body:
                values[field] = (body.get(key) or '').strip()
        for key, field in (('startsOn', 'starts_on'), ('endsOn', 'ends_on')):
            if key in body:
                values[field] = body.get(key) or False
        if values.get('name') == '':
            return self._fail('A page needs a name.')
        try:
            page.write(values)
        except (AccessError, UserError, ValueError) as exc:
            return self._fail(str(exc))
        return self._json({'ok': True, 'page': self._serialize(page)})

    @http.route('/369mart/admin/home/pages/<int:page_id>/current', **_POST)
    def make_current(self, page_id, **kwargs):
        """Switch this page on. Turning one on turns the others off."""
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        page = self._page(page_id)
        if not page:
            return self._fail('No such page.', status=404)
        try:
            page.action_mart369_make_current()
        except (AccessError, UserError) as exc:
            return self._fail(str(exc))
        pages = self._pages().search([])
        return self._json({
            'ok': True,
            'pages': [self._serialize(p) for p in pages],
        })

    @http.route('/369mart/admin/home/pages/<int:page_id>', **_DELETE)
    def delete_page(self, page_id, **kwargs):
        """Remove a saved page. The model refuses the live one and the last."""
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        page = self._page(page_id)
        if not page:
            return self._fail('No such page.', status=404)
        try:
            page.unlink()
        except (AccessError, UserError) as exc:
            # The model's own words - it knows why better than this does.
            return self._fail(str(exc), status=409)
        return self._json({'ok': True})
