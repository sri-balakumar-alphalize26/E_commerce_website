"""The rest of the Reviews desk, for the app's own admin console.

The Odoo desk moderates through three model methods on rating.rating -
publish or hide with a reason, reply, approve or remove a photo - and the
console had no way to reach them: its only write was `PATCH {state}`, which
hides without a reason and publishes without clearing why a review was held.
These routes call those same methods, so both screens obey one set of rules.

Same lock as every admin route: the group is checked first, and a shopper is
refused, not filtered.
"""

from odoo import http
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import request

from .admin_api import _POST, Mart369ReviewAdminApi


class Mart369ReviewConsoleApi(Mart369ReviewAdminApi):

    def _answer(self, fn):
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        try:
            with request.env.cr.savepoint():
                review = fn(request.env['rating.rating'], self._body())
        except AccessError as exc:
            return self._fail(str(exc), status=403)
        except (UserError, ValidationError) as exc:
            return self._fail(str(exc))
        return self._json({'ok': True, 'review': review})

    @http.route('/369mart/admin/reviews/<int:rating_id>/moderate', **_POST)
    def moderate(self, rating_id, **kwargs):
        """Publish (clears why it was held or hidden), or hide - with a reason."""
        return self._answer(lambda R, b: R.mart369_admin_moderate(
            rating_id, b.get('state'), b.get('reason')))

    @http.route('/369mart/admin/reviews/<int:rating_id>/reply', **_POST)
    def reply(self, rating_id, **kwargs):
        """The shop's public reply under the review. Empty text removes it."""
        return self._answer(lambda R, b: R.mart369_admin_reply(rating_id, b.get('text') or ''))

    @http.route('/369mart/admin/reviews/media/<int:media_id>', **_POST)
    def media(self, media_id, **kwargs):
        """Approve a photo or video so shoppers see it, or remove it (and its file)."""
        return self._answer(lambda R, b: R.mart369_admin_media(media_id, b.get('action')))
