"""The staff side of rewards, and three things about money.

A scratch card is money: scratching one credits the wallet out of the shop's
pocket. So the things worth pinning here are the ones that would be wrong
quietly.

**Paid before marked.** The card used to be written `scratched` and only then
paid. If the payment raised - no wallet on the account - the controller caught
the error, the card was already scratched, and the early return turned every
retry into a no-op: the customer watched their prize revealed and never got the
money. The test below forces the failure and asserts the card is still
scratchable.

**Never added across currencies.** A card keeps the currency it was minted in.
Summing the raw amounts put rupees and dollars in one total and printed it with
whatever symbol the company happened to use.

**Read-only.** There is no admin route that writes a card, and there should
never be one.

`mart369_scratch_dashboard` had no test at all before this file.
"""

import json
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import Mart369AccountCase, Mart369AccountHttpCase

HEADERS = {'Content-Type': 'application/json'}
LIST = '/369mart/admin/rewards'


@tagged('post_install', '-at_install')
class TestRewardsAdminModel(Mart369AccountCase):

    def setUp(self):
        super().setUp()
        self.Scratch = self.env['mart369.scratch']

    def _card(self, **values):
        base = {'partner_id': self.partner.id, 'origin': 'Order #369M-TEST',
                'reward_type': 'none'}
        base.update(values)
        return self.Scratch.create(base)

    # ------------------------------------------------- paid before marked

    def test_a_card_that_could_not_be_paid_stays_scratchable(self):
        """The regression test for the ordering.

        Marking first meant a failed payment left the card scratched and
        unpaid, and the early return made every retry a no-op.
        """
        card = self._card(reward_type='cash', amount=50.0)

        with patch.object(
                type(self.env['loyalty.card']), '_mart369_wallet',
                return_value=self.env['loyalty.card']):
            with self.assertRaises(UserError):
                card._mart369_scratch()

        self.assertFalse(card.scratched,
                         'a prize that was not paid was not revealed either')
        self.assertFalse(card.scratched_at)

    def test_and_once_it_can_be_paid_it_scratches(self):
        """The other half: the failure above must not have poisoned the card."""
        self._delivered()  # gives the partner a wallet
        card = self._card(reward_type='cash', amount=50.0)
        card._mart369_scratch()
        self.assertTrue(card.scratched)
        self.assertTrue(card.scratched_at)

    # ------------------------------------------------------- the money

    def test_a_prize_keeps_the_currency_it_was_minted_in(self):
        other = self.env.ref('base.USD')
        card = self._card(reward_type='cash', amount=20.0, currency_id=other.id)
        row = card._mart369_admin_row()
        self.assertEqual(row['amount'], 20.0)
        self.assertEqual(row['currency'], other.name)

    def test_two_currencies_are_converted_not_added(self):
        """Rupees plus dollars is not a number.

        The second currency is given an explicit rate, because without one it
        converts one-for-one and the test cannot tell a conversion from a
        plain sum - which is the whole thing being checked.
        """
        company = self.env.company.currency_id
        other = self.env['res.currency'].search(
            [('id', '!=', company.id)], limit=1)
        other.active = True
        self.env['res.currency.rate'].create({
            'currency_id': other.id,
            'company_id': self.env.company.id,
            'rate': 2.0,  # 2 of theirs to 1 of ours
            'name': fields.Date.context_today(self),
        })

        a = self._card(reward_type='cash', amount=100.0, scratched=True,
                       currency_id=company.id)
        b = self._card(reward_type='cash', amount=100.0, scratched=True,
                       currency_id=other.id)

        paid = self.Scratch._mart369_paid_in_company(a | b)
        self.assertAlmostEqual(
            paid, 150.0, places=2,
            msg='100 of ours plus 100 of theirs at 2:1 is 150, not 200')

    def test_the_payload_carries_a_number_not_a_string(self):
        """The console formats through lib/money.js and cannot do arithmetic
        on "Rs 1,200.00"."""
        counts = self.Scratch.mart369_admin_counts()
        self.assertIsInstance(counts['paidAmount'], float)
        self.assertIn('symbol', counts['currency'])

    # ----------------------------------------------------------- reading

    def _ids(self, **kwargs):
        return [c['id'] for c in self.Scratch.mart369_admin_list(**kwargs)['cards']]

    def test_each_tab_asks_for_what_it_says(self):
        waiting = self._card(reward_type='cash', amount=10.0)
        opened = self._card(reward_type='none', scratched=True)

        self.assertIn(waiting.id, self._ids(tab='unscratched'))
        self.assertNotIn(opened.id, self._ids(tab='unscratched'))
        self.assertIn(opened.id, self._ids(tab='nothing'))
        self.assertIn(waiting.id, self._ids(tab='all'))

    def test_search_matches_the_customer_and_the_origin(self):
        card = self._card(origin='Order #369M-FINDME')
        self.assertIn(card.id, self._ids(tab='all', q='FINDME'))
        self.assertIn(card.id, self._ids(tab='all', q=self.partner.name))
        self.assertNotIn(card.id, self._ids(tab='all', q='nothing is called this'))

    def test_the_tiles_count_everything_not_the_filtered_rows(self):
        self._card(origin='Order #369M-ONE')
        self._card(origin='Order #369M-TWO')
        wide = self.Scratch.mart369_admin_list(tab='all')
        narrow = self.Scratch.mart369_admin_list(tab='all', q='ONE')
        self.assertEqual(wide['counts'], narrow['counts'])
        self.assertLess(len(narrow['cards']), len(wide['cards']))

    def test_the_staff_shape_does_not_leak_into_the_shopper_one(self):
        card = self._card(reward_type='cash', amount=25.0)
        shopper = card._mart369_serialize()
        self.assertNotIn('customer', shopper)
        self.assertNotIn('origin', shopper)
        self.assertIn('from', shopper, 'the shopper still sees where it came from')

    # ------------------------------------------------------- the board

    def test_the_board_and_the_console_agree_about_what_was_paid(self):
        """Two screens, one answer. The board had no test at all before this."""
        self._card(reward_type='cash', amount=40.0, scratched=True)
        board = self.Scratch.mart369_scratch_dashboard()
        console = self.Scratch.mart369_admin_counts()
        self.assertEqual(board['paid_count'], console['paidCount'])


@tagged('post_install', '-at_install')
class TestRewardsAdminRoutes(Mart369AccountHttpCase):

    def setUp(self):
        super().setUp()
        self.env['mart369.scratch'].create({
            'partner_id': self.partner.id,
            'origin': 'Order #369M-ROUTE',
            'reward_type': 'cash',
            'amount': 30.0,
        })
        self.shopper = self.env['res.users'].sudo().create({
            'name': 'A Shopper',
            'login': 'mart369_rewards_shopper',
            'password': 'mart369_rewards_shopper',
            'group_ids': [(6, 0, [self.env.ref('base.group_portal').id])],
        })

    def test_a_shopper_is_refused(self):
        """The queue carries other customers' names and what they won."""
        self.authenticate('mart369_rewards_shopper', 'mart369_rewards_shopper')
        self.assertEqual(self.url_open(LIST).status_code, 403)
        self.assertEqual(self.url_open(LIST + '/counts').status_code, 403)

    def test_signed_out_is_sent_to_the_sign_in_page(self):
        response = self.url_open(LIST)
        self.assertIn('/web/login', response.url)

    def test_staff_read_the_cards(self):
        self.authenticate('admin', 'admin')
        payload = self.url_open(LIST + '?tab=all').json()
        self.assertTrue(payload['ok'])
        self.assertIn('cards', payload)
        self.assertIn('counts', payload)
        self.assertIn('paidAmount', payload)

    def test_there_is_no_way_to_write_a_card(self):
        """Read-only is the decision, and nothing should answer a write."""
        self.authenticate('admin', 'admin')
        for method in ('POST', 'PATCH', 'DELETE'):
            response = self.url_open(
                LIST, data=json.dumps({}), headers=HEADERS, method=method)
            self.assertNotEqual(
                response.status_code, 200,
                '%s reached something it should not have' % method)
