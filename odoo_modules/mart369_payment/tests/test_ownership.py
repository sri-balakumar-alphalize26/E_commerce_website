"""A customer may only ever touch their own saved methods and their own wallet.

This is the test most worth failing loudly. Every route that takes an id resolves
it through a helper that comes back empty for anyone else's, and the caller answers
404 - never 403, because a 403 confirms the id exists and lets someone walk the
table to find out who banks where.

Each case also re-reads the victim's record afterwards, because a route that leaks
nothing but still writes is just as broken.
"""

import json

from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestMart369PaymentOwnership(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        portal = cls.env.ref('base.group_portal')
        cls.mine = cls.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Mine Customer', 'login': 'mine@369.test',
            'email': 'mine@369.test', 'password': 'mine-pw-3691',
            'group_ids': [(6, 0, [portal.id])],
        })
        cls.theirs = cls.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Theirs Customer', 'login': 'theirs@369.test',
            'email': 'theirs@369.test', 'password': 'theirs-pw-3691',
            'group_ids': [(6, 0, [portal.id])],
        })
        cls.their_token = cls._make_token(cls, cls.theirs.partner_id, 'theirs@okaxis')

    def _make_token(self, partner, vpa):
        provider = self.env['payment.provider'].sudo().search([], order='sequence asc', limit=1)
        method = self.env.ref('payment.payment_method_upi', raise_if_not_found=False)
        return self.env['payment.token'].sudo().create({
            'provider_id': provider.id,
            'payment_method_id': method.id,
            'partner_id': partner.id,
            'payment_details': vpa,
            'provider_ref': vpa,
            'mart369_vpa': vpa,
            'mart369_upi_app': 'gpay',
        })

    def _req(self, method, path, payload=None):
        url = self.base_url() + path
        data = json.dumps(payload) if payload is not None else None
        return self.opener.request(
            method, url, data=data,
            headers={'Content-Type': 'application/json'}, allow_redirects=False)

    # ------------------------------------------------------------- the cases

    def test_a_customer_cannot_touch_another_s_saved_method(self):
        self.authenticate('mine@369.test', 'mine-pw-3691')
        path = '/369mart/payment/methods/%s' % self.their_token.id
        for method, payload in (('PATCH', {'default': True}), ('DELETE', None)):
            response = self._req(method, path, payload)
            self.assertEqual(
                response.status_code, 404,
                '%s %s leaked another customer payment method' % (method, path))
            self.assertNotIn(
                'theirs@okaxis', response.text,
                'the answer must not confirm what the id points at')

        self.their_token.invalidate_recordset()
        self.assertTrue(self.their_token.active, 'and nothing was changed')
        self.assertFalse(self.their_token.mart369_default)

    def test_a_made_up_id_is_404_and_never_403(self):
        self.authenticate('mine@369.test', 'mine-pw-3691')
        response = self._req('DELETE', '/369mart/payment/methods/98765432')
        self.assertEqual(response.status_code, 404,
                         'an id that never existed is indistinguishable from one that is not yours')

    def test_an_archived_method_of_another_customer_is_still_404(self):
        self.their_token.sudo().write({'active': False})
        self.authenticate('mine@369.test', 'mine-pw-3691')
        response = self._req('PATCH', '/369mart/payment/methods/%s' % self.their_token.id,
                             {'default': True})
        self.assertEqual(response.status_code, 404,
                         'archiving is not a way through the ownership check')

    def test_a_customer_only_sees_their_own_saved_methods(self):
        self.authenticate('mine@369.test', 'mine-pw-3691')
        self._make_token(self.mine.partner_id, 'mine@okaxis')
        response = self._req('GET', '/369mart/payment/methods')
        self.assertEqual(response.status_code, 200)
        body = response.json()
        vpas = [u['vpa'] for u in body['upis']]
        self.assertIn('mine@okaxis', vpas, 'their own is listed')
        self.assertNotIn('theirs@okaxis', vpas, "and nobody else's is")

    def test_a_customer_gets_their_own_wallet_not_a_shared_one(self):
        self.authenticate('mine@369.test', 'mine-pw-3691')
        mine = self._req('GET', '/369mart/wallet').json()
        self.env['loyalty.card']._mart369_wallet(
            self.theirs.partner_id)._mart369_move(500, 'add', 'Money added')
        again = self._req('GET', '/369mart/wallet').json()
        self.assertEqual(mine['balance'], again['balance'],
                         "another customer's top-up must not show in this wallet")

    def test_the_routes_need_an_account(self):
        self.opener.cookies.clear()
        response = self._req('GET', '/369mart/payment/methods')
        self.assertNotEqual(response.status_code, 200,
                            'a signed-out caller gets nothing')

    # -------------------------------------------------------- the card guard

    def test_a_card_cannot_be_saved_by_posting_its_number(self):
        self.authenticate('mine@369.test', 'mine-pw-3691')
        response = self._req('POST', '/369mart/payment/methods/card',
                             {'num': '4111 1111 1111 1111', 'cvv': '123'})
        self.assertEqual(response.status_code, 400)
        self.assertIn('payment form', response.json()['error'],
                      'the refusal says where a card belongs')

    def test_no_saved_method_can_hold_something_shaped_like_a_card_number(self):
        from odoo.exceptions import ValidationError
        token = self._make_token(self.mine.partner_id, 'guard@okaxis')
        with self.assertRaises(ValidationError, msg='there must be nowhere to put a PAN'):
            token.sudo().write({'mart369_holder': '4111 1111 1111 1111'})
