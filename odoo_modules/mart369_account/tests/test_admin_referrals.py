"""Referrals: the path that makes one real, and the staff side of it.

Referrals looked alive before this and were not. `_mart369_on_signup` - the
hook that turns an invite into a joined one - had a passing unit test and no
caller: the signup route never read a code, so no invite could ever progress
and no reward could ever be paid. The first test here is the one that would
have caught that, because it goes through the HTTP route a real customer uses
rather than calling the hook by hand.

The rest is the same pair the reviews tests pin: who may look, and what the
console may write.
"""

import json

from odoo.tests import tagged
from odoo.tests.common import HttpCase

HEADERS = {'Content-Type': 'application/json'}

SIGNUP = '/369mart/auth/signup'
LIST = '/369mart/admin/referrals'
REWARD = '/369mart/admin/referrals/reward'


@tagged('post_install', '-at_install')
class TestAdminReferrals(HttpCase):

    def setUp(self):
        super().setUp()
        self.inviter = self.env['res.users'].sudo().create({
            'name': 'Referral Inviter',
            'login': 'mart369_ref_inviter',
            'password': 'mart369_ref_inviter',
            'email': 'mart369_ref_inviter@example.com',
            'group_ids': [(6, 0, [self.env.ref('base.group_portal').id])],
        })
        self.partner = self.inviter.partner_id
        # Allocated on first use rather than at signup, so ask for it the way
        # the storefront's referrals screen does.
        self.code = self.partner.sudo()._mart369_code()
        self.assertTrue(self.code, "an inviter needs a code to invite with")

        self.shopper = self.env['res.users'].sudo().create({
            'name': 'Referral Shopper',
            'login': 'mart369_ref_shopper',
            'password': 'mart369_ref_shopper',
            'group_ids': [(6, 0, [self.env.ref('base.group_portal').id])],
        })

    def _send(self, method, path, payload=None):
        return self.url_open(
            path, data=json.dumps(payload or {}), headers=HEADERS, method=method)

    def _signup(self, login, code=None):
        body = {
            'name': login.replace('_', ' ').title(),
            'email': '%s@example.com' % login,
            'password': 'mart369_signup_pw',
        }
        if code is not None:
            body['code'] = code
        return self._send('POST', SIGNUP, body)

    def _rows(self, **params):
        """The console's own list, as the console asks for it."""
        query = '&'.join('%s=%s' % kv for kv in params.items())
        res = self.url_open(LIST + ('?%s' % query if query else ''))
        return res.status_code, res.json()

    # ------------------------------------------- the path, end to end

    def test_signing_up_with_a_code_marks_the_invite_joined(self):
        """The whole point. Through the route, not the hook.

        The hook was already tested and already worked; what was missing was
        anybody calling it, which only a request can show.
        """
        referrals = self.env['mart369.referral'].sudo()
        before = referrals.search_count([('partner_id', '=', self.partner.id)])

        res = self._signup('mart369_ref_joiner', code=self.code)
        self.assertEqual(res.status_code, 201, res.text)

        rows = referrals.search(
            [('partner_id', '=', self.partner.id), ('state', '=', 'joined')])
        self.assertEqual(
            referrals.search_count([('partner_id', '=', self.partner.id)]),
            before + 1)
        self.assertTrue(rows, "the signup should have credited the inviter")
        joined = rows[0].joined_partner_id
        self.assertEqual(joined.mart369_referred_by_id, self.partner)

    def test_a_wrong_code_still_creates_the_account(self):
        """A typo costs the reward, never the customer.

        Somebody mistyping a friend's invite must still end up with an account
        - which is why the crediting call is guarded rather than validated.
        """
        res = self._signup('mart369_ref_typo', code='NOTACODE369')
        self.assertEqual(res.status_code, 201, res.text)
        self.assertTrue(self.env['res.users'].sudo().search(
            [('login', '=', 'mart369_ref_typo@example.com')]))

    def test_signing_up_without_a_code_changes_nothing(self):
        referrals = self.env['mart369.referral'].sudo()
        before = referrals.search_count([])
        res = self._signup('mart369_ref_plain')
        self.assertEqual(res.status_code, 201, res.text)
        self.assertEqual(referrals.search_count([]), before)

    # ---------------------------------------------------------- the lock

    def test_a_shopper_is_refused_every_admin_route(self):
        """Refused, not filtered - these rows carry customers' names."""
        self.authenticate('mart369_ref_shopper', 'mart369_ref_shopper')
        for res in (self.url_open(LIST),
                    self._send('PATCH', REWARD, {'reward': 1})):
            self.assertEqual(res.status_code, 403)
            self.assertFalse(res.json().get('ok'))

    def test_a_shopper_cannot_move_the_reward(self):
        self.authenticate('mart369_ref_shopper', 'mart369_ref_shopper')
        was = self.env['mart369.referral']._mart369_reward()
        self._send('PATCH', REWARD, {'reward': was + 555})
        self.env['ir.config_parameter'].sudo().invalidate_recordset()
        self.assertEqual(self.env['mart369.referral']._mart369_reward(), was)

    # -------------------------------------------------------- the console

    def test_the_list_filters_on_the_server(self):
        self.env['mart369.referral'].sudo().create({
            'partner_id': self.partner.id, 'name': 'Waiting Friend'})
        self.authenticate('admin', 'admin')

        status, all_rows = self._rows()
        self.assertEqual(status, 200)
        self.assertTrue(all_rows['ok'])

        status, waiting = self._rows(state='invited')
        self.assertEqual(status, 200)
        self.assertTrue(
            all(r['state'] == 'invited' for r in waiting['rows']),
            "the tab is meant to be a domain, not a suggestion")

        status, found = self._rows(q='Waiting Friend')
        self.assertEqual(
            [r['friend'] for r in found['rows']], ['Waiting Friend'])

    def test_the_tiles_carry_numbers_as_well_as_words(self):
        """The backend strip prints strings; the console does arithmetic."""
        self.authenticate('admin', 'admin')
        __, payload = self._rows()
        tiles = payload['tiles']
        self.assertIsInstance(tiles['reward_amount'], float)
        self.assertIsInstance(tiles['paid_amount'], float)

    def test_staff_can_change_what_a_referral_pays(self):
        """The one elevated write in the controller, and its fence."""
        self.authenticate('admin', 'admin')
        was = self.env['mart369.referral']._mart369_reward()
        try:
            res = self._send('PATCH', REWARD, {'reward': was + 37})
            self.assertEqual(res.status_code, 200, res.text)
            self.env['ir.config_parameter'].sudo().invalidate_recordset()
            self.assertEqual(
                self.env['mart369.referral']._mart369_reward(), was + 37)
        finally:
            self.env['ir.config_parameter'].sudo().set_param(
                'mart369_account.referral_reward', str(was))

    def test_a_reward_must_be_a_number_and_not_negative(self):
        self.authenticate('admin', 'admin')
        was = self.env['mart369.referral']._mart369_reward()
        for bad in ('lots', -5):
            res = self._send('PATCH', REWARD, {'reward': bad})
            self.assertEqual(res.status_code, 400, res.text)
        self.env['ir.config_parameter'].sudo().invalidate_recordset()
        self.assertEqual(self.env['mart369.referral']._mart369_reward(), was)
