"""The staff side of reviews, for the app's own admin console.

Same two rules as every other admin controller in the suite, for the same
reason. Every other route under /369mart answers "this shopper's own things"
and is fenced by the signed-in partner; nothing here has that fence, so:

* **The group is checked on every route**, first, and somebody who is not
  staff is refused rather than handed an empty list.
* **Nothing is sudo'd.** Records are read and written as the person signed in,
  so Odoo's own access rules do their job rather than being re-implemented
  here badly.

There is exactly one thing this controller can write: `mart369_state`. Staff
moderate a review - they decide whether the shop shows it - and they do not
edit it. A customer's words stay the customer's, so no route here can change
the stars, the headline or the text, and the allow-list is what enforces that
rather than a promise in a docstring.
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
_POST = {'type': 'http', 'auth': 'user', 'methods': ['POST'],
         'csrf': False, 'sitemap': False}

EDITOR_GROUP = 'website.group_website_designer'

STATES = ('pending', 'published', 'hidden')


class Mart369ReviewAdminApi(http.Controller):

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

    def _ratings(self):
        """Not sudo'd - on purpose. See the module docstring."""
        return request.env['rating.rating']

    def _rating(self, rating_id):
        try:
            return self._ratings().browse(int(rating_id)).exists()
        except (TypeError, ValueError):
            return self._ratings()

    # ---------------------------------------------------------------- routes

    def _flag(self, raw):
        """A query string carries text, and the model wants a tri-state.

        Absent or empty means "do not care" and must stay None - `bool('0')`
        is True, so reading these as plain truthy values would turn "only the
        unverified ones" into "only the verified ones".
        """
        if raw is None:
            return None
        text = str(raw).strip().lower()
        if not text:
            return None
        return text not in ('0', 'false', 'no')

    @http.route('/369mart/admin/reviews', **_GET)
    def reviews(self, state=None, q=None, verified=None, photos=None, **kwargs):
        """Every product review, and the numbers above them."""
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        try:
            payload = self._ratings().mart369_admin_list(
                state=state, q=q,
                verified=self._flag(verified), photos=self._flag(photos))
        except AccessError as exc:
            return self._fail(str(exc), status=403)
        payload['ok'] = True
        return self._json(payload)

    @http.route('/369mart/admin/reviews/counts', **_GET)
    def counts(self, **kwargs):
        """The three tallies alone, for the sidebar badge.

        Declared before the `<int:rating_id>` route below so 'counts' is never
        read as an id.
        """
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        try:
            counts = self._ratings().mart369_admin_counts()
        except AccessError as exc:
            return self._fail(str(exc), status=403)
        return self._json({'ok': True, 'counts': counts})

    @http.route('/369mart/admin/reviews/<int:rating_id>', **_PATCH)
    def set_state(self, rating_id, **kwargs):
        """Publish or hide one review. The only write in this file."""
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)

        rating = self._rating(rating_id)
        if not rating:
            return self._fail('That review no longer exists.', status=404)

        state = self._body().get('state')
        if state not in STATES:
            return self._fail(
                'A review can only be waiting, published or hidden.',
                field='state')

        # An order or rider rating is not a product review and has no moderation
        # of its own; letting this route touch one would write a state nothing
        # reads and imply a power that does not exist.
        if rating.res_model != 'product.template':
            return self._fail('That is not a product review.', status=404)

        try:
            rating.write({'mart369_state': state})
        except AccessError as exc:
            return self._fail(str(exc), status=403)
        except (UserError, ValidationError) as exc:
            return self._fail(str(exc))

        _logger.info('369 Mart: review %s set to %s by %s',
                     rating.id, state, request.env.user.login)
        return self._json({
            'ok': True,
            'review': rating._mart369_admin_serialize(),
        })


class Mart369ReferralAdminApi(Mart369ReviewAdminApi):
    """Referrals, for the same console and under the same two rules.

    A subclass so the helpers, the group and the refusal wording are literally
    the same ones - two copies of `_may_edit` is how the two screens end up
    fenced by different groups without anybody noticing.

    Everything here is read-only bar one write, and that write is the single
    deliberate sudo in the suite. See `reward` below.
    """

    def _referrals(self):
        """Not sudo'd - on purpose, like the reviews above."""
        return request.env['mart369.referral']

    @http.route('/369mart/admin/referrals', **_GET)
    def referrals(self, state='all', q='', **kwargs):
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        if state not in self._referrals().ADMIN_TABS:
            state = 'all'
        try:
            payload = self._referrals().mart369_admin_list(state=state, q=q)
        except AccessError as exc:
            return self._fail(str(exc), status=403)
        payload['ok'] = True
        return self._json(payload)

    @http.route('/369mart/admin/referrals/reward', **_PATCH)
    def reward(self, **kwargs):
        """Set what one successful referral pays.

        The write itself is `mart369_admin_set_reward` on the model, not here,
        because the backend desk sets the same number and two copies of a
        setting write is how the two screens end up disagreeing. The one sudo
        it needs, and why, is documented there.
        """
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)

        raw = self._body().get('reward')
        try:
            tiles = self._referrals().mart369_admin_set_reward(raw)
        except AccessError as exc:
            return self._fail(str(exc), status=403)
        except (UserError, ValidationError) as exc:
            return self._fail(str(exc), field='reward')

        _logger.info('369 Mart: referral reward set to %s by %s',
                     raw, request.env.user.login)
        return self._json({'ok': True, 'tiles': tiles})


class Mart369RewardAdminApi(Mart369ReviewAdminApi):
    """The staff side of rewards.

    Subclassed for the helpers and the group check only, the same way the
    referral routes above are.

    **Read only, and deliberately so.** A scratch card is money - scratching
    one credits the 369 Wallet out of the shop's pocket - so there is no route
    here that mints, edits or voids one. The decision is enforced by there
    being nothing to call, rather than by a check somebody can loosen later.
    """

    def _cards(self):
        """Not sudo'd - on purpose. See the module docstring."""
        return request.env['mart369.scratch']

    @http.route('/369mart/admin/rewards', **_GET)
    def rewards(self, tab=None, q=None, limit=None, **kwargs):
        """The cards, and the numbers above them."""
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        try:
            payload = self._cards().mart369_admin_list(
                tab=tab, q=q, limit=int(limit or 30))
        except AccessError as exc:
            return self._fail(str(exc), status=403)
        except (TypeError, ValueError):
            return self._fail('That is not a number we can use.', field='limit')
        payload['ok'] = True
        return self._json(payload)

    @http.route('/369mart/admin/rewards/counts', **_GET)
    def reward_counts(self, **kwargs):
        """The tallies alone, for the sidebar badge."""
        if not self._may_edit():
            return self._fail('You do not have access to this.', status=403)
        try:
            payload = self._cards().mart369_admin_counts()
        except AccessError as exc:
            return self._fail(str(exc), status=403)
        payload['ok'] = True
        return self._json(payload)
