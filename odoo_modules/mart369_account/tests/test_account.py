"""Profile, referrals, rewards, notifications and the wishlist."""

from odoo.tests import tagged

from .common import Mart369AccountCase


@tagged('post_install', '-at_install')
class TestMart369Profile(Mart369AccountCase):

    def test_a_saved_profile_survives(self):
        """`onSave` was `setUser`, so the edit was gone on reload after the UI
        had already said "Saved"."""
        ok, error = self.partner._mart369_write_profile({'name': 'Renamed Person'})
        self.assertTrue(ok, error)
        self.partner.invalidate_recordset()
        self.assertEqual(self.partner.name, 'Renamed Person')

    def test_changing_the_email_moves_the_login_with_it(self):
        """Signing up sets login to the email, so the address on the profile
        screen is how this customer signs in."""
        ok, __ = self.partner._mart369_write_profile({'email': 'renamed@369mart.test'})
        self.assertTrue(ok)
        self.assertEqual(self.customer.login, 'renamed@369mart.test')

    def test_an_email_somebody_else_uses_is_refused(self):
        ok, error = self.partner._mart369_write_profile(
            {'email': 'someone.else@369mart.test'})
        self.assertFalse(ok)
        self.assertEqual(error[1], 'email')
        self.assertEqual(self.customer.login, 'order.tester@369mart.test',
                         'and nothing moved')

    def test_an_empty_name_is_refused(self):
        ok, error = self.partner._mart369_write_profile({'name': '   '})
        self.assertFalse(ok)
        self.assertEqual(error[1], 'name')

    def test_a_bad_mobile_is_refused_the_same_way_the_address_form_does(self):
        ok, error = self.partner._mart369_write_profile({'phone': '12'})
        self.assertFalse(ok)
        self.assertEqual(error[1], 'phone')


@tagged('post_install', '-at_install')
class TestMart369Prefs(Mart369AccountCase):

    def test_prefs_are_the_flat_map_the_screen_reads(self):
        prefs = self.partner._mart369_prefs()
        self.assertEqual(set(prefs), {'orders', 'offers', 'wallet',
                                      'whatsapp', 'email', 'sms'})

    def test_order_updates_cannot_be_turned_off(self):
        """The app draws that switch locked on, so an API caller must not be
        able to do what the screen says cannot be done."""
        self.partner._mart369_write_prefs({'orders': False, 'sms': False})
        prefs = self.partner._mart369_prefs()
        self.assertTrue(prefs['orders'], 'still on')
        self.assertFalse(prefs['sms'], 'but the others really change')


@tagged('post_install', '-at_install')
class TestMart369Referrals(Mart369AccountCase):

    def test_a_code_is_allocated_once_and_stays(self):
        first = self.partner._mart369_code()
        self.assertTrue(first.endswith('369'))
        self.assertEqual(first, self.partner._mart369_code())

    def test_the_code_does_not_change_when_they_rename_themselves(self):
        """It used to be built from the name, so it changed the moment they
        edited it - after they had sent it to their friends."""
        code = self.partner._mart369_code()
        self.partner._mart369_write_profile({'name': 'Something Else Entirely'})
        self.assertEqual(self.partner._mart369_code(), code)

    def test_two_customers_get_different_codes(self):
        self.assertNotEqual(self.partner._mart369_code(),
                            self._other_customer()._mart369_code())

    def test_signing_up_with_a_code_marks_the_invite_joined(self):
        Referral = self.env['mart369.referral']
        row = Referral.sudo().create({'partner_id': self.partner.id, 'name': 'A Friend'})
        code = self.partner._mart369_code()

        Referral._mart369_on_signup(self._other_customer(), code)
        self.assertEqual(row.state, 'joined')
        self.assertEqual(row.joined_partner_id, self._other_customer())

    def test_your_own_code_does_nothing_for_you(self):
        Referral = self.env['mart369.referral']
        code = self.partner._mart369_code()
        self.assertFalse(Referral._mart369_on_signup(self.partner, code))

    def test_a_first_order_pays_the_inviter(self):
        Referral = self.env['mart369.referral']
        Referral.sudo().create({'partner_id': self.partner.id, 'name': 'A Friend'})
        Referral._mart369_on_signup(self._other_customer(), self.partner._mart369_code())

        wallet = self.env['loyalty.card'].sudo()._mart369_wallet(self.partner)
        before = wallet._mart369_balance()

        order = self._place(ref='369M-REF1')
        order.sudo().write({'partner_id': self._other_customer().id})
        self._pay(order)

        row = Referral.sudo().search([('joined_partner_id', '=', self._other_customer().id)])
        self.assertEqual(row.state, 'ordered')
        self.assertGreater(wallet._mart369_balance(), before, 'the inviter was paid')


@tagged('post_install', '-at_install')
class TestMart369Rewards(Mart369AccountCase):

    def test_a_delivered_order_mints_a_scratch_card(self):
        """Nothing ever minted one in the app, so everybody saw the same four
        seed cards forever."""
        order = self._delivered()
        card = self.env['mart369.scratch'].sudo().search([('order_id', '=', order.id)])
        self.assertEqual(len(card), 1)
        self.assertFalse(card.scratched)

    def test_an_order_only_ever_mints_one(self):
        order = self._delivered()
        self.env['mart369.scratch']._mart369_mint_for_order(order)
        self.env['mart369.scratch']._mart369_mint_for_order(order)
        self.assertEqual(self.env['mart369.scratch'].sudo().search_count(
            [('order_id', '=', order.id)]), 1)

    def test_scratching_a_cash_card_pays_the_wallet_once(self):
        order = self._delivered()
        card = self.env['mart369.scratch'].sudo().search([('order_id', '=', order.id)])
        card.sudo().write({'reward_type': 'cash', 'amount': 25.0, 'scratched': False})

        wallet = self.env['loyalty.card'].sudo()._mart369_wallet(self.partner)
        before = wallet._mart369_balance()
        card._mart369_scratch()
        after = wallet._mart369_balance()
        self.assertEqual(after - before, 25.0)

        card._mart369_scratch()
        self.assertEqual(wallet._mart369_balance(), after, 'scratching again pays nothing')

    def test_a_card_that_won_nothing_pays_nothing(self):
        order = self._delivered()
        card = self.env['mart369.scratch'].sudo().search([('order_id', '=', order.id)])
        card.sudo().write({'reward_type': 'none', 'amount': 0.0, 'scratched': False})
        wallet = self.env['loyalty.card'].sudo()._mart369_wallet(self.partner)
        before = wallet._mart369_balance()
        card._mart369_scratch()
        self.assertEqual(wallet._mart369_balance(), before)


@tagged('post_install', '-at_install')
class TestMart369Notifications(Mart369AccountCase):

    def test_an_order_makes_a_notification_the_app_recognises(self):
        """The id has to stay `n-<ref>-<status>`: it is what read state is
        keyed on, so changing it loses everyone's."""
        order = self._place()
        self._pay(order)
        feed = self.env['mart369.notifications']._mart369_for(self.partner)
        ids = [row['id'] for row in feed['notifications']]
        self.assertIn('n-%s-placed' % order.mart369_ref, ids)

    def test_reading_one_is_remembered(self):
        order = self._place()
        self._pay(order)
        note_id = 'n-%s-placed' % order.mart369_ref
        self.partner._mart369_add_ids('mart369_read_ids', [note_id])
        feed = self.env['mart369.notifications']._mart369_for(self.partner)
        row = next(r for r in feed['notifications'] if r['id'] == note_id)
        self.assertTrue(row['read'])

    def test_a_dismissed_notification_stays_gone(self):
        order = self._place()
        self._pay(order)
        note_id = 'n-%s-placed' % order.mart369_ref
        self.partner._mart369_add_ids('mart369_dismissed_ids', [note_id])
        feed = self.env['mart369.notifications']._mart369_for(self.partner)
        self.assertNotIn(note_id, [r['id'] for r in feed['notifications']])

    def test_turning_offers_off_really_hides_them(self):
        self.partner._mart369_write_prefs({'offers': False})
        feed = self.env['mart369.notifications']._mart369_for(self.partner)
        self.assertFalse([r for r in feed['notifications'] if r['type'] == 'offer'])

    def test_one_customers_orders_do_not_appear_in_anothers_feed(self):
        order = self._place()
        self._pay(order)
        feed = self.env['mart369.notifications']._mart369_for(self._other_customer())
        self.assertNotIn(order.mart369_ref,
                         ' '.join(r['id'] for r in feed['notifications']))
