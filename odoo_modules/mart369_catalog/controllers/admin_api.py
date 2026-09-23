"""The staff side of searches, for the app's own admin console.

The first admin controller in this module, and it follows the same two rules
as every other one in the suite, for the same reason. Every other route under
/369mart answers "this shopper's own things" and is fenced by the signed-in
partner; nothing here has that fence, so:

* **The group is checked on every route**, first, and somebody who is not
  staff is refused rather than handed an empty list.
* **Nothing is sudo'd.** Records are read and written as the person signed in,
  so Odoo's own access rules do their job rather than being re-implemented
  here badly. The designer group's write on `mart369.search.term` is granted
  in security/ir.model.access.csv, which is why no route here needs to lift
  itself.

There is exactly one thing this controller can write: `trending`. What a term
is, how often it was searched for, how many results it found and when - those
are counts of things that really happened, and a screen that could edit them
could make the catalogue's own gaps disappear by typing over them. The
allow-list is what enforces that rather than a promise in a docstring.
"""

import logging

from odoo import http
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import request

_logger = logging.getLogger(__name__)

_GET = {'type': 'http', 'auth': 'user', 'methods': ['GET'],
        'csrf': False, 'sitemap': False}
_PATCH = {'type': 'http', 'auth': 'user', 'methods': ['PATCH'],
          'csrf': False, 'sitemap': False}

EDITOR_GROUP = 'website.group_website_designer'


class Mart369SearchAdminApi(http.Controller):

    # --------------------------------------------------------------- helpers

    def _json(self, payload, status=200):
        return request.make_json_response(payload, status=status)

    def _fail(self, error, field=None, status=400):
        payload = {'ok': False, 'error': error}
        if field:
            payload['field'] = field
        return self._json(payload, status=status)

    def _body(self):
        try:
            data = request.get_json_data()
        except Exception:  # noqa: BLE001
            data = None
        return data if isinstance(data, dict) else {}

    def _may_edit(self):
        """Refused, not filtered. A shopper must not learn this exists."""
        return request.env.user.has_group(EDITOR_GROUP)

    def _terms(self):
        """Not sudo'd - on purpose. See the module docstring."""
        return request.env['mart369.search.term']

    # ---------------------------------------------------------------- routes

    @http.route('/369mart/admin/searches', **_GET)
    def searches(self, tab='all', q='', **kwargs):
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        if tab not in self._terms().ADMIN_TABS:
            tab = 'all'
        try:
            payload = self._terms().mart369_admin_list(tab=tab, q=q)
        except AccessError as exc:
            return self._fail(str(exc), status=403)
        payload['ok'] = True
        return self._json(payload)

    @http.route('/369mart/admin/searches/<int:term_id>', **_PATCH)
    def set_trending(self, term_id, **kwargs):
        """Allow or stop one term as a shopper-facing suggestion.

        The only write in this file. It changes nothing about what was
        searched for - the term keeps being counted either way.
        """
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)

        term = self._terms().browse(term_id).exists()
        if not term:
            return self._fail('That search term no longer exists.', status=404)

        trending = self._body().get('trending')
        if not isinstance(trending, bool):
            return self._fail(
                'A term is either allowed in Trending or it is not.',
                field='trending')

        try:
            row = term.mart369_admin_set_trending(trending)
        except AccessError as exc:
            return self._fail(str(exc), status=403)
        except (UserError, ValidationError) as exc:
            return self._fail(str(exc))

        _logger.info('369 Mart: search term %s trending=%s by %s',
                     term.term, trending, request.env.user.login)
        return self._json({'ok': True, 'term': row})
