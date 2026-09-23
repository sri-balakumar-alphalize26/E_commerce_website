"""The staff side of searches, over HTTP.

Three things are worth pinning here, and none would announce itself.

**Who may look.** These routes have no per-shopper fence - that is the point of
them - so the group check is the only thing between a shopper and the shop's
whole demand list. A shopper is refused rather than handed an empty list.

**What the screen may write.** A term, its hit count, how many results it found
and when are counts of things that really happened. Only `trending` can be
written, and a request carrying anything else must change nothing - otherwise
the catalogue's own gaps can be typed over.

**The tiles count everything.** They are the tabs; if they counted the filtered
rows instead, "Found nothing 7" would drop to 0 the moment somebody searched,
and stop being the reason to open the screen.
"""

import json

from odoo.tests import tagged
from odoo.tests.common import HttpCase

HEADERS = {'Content-Type': 'application/json'}

LIST = '/369mart/admin/searches'


@tagged('post_install', '-at_install')
class TestAdminSearches(HttpCase):

    def setUp(self):
        super().setUp()
        Term = self.env['mart369.search.term'].sudo()
        self.found = Term.create({
            'term': 'test term that found things', 'hits': 11, 'results': 4})
        self.empty = Term.create({
            'term': 'test term that found nothing', 'hits': 6, 'results': 0})
        self.blocked = Term.create({
            'term': 'test term nobody should see', 'hits': 2, 'results': 3,
            'trending': False})

        self.shopper = self.env['res.users'].sudo().create({
            'name': 'Search Shopper',
            'login': 'mart369_search_shopper',
            'password': 'mart369_search_shopper',
            'group_ids': [(6, 0, [self.env.ref('base.group_portal').id])],
        })

    def _send(self, method, path, payload=None):
        return self.url_open(
            path, data=json.dumps(payload or {}), headers=HEADERS, method=method)

    def _rows(self, **params):
        query = '&'.join('%s=%s' % kv for kv in params.items())
        res = self.url_open(LIST + ('?%s' % query if query else ''))
        return res.status_code, res.json()

    def _terms_in(self, payload):
        return [r['term'] for r in payload['rows']]

    # ---------------------------------------------------------------- the lock

    def test_a_shopper_is_refused_every_admin_route(self):
        """Refused, not filtered. A shopper must not learn this exists."""
        self.authenticate('mart369_search_shopper', 'mart369_search_shopper')
        for res in (self.url_open(LIST),
                    self._send('PATCH', '%s/%s' % (LIST, self.found.id),
                               {'trending': False})):
            self.assertEqual(res.status_code, 403)
            self.assertFalse(res.json().get('ok'))

    def test_a_shopper_cannot_hide_a_term(self):
        self.authenticate('mart369_search_shopper', 'mart369_search_shopper')
        self._send('PATCH', '%s/%s' % (LIST, self.found.id), {'trending': False})
        self.found.invalidate_recordset()
        self.assertTrue(self.found.trending)

    # -------------------------------------------------------------- the screen

    def test_each_tab_is_a_domain_not_a_suggestion(self):
        self.authenticate('admin', 'admin')

        status, empty = self._rows(tab='empty')
        self.assertEqual(status, 200)
        self.assertTrue(empty['ok'])
        self.assertTrue(all(r['results'] == 0 for r in empty['rows']))
        self.assertIn(self.empty.term, self._terms_in(empty))
        self.assertNotIn(self.found.term, self._terms_in(empty))

        __, blocked = self._rows(tab='blocked')
        self.assertTrue(all(r['trending'] is False for r in blocked['rows']))
        self.assertIn(self.blocked.term, self._terms_in(blocked))

    def test_an_unknown_tab_falls_back_to_all_rather_than_failing(self):
        """A stale bookmark should show the screen, not an error."""
        self.authenticate('admin', 'admin')
        status, payload = self._rows(tab='nonsense')
        self.assertEqual(status, 200)
        self.assertIn(self.found.term, self._terms_in(payload))

    def test_search_matches_the_term(self):
        self.authenticate('admin', 'admin')
        __, payload = self._rows(q='found nothing')
        self.assertEqual(self._terms_in(payload), [self.empty.term])

    def test_the_tiles_count_everything_not_the_filtered_rows(self):
        """The tiles are the tabs. If they moved with the search box, the one
        number worth opening this screen for would vanish when used."""
        self.authenticate('admin', 'admin')
        __, everything = self._rows()
        __, searched = self._rows(q='found nothing')
        self.assertEqual(len(searched['rows']), 1)
        self.assertEqual(searched['tiles'], everything['tiles'])
        self.assertEqual(searched['counts'], everything['counts'])

    def test_the_gap_is_counted_in_searches_as_well_as_terms(self):
        """Six people asking once is the same gap as one asking six times, and
        the screen says both numbers because they answer different questions."""
        self.authenticate('admin', 'admin')
        __, payload = self._rows()
        tiles = payload['tiles']
        self.assertGreaterEqual(tiles['empty'], 1)
        self.assertGreaterEqual(tiles['empty_searches'], self.empty.hits)
        self.assertGreaterEqual(tiles['searches'], tiles['terms'])

    # --------------------------------------------------------------- the write

    def test_staff_can_stop_and_restart_suggesting_a_term(self):
        self.authenticate('admin', 'admin')

        res = self._send('PATCH', '%s/%s' % (LIST, self.found.id),
                         {'trending': False})
        self.assertEqual(res.status_code, 200, res.text)
        self.found.invalidate_recordset()
        self.assertFalse(self.found.trending)
        self.assertNotIn(self.found.term,
                         self.env['mart369.search.term']._mart369_trending(limit=50))

        res = self._send('PATCH', '%s/%s' % (LIST, self.found.id),
                         {'trending': True})
        self.assertEqual(res.status_code, 200, res.text)
        self.found.invalidate_recordset()
        self.assertTrue(self.found.trending)

    def test_hiding_a_term_does_not_stop_it_being_counted(self):
        """The point of the switch: keep counting it, never suggest it."""
        self.authenticate('admin', 'admin')
        self._send('PATCH', '%s/%s' % (LIST, self.found.id), {'trending': False})
        before = self.found.hits
        self.env['mart369.search.term']._mart369_record(self.found.term, 4)
        self.found.invalidate_recordset()
        self.assertEqual(self.found.hits, before + 1)
        self.assertFalse(self.found.trending)

    def test_the_write_is_allow_listed_to_trending(self):
        """A request carrying counts must change none of them."""
        self.authenticate('admin', 'admin')
        res = self._send('PATCH', '%s/%s' % (LIST, self.empty.id), {
            'trending': True,
            'term': 'typed over',
            'hits': 9999,
            'results': 50,
        })
        self.assertEqual(res.status_code, 200, res.text)
        self.empty.invalidate_recordset()
        self.assertEqual(self.empty.term, 'test term that found nothing')
        self.assertEqual(self.empty.hits, 6)
        self.assertEqual(self.empty.results, 0)

    def test_trending_has_to_be_a_yes_or_no(self):
        self.authenticate('admin', 'admin')
        for bad in ('yes', 1, None):
            res = self._send('PATCH', '%s/%s' % (LIST, self.found.id),
                             {'trending': bad})
            self.assertEqual(res.status_code, 400, res.text)
        self.found.invalidate_recordset()
        self.assertTrue(self.found.trending)

    def test_a_term_that_is_gone_is_a_404(self):
        self.authenticate('admin', 'admin')
        missing = self.empty.id
        self.empty.unlink()
        res = self._send('PATCH', '%s/%s' % (LIST, missing), {'trending': False})
        self.assertEqual(res.status_code, 404)

    # ----------------------------------------------------------- the demo data

    def test_the_demo_never_runs_on_a_shop_with_searches(self):
        """setUp has already counted three terms, so this stands in for any
        shop with traffic: examples must never be mixed into a real demand
        list."""
        self.assertFalse(self.env['mart369.search.term']._mart369_load_demo())
