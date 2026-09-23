"""The staff side of coupons.

Three things are worth pinning here, and they are the three that would not
announce themselves when they break.

**Who may look.** These routes have no per-shopper fence - that is the point
of them - so the group check is the only thing between a shopper and every
code, its cap and how much of it is left. It is checked on every route, and a
shopper is refused rather than handed an empty list.

**What the shopper payload carries.** The cart sends every live coupon to
every customer who opens it. `used_count`, the caps and the per-customer limit
are staff numbers; if they ever turn up in `_mart369_serialize`, a shopper can
read how close a code is to running out and race for it.

**What the console may write.** `used_count` belongs to the order flow - up
when a payment lands, down when an order is cancelled. A form that could write
it could hand a spent code back to everybody.
"""

import json

from odoo.tests import tagged
from odoo.tests.common import HttpCase

HEADERS = {'Content-Type': 'application/json'}


@tagged('post_install', '-at_install')
class TestAdminCoupons(HttpCase):

    def setUp(self):
        super().setUp()
        self.Coupon = self.env['mart369.coupon'].with_context(active_test=False)
        self.coupon = self.Coupon.create({
            'code': 'ADMINTEST',
            'title': 'Ten off',
            'kind': 'flat',
            'value': 10.0,
        })
        self.shopper = self.env['res.users'].sudo().create({
            'name': 'A Shopper',
            'login': 'mart369_coupon_shopper',
            'password': 'mart369_coupon_shopper',
            'group_ids': [(6, 0, [self.env.ref('base.group_portal').id])],
        })

    # ------------------------------------------------------------- acting

    def _get(self, path):
        return self.url_open(path)

    def _send(self, method, path, payload=None):
        return self.url_open(
            path, data=json.dumps(payload or {}), headers=HEADERS, method=method)

    def _staff(self):
        self.authenticate('admin', 'admin')

    # ------------------------------------------------------------- the lock

    def test_a_shopper_is_refused_every_admin_route(self):
        """Refused, not filtered. A shopper must not learn this exists."""
        self.authenticate('mart369_coupon_shopper', 'mart369_coupon_shopper')
        for response in (
            self._get('/369mart/admin/coupons'),
            self._send('POST', '/369mart/admin/coupons',
                       {'code': 'SNEAK', 'title': 'Mine'}),
            self._send('PATCH', '/369mart/admin/coupons/%s' % self.coupon.id,
                       {'active': False}),
            self._send('DELETE', '/369mart/admin/coupons/%s' % self.coupon.id),
        ):
            self.assertEqual(response.status_code, 403)
        self.assertTrue(self.coupon.active, 'and nothing moved')

    # ------------------------------------------------------- the two shapes

    def test_the_shopper_payload_keeps_the_staff_numbers_out(self):
        """The one that would leak quietly."""
        shopper_side = set(self.coupon._mart369_serialize())
        for secret in ('usedCount', 'used_count', 'limitTotal', 'limit_total',
                       'limitPerCustomer', 'maxOff', 'active'):
            self.assertNotIn(secret, shopper_side)

    def test_the_staff_payload_carries_what_the_screen_draws(self):
        row = self.coupon._mart369_admin_serialize()
        for key in ('id', 'code', 'title', 'kind', 'value', 'minSpend',
                    'active', 'limitTotal', 'usedCount', 'live'):
            self.assertIn(key, row)

    def test_switched_on_is_not_the_same_as_usable(self):
        """A code can be on and spent, and the screen has to say which."""
        self.coupon.write({'limit_total': 2, 'used_count': 2})
        row = self.coupon._mart369_admin_serialize()
        self.assertTrue(row['active'])
        self.assertFalse(row['live'])

    # -------------------------------------------------------------- reading

    def test_the_list_includes_the_switched_off_ones(self):
        """A paused coupon is exactly what somebody opened the screen to
        find, so `active_test` must be off."""
        self.coupon.active = False
        self._staff()
        body = self._get('/369mart/admin/coupons').json()
        self.assertTrue(body['ok'])
        codes = [c['code'] for c in body['coupons']]
        self.assertIn('ADMINTEST', codes)
        self.assertGreaterEqual(body['counts']['paused'], 1)

    def test_nearly_used_up_counts_the_ones_about_to_refuse_people(self):
        before = self._counts()['nearlyUsedUp']
        self.coupon.write({'limit_total': 10, 'used_count': 9})
        self.assertEqual(self._counts()['nearlyUsedUp'], before + 1)

    def _counts(self):
        return self.Coupon.mart369_admin_list()['counts']

    # -------------------------------------------------------------- writing

    def test_a_code_is_created_and_comes_back_upper_cased(self):
        self._staff()
        response = self._send('POST', '/369mart/admin/coupons', {
            'code': ' newyear ', 'title': 'New year', 'kind': 'percent',
            'value': 15, 'max_off': 100,
        })
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['coupon']['code'], 'NEWYEAR')

    def test_a_code_without_a_title_is_refused_and_says_which_field(self):
        """The screen puts the message under the control the server named."""
        self._staff()
        response = self._send('POST', '/369mart/admin/coupons', {'code': 'NOTITLE'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['field'], 'title')

    def test_a_window_that_ends_before_it_starts_is_refused(self):
        self._staff()
        response = self._send('PATCH', '/369mart/admin/coupons/%s' % self.coupon.id,
                              {'starts_on': '2026-10-10', 'ends_on': '2026-10-01'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['field'], 'ends_on')

    def test_a_duplicate_code_is_refused_with_a_sentence(self):
        """Not the database's integrity error. The unique index fires after
        the handler returns unless the write is flushed inside it, so an
        operator would otherwise get a raw 422 and no idea what to change."""
        self._staff()
        response = self._send('POST', '/369mart/admin/coupons',
                              {'code': 'admintest', 'title': 'Again'})
        self.assertEqual(response.status_code, 409)
        body = response.json()
        self.assertEqual(body['field'], 'code')
        self.assertIn('ADMINTEST', body['error'])

    def test_renaming_a_code_onto_another_one_is_refused(self):
        other = self.Coupon.create({'code': 'OTHERONE', 'title': 'Other', 'value': 5.0})
        self._staff()
        response = self._send('PATCH', '/369mart/admin/coupons/%s' % other.id,
                              {'code': 'ADMINTEST'})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(other.code, 'OTHERONE')

    def test_pausing_a_code_is_one_patch(self):
        self._staff()
        response = self._send('PATCH', '/369mart/admin/coupons/%s' % self.coupon.id,
                              {'active': False})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['coupon']['active'])

    def test_the_console_cannot_write_how_often_a_code_has_been_used(self):
        """It belongs to the order flow. Writing it here would hand a spent
        code back to everybody."""
        self.coupon.used_count = 7
        self._staff()
        self._send('PATCH', '/369mart/admin/coupons/%s' % self.coupon.id,
                   {'used_count': 0, 'usedCount': 0, 'title': 'Still ten off'})
        self.coupon.invalidate_recordset()
        self.assertEqual(self.coupon.used_count, 7)
        self.assertEqual(self.coupon.title, 'Still ten off',
                         'and the fields it may write still went through')

    def test_a_made_up_coupon_is_a_404(self):
        self._staff()
        self.assertEqual(
            self._send('PATCH', '/369mart/admin/coupons/99999', {'active': False})
            .status_code, 404)

    # ------------------------------------------------- refused means undone

    def test_a_refused_percentage_is_not_saved_anyway(self):
        """The whole point of the savepoint.

        The model refuses a percentage over 100 on flush - which is *after*
        `write` has already put it in the transaction. Catching that and
        answering 400 is only half an answer: without a savepoint to roll back
        to, the operator is told no and the nonsense value is committed
        regardless, so the next person to open the screen sees 150% and the
        cart starts honouring it.
        """
        self.coupon.write({'kind': 'percent', 'value': 10.0})
        self._staff()
        response = self._send(
            'PATCH', '/369mart/admin/coupons/%s' % self.coupon.id, {'value': 150.0})

        self.assertEqual(response.status_code, 400)
        self.assertIn('between 0 and 100', response.json()['error'])
        self.coupon.invalidate_recordset()
        self.assertEqual(self.coupon.value, 10.0)

    def test_a_refused_new_coupon_leaves_nothing_behind(self):
        """Same on create: the row exists in the transaction before the
        constraint speaks, so a refusal has to take it away again."""
        self._staff()
        response = self._send('POST', '/369mart/admin/coupons', {
            'code': 'HALFOFF', 'title': 'Too much', 'kind': 'percent', 'value': 900.0,
        })

        self.assertEqual(response.status_code, 400)
        self.assertFalse(self.Coupon.search([('code', '=', 'HALFOFF')]))

    def test_the_transaction_still_works_after_a_refusal(self):
        """A rolled-back write must leave the cursor usable.

        Before the savepoint the failed flush poisoned the transaction, so the
        *next* statement - even building the error response - came back
        'current transaction is aborted'. A refusal and then an ordinary save
        is the sequence an operator actually performs: get it wrong, fix it,
        save.
        """
        self.coupon.write({'kind': 'percent', 'value': 10.0})
        self._staff()
        self._send('PATCH', '/369mart/admin/coupons/%s' % self.coupon.id,
                   {'value': 150.0})

        good = self._send('PATCH', '/369mart/admin/coupons/%s' % self.coupon.id,
                          {'value': 25.0})
        self.assertEqual(good.status_code, 200)
        self.coupon.invalidate_recordset()
        self.assertEqual(self.coupon.value, 25.0)

    # ------------------------------------------------------------- deleting

    def test_an_unused_code_can_be_deleted(self):
        self._staff()
        response = self._send('DELETE', '/369mart/admin/coupons/%s' % self.coupon.id)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.coupon.exists())

    def test_a_code_somebody_has_used_is_kept(self):
        """It belongs to the orders that used it now. The honest answer is to
        switch it off, and the message says so."""
        self.coupon.used_count = 3
        self._staff()
        response = self._send('DELETE', '/369mart/admin/coupons/%s' % self.coupon.id)
        self.assertEqual(response.status_code, 409)
        self.assertIn('Switch it off', response.json()['error'])
        self.assertTrue(self.coupon.exists())
