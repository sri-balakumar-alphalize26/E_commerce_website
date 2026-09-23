"""The staff side of payments and wallets, over HTTP.

What is worth pinning here is mostly what these screens **cannot** do, and
three figures that used to say something they did not mean.

**Nothing writes.** A payment becomes true after the provider's webhook; a
wallet balance only moves through `_mart369_move`. Neither controller has a
write route at all, and that is the safety - not a check somebody could relax
later.

**Money in today** follows `last_state_change`, not `write_date`. write_date
moves whenever anything touches a row, so a payment settled last week landed
in today's takings the moment a recompute brushed past it.

**A wallet-settled order is not counted twice.** `_create_tx` stores
`amount = payable or wallet_used`, so an order paid entirely from the wallet
carries the wallet amount as its own amount - money already counted when it
was topped up.

**The settled percentage says what it is out of**, because payments still
waiting are not in the denominator and a shop whose cash-on-delivery all sits
pending would otherwise read a flawless 100%.
"""

import json

from odoo import fields
from odoo.tests import tagged
from odoo.tests.common import HttpCase

HEADERS = {'Content-Type': 'application/json'}

PAYMENTS = '/369mart/admin/payments'
WALLETS = '/369mart/admin/wallets'


@tagged('post_install', '-at_install')
class TestAdminMoney(HttpCase):

    def setUp(self):
        super().setUp()
        self.customer = self.env['res.partner'].sudo().create({
            'name': 'Money Test Customer'})
        self.provider = self.env['payment.provider'].sudo().search(
            [('state', '!=', 'disabled')], limit=1)
        self.method = self.provider.payment_method_ids[:1]

        # A counter, not a timestamp: two transactions made in the same
        # second would collide on payment.transaction's unique reference.
        self._made = 0

        self.shopper = self.env['res.users'].sudo().create({
            'name': 'Money Shopper',
            'login': 'mart369_money_shopper',
            'password': 'mart369_money_shopper',
            'group_ids': [(6, 0, [self.env.ref('base.group_portal').id])],
        })

    # ------------------------------------------------------------- building

    def _tx(self, amount=100.0, state='done', kind='order', wallet_used=0.0,
            settled_today=True):
        self._made += 1
        tx = self.env['payment.transaction'].sudo().create({
            'provider_id': self.provider.id,
            'payment_method_id': self.method.id,
            'partner_id': self.customer.id,
            'amount': amount,
            'currency_id': self.env.company.currency_id.id,
            'mart369_kind': kind,
            'mart369_wallet_used': wallet_used,
            'reference': 'MONEY-TEST-%s-%s' % (id(self), self._made),
        })
        # Written straight rather than driven through the gateway: these tests
        # are about what the screen says, not about how a payment settles.
        tx.write({'state': state})
        if state == 'done':
            tx.write({'last_state_change': fields.Datetime.now() if settled_today
                      else fields.Datetime.subtract(fields.Datetime.now(), days=9)})
        return tx

    def _wallet(self):
        return self.env['loyalty.card'].sudo()._mart369_wallet(self.customer)

    def _send(self, method, path, payload=None):
        return self.url_open(
            path, data=json.dumps(payload or {}), headers=HEADERS, method=method)

    def _get(self, base, **params):
        query = '&'.join('%s=%s' % kv for kv in params.items())
        res = self.url_open(base + ('?%s' % query if query else ''))
        return res.status_code, res.json()

    # ---------------------------------------------------------------- the lock

    def test_a_shopper_is_refused_every_admin_route(self):
        """Refused, not filtered. These rows carry customers' names and what
        they paid."""
        self.authenticate('mart369_money_shopper', 'mart369_money_shopper')
        card = self._wallet()
        for res in (self.url_open(PAYMENTS),
                    self.url_open(WALLETS),
                    self.url_open('%s/%s/ledger' % (WALLETS, card.id))):
            self.assertEqual(res.status_code, 403)
            self.assertFalse(res.json().get('ok'))

    def test_there_is_no_write_route_at_all(self):
        """The safety is that there is nothing to call. A POST or PATCH to
        either screen must not be a route."""
        self.authenticate('admin', 'admin')
        for method in ('POST', 'PATCH', 'DELETE'):
            for path in (PAYMENTS, WALLETS):
                res = self._send(method, path, {'state': 'done'})
                self.assertNotEqual(
                    res.status_code, 200,
                    "%s %s answered - this screen must not write" % (method, path))

    # ------------------------------------------------------- honest figures

    def test_money_in_today_follows_when_it_was_paid(self):
        """Not write_date, which moves whenever anything touches the row."""
        old = self._tx(amount=500.0, settled_today=False)
        # Anything at all touching the row: a recompute, an upgrade, this.
        old.write({'mart369_order_ref': 'touched-today'})

        self.authenticate('admin', 'admin')
        __, payload = self._get(PAYMENTS)
        today = self._tx(amount=70.0, settled_today=True)
        __, after = self._get(PAYMENTS)

        self.assertAlmostEqual(
            after['tiles']['collected_amount'] - payload['tiles']['collected_amount'],
            70.0, places=2,
            msg="a payment settled days ago must not land in today's takings")
        self.assertTrue(today)

    def test_an_order_paid_from_the_wallet_is_not_counted_twice(self):
        """That money was counted when it was topped up."""
        self.authenticate('admin', 'admin')
        __, before = self._get(PAYMENTS)
        # `amount == wallet_used` is what _create_tx writes for an order
        # settled entirely from the wallet.
        self._tx(amount=250.0, wallet_used=250.0)
        __, after = self._get(PAYMENTS)
        self.assertAlmostEqual(
            after['tiles']['collected_amount'],
            before['tiles']['collected_amount'], places=2)
        self.assertEqual(
            after['tiles']['from_wallet_count'],
            before['tiles']['from_wallet_count'] + 1,
            "it should be named rather than silently missing")

    def test_a_split_payment_counts_only_the_gateway_leg(self):
        """Half from the wallet, half from a card: only the card half is new
        money."""
        self.authenticate('admin', 'admin')
        __, before = self._get(PAYMENTS)
        self._tx(amount=120.0, wallet_used=80.0)
        __, after = self._get(PAYMENTS)
        self.assertAlmostEqual(
            after['tiles']['collected_amount'] - before['tiles']['collected_amount'],
            120.0, places=2)

    def test_the_settled_percentage_says_what_it_is_out_of(self):
        self.authenticate('admin', 'admin')
        __, payload = self._get(PAYMENTS)
        self.assertIn('success_of', payload['tiles'])
        self.assertIsInstance(payload['tiles']['success_of'], int)

    def test_the_payload_carries_numbers_not_only_strings(self):
        """The console does arithmetic and formats for itself; it cannot do
        either with "Rs 1,200.00"."""
        self.authenticate('admin', 'admin')
        __, pay = self._get(PAYMENTS)
        for key in ('collected_amount', 'cash_amount', 'wallet_float_amount'):
            self.assertIsInstance(pay['tiles'][key], float)
        __, wal = self._get(WALLETS)
        for key in ('held_amount', 'biggest_amount'):
            self.assertIsInstance(wal['tiles'][key], float)

    # -------------------------------------------------------- the payments

    def test_each_tab_is_a_domain_not_a_suggestion(self):
        self.authenticate('admin', 'admin')
        self._tx(state='done')
        self._tx(state='error')

        __, paid = self._get(PAYMENTS, tab='paid')
        self.assertTrue(all(r['state'] == 'done' for r in paid['rows']))

        __, failed = self._get(PAYMENTS, tab='failed')
        self.assertTrue(all(r['state'] in ('cancel', 'error') for r in failed['rows']))

    def test_cash_at_the_door_is_not_waiting_on_a_bank(self):
        """The two pending tabs split on the provider, which no domain sees."""
        self.authenticate('admin', 'admin')
        __, cash = self._get(PAYMENTS, tab='cash')
        self.assertTrue(all(r['cod'] for r in cash['rows']))
        __, waiting = self._get(PAYMENTS, tab='waiting')
        self.assertTrue(all(not r['cod'] for r in waiting['rows']))

    def test_the_tiles_count_everything_not_the_filtered_rows(self):
        self.authenticate('admin', 'admin')
        self._tx(state='done')
        __, everything = self._get(PAYMENTS)
        __, searched = self._get(PAYMENTS, q='MONEY-TEST-no-such-reference')
        self.assertEqual(searched['rows'], [])
        self.assertEqual(searched['tiles'], everything['tiles'])
        self.assertEqual(searched['counts'], everything['counts'])

    def test_an_order_reference_that_leads_nowhere_is_not_a_link(self):
        """`mart369_order_ref` is text; a link drawn for every row would 404."""
        self.authenticate('admin', 'admin')
        tx = self._tx()
        tx.write({'mart369_order_ref': 'NO-SUCH-ORDER-369'})
        __, payload = self._get(PAYMENTS)
        row = next(r for r in payload['rows'] if r['id'] == tx.id)
        self.assertEqual(row['orderRef'], 'NO-SUCH-ORDER-369')
        self.assertIsNone(row['orderId'])

    # --------------------------------------------------------- the wallets

    def test_a_wallet_shows_its_balance_and_its_ledger(self):
        self.authenticate('admin', 'admin')
        card = self._wallet()
        card._mart369_move(60.0, 'add', 'Top-up', sub='a test')

        __, payload = self._get(WALLETS)
        row = next(r for r in payload['rows'] if r['id'] == card.id)
        self.assertAlmostEqual(row['balance'], 60.0, places=2)
        self.assertTrue(row['consistent'])
        self.assertEqual(row['lastKind'], 'add')

        res = self.url_open('%s/%s/ledger' % (WALLETS, card.id))
        self.assertEqual(res.status_code, 200, res.text)
        ledger = res.json()
        self.assertTrue(ledger['ok'])
        self.assertEqual(ledger['moves'][0]['kind'], 'add')
        # The customer's own six keys, plus the formatted amount for the desk.
        self.assertEqual(
            set(ledger['moves'][0]) - {'amountText'},
            {'id', 'kind', 'amount', 'title', 'sub', 'at'})

    def test_money_we_hold_is_every_wallet_added_up(self):
        self.authenticate('admin', 'admin')
        __, before = self._get(WALLETS)
        self._wallet()._mart369_move(25.0, 'add', 'Top-up')
        __, after = self._get(WALLETS)
        self.assertAlmostEqual(
            after['tiles']['held_amount'] - before['tiles']['held_amount'],
            25.0, places=2)

    def test_the_ledger_refuses_a_card_that_is_not_a_wallet(self):
        self.authenticate('admin', 'admin')
        other = self.env['loyalty.card'].sudo().search(
            [('mart369_is_wallet', '=', False)], limit=1)
        if not other:
            self.skipTest("no non-wallet loyalty card in this database")
        res = self.url_open('%s/%s/ledger' % (WALLETS, other.id))
        self.assertEqual(res.status_code, 404)

    def test_a_balance_cannot_be_written_directly(self):
        """Not a route thing - the model itself refuses, which is why there is
        nothing to expose."""
        card = self._wallet()
        with self.assertRaises(Exception):
            card.sudo().write({'points': 9999.0})

    # ----------------------------------------------------------- demo data

    def test_the_demo_never_runs_on_a_shop_that_has_wallets(self):
        self._wallet()
        self.assertFalse(self.env['loyalty.card']._mart369_load_demo())
