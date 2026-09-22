"""The staff side of support, for the app's own admin console.

Same two rules as every other admin controller in the suite, for the same
reason. The five routes in support_api.py answer "this shopper's own
conversation" and are fenced by the signed-in partner; nothing here has that
fence, so:

* **The group is checked on every route**, first, and somebody who is not staff
  is refused rather than handed an empty list. A support queue carries other
  customers' names, their order numbers and what they complained about.
* **Nothing is sudo'd.** Records are read and written as the person signed in,
  so Odoo's own access rules do their job rather than being re-implemented here
  badly.

What a ticket can do next is not decided here. `mart369_admin_advance` maps the
action the server itself put in `next` onto the model's own
`mart369_action_take/_done/_drop/_wait`, and this controller moves JSON and
nothing else - a second copy of the ladder is a second thing to get wrong.
"""

import logging

from odoo import http
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import request

_logger = logging.getLogger(__name__)

_GET = {'type': 'http', 'auth': 'user', 'methods': ['GET'],
        'csrf': False, 'sitemap': False}
_POST = {'type': 'http', 'auth': 'user', 'methods': ['POST'],
         'csrf': False, 'sitemap': False}
_PATCH = {'type': 'http', 'auth': 'user', 'methods': ['PATCH'],
          'csrf': False, 'sitemap': False}

EDITOR_GROUP = 'website.group_website_designer'

# What a PATCH may set. Staff move a ticket along and decide who owns it; they
# do not edit what the customer asked or when they asked it.
WRITABLE = ('state', 'assignee')


class Mart369SupportAdminApi(http.Controller):

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

    def _tickets(self):
        """Not sudo'd - on purpose. See the module docstring."""
        return request.env['mart369.ticket']

    def _flag(self, raw):
        """A query string carries text, and "0" is a true string."""
        if raw is None:
            return None
        text = str(raw).strip().lower()
        if not text:
            return None
        return text not in ('0', 'false', 'no')

    # ---------------------------------------------------------------- routes

    @http.route('/369mart/admin/support', **_GET)
    def tickets(self, tab=None, q=None, mine=None, assignee=None, sort=None,
                limit=None, **kwargs):
        """The queue, the tiles, and who a ticket can be handed to."""
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        try:
            payload = self._tickets().mart369_admin_list(
                tab=tab, q=q, mine=self._flag(mine), assignee=assignee,
                sort=sort, limit=int(limit or 30))
        except AccessError as exc:
            return self._fail(str(exc), status=403)
        except (TypeError, ValueError):
            return self._fail('That is not a number we can use.', field='limit')
        payload['ok'] = True
        return self._json(payload)

    @http.route('/369mart/admin/support/counts', **_GET)
    def counts(self, **kwargs):
        """The tallies alone, for the sidebar badge.

        Declared before the `<string:ref>` route below so 'counts' is never
        read as a ticket reference.
        """
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        try:
            payload = self._tickets().mart369_admin_counts()
        except AccessError as exc:
            return self._fail(str(exc), status=403)
        payload['ok'] = True
        return self._json(payload)

    @http.route('/369mart/admin/support/<string:ref>', **_GET)
    def detail(self, ref, **kwargs):
        """One ticket and its conversation."""
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        try:
            ticket = self._tickets().mart369_admin_detail(ref)
        except AccessError as exc:
            return self._fail(str(exc), status=403)
        if not ticket:
            return self._fail('That ticket no longer exists.', status=404)
        return self._json({'ok': True, 'ticket': ticket})

    @http.route('/369mart/admin/support/<string:ref>/reply', **_POST)
    def reply(self, ref, **kwargs):
        """Answer the customer.

        Returns the whole ticket back rather than just the new line: replying
        is also what claims a ticket and stamps it answered, and the screen
        must not have to work out that it did.
        """
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        try:
            ticket = self._tickets().mart369_admin_reply(
                ref, self._body().get('text'))
        except AccessError as exc:
            return self._fail(str(exc), status=403)
        except (UserError, ValidationError) as exc:
            return self._fail(str(exc), field='text')

        _logger.info('369 Mart: ticket %s answered by %s',
                     ref, request.env.user.login)
        return self._json({'ok': True, 'ticket': ticket})

    @http.route('/369mart/admin/support/<string:ref>', **_PATCH)
    def update(self, ref, **kwargs):
        """Move a ticket along, or hand it to somebody."""
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)

        body = self._body()
        unknown = [key for key in body if key not in WRITABLE]
        if unknown:
            return self._fail(
                'A ticket is moved along or handed over, not edited.',
                field=unknown[0])

        try:
            row = None
            if 'assignee' in body:
                row = self._tickets().mart369_admin_assign(ref, body['assignee'])
            if 'state' in body:
                row = self._tickets().mart369_admin_advance(ref, body['state'])
        except AccessError as exc:
            return self._fail(str(exc), status=403)
        except (UserError, ValidationError) as exc:
            return self._fail(str(exc))

        if row is None:
            return self._fail('Nothing to change.')
        return self._json({'ok': True, 'ticket': row})
