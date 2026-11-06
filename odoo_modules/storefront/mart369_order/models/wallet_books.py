"""The 369 Wallet in Odoo's own books.

The wallet is money the shop owes its customers, so it lives on a liability
account - *369 Wallet balances* - and every movement of the app's ledger
(`loyalty.card._mart369_move`) that brings money *in* is booked against it:

* a refund to the wallet (cancel, return, item removed, cheaper substitute):
  an outbound customer payment in the 369 Wallet journal, reconciled with the
  order's credit note - Dr receivable / Cr Wallet balances;
* a top-up: the same payment, reconciled with the gateway payment that brought
  the money in - the customer's receivable nets to nothing;
* a scratch prize, a referral reward, a goodwill credit: an entry
  Dr *369 Wallet rewards* (expense) / Cr Wallet balances.

Money going *out* - spending the wallet on an order - is the wallet journal's
ordinary inbound payment (payment_journal.py, order_accounting.py), which now
posts to the same liability account. So the account's credit balance is the
sum of every wallet, once the opening entry for the balances that predate
this module is posted.

Like the rest of the accounting here (order_accounting.py), a booking that
fails is logged and never takes the customer's money back: the wallet move
has already happened, and a missing entry is finance's to redo.
"""

import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

# xmlid stem -> (name, account type, code to count up from when none of that
# type exists yet)
ACCOUNTS = {
    'wallet_liability': ('369 Wallet balances', 'liability_current', '209000'),
    'wallet_rewards': ('369 Wallet rewards', 'expense', '609000'),
}


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    @api.model
    def _mart369_account_for(self, stem, company):
        """The company's account for `stem`, found by its xmlid or created once."""
        name, account_type, start = ACCOUNTS[stem]
        xmlid = '%s_company_%s' % (stem, company.id)
        account = self.env.ref('mart369_order.%s' % xmlid, raise_if_not_found=False)
        if account:
            return account.sudo()
        Account = self.env['account.account'].sudo().with_company(company)
        sibling = Account.search([
            *Account._check_company_domain(company),
            ('account_type', '=', account_type),
        ], order='code desc', limit=1)
        code = Account._search_new_account_code(sibling.code or start)
        account = Account.create({
            'name': name,
            'code': code,
            'account_type': account_type,
            # Not reconcilable: a wallet payment is then Paid the moment it
            # posts, and so is the invoice it settles.
            'reconcile': False,
            'company_ids': [(6, 0, [company.id])],
        })
        self.env['ir.model.data'].sudo().create({
            'module': 'mart369_order',
            'name': xmlid,
            'model': 'account.account',
            'res_id': account.id,
            'noupdate': True,
        })
        _logger.info('mart369: created account %s %s for %s', code, name, company.name)
        return account

    def _mart369_give_lines_an_account(self, account):
        """Odoo 19 books a payment only when its method line has an
        outstanding account; without one the payment is 'in process' for
        ever and no entry is made. Never overwrites a choice already made."""
        for line in (self.inbound_payment_method_line_ids
                     + self.outbound_payment_method_line_ids):
            if not line.payment_account_id:
                line.sudo().payment_account_id = account

    @api.model
    def _mart369_setup_books(self, company, kinds=('cash_on_delivery', 'mart369_wallet')):
        """Accounts on the journals of `kinds`, for one company. Idempotent.
        Only the kinds the company runs a provider for: a branch without the
        wallet gets no wallet journal."""
        company = company.sudo()
        for kind in kinds:
            journal = self._mart369_journal_for(kind, company)
            if journal:
                journal._mart369_setup_journal_books()
        self._mart369_books_catch_up(company)
        if 'mart369_wallet' in kinds:
            self._mart369_wallet_opening(company)

    def _mart369_setup_journal_books(self):
        """The accounts one of the two journals needs. Idempotent; also run
        when the journal is first made (payment_journal.py)."""
        self.ensure_one()
        company = self.company_id.sudo()
        if self == self.env.ref('mart369_order.journal_cod_company_%s' % company.id,
                                raise_if_not_found=False):
            if self.default_account_id:
                # The rider's cash is cash: the journal's own account.
                self._mart369_give_lines_an_account(self.default_account_id)
            return
        wallet = self
        liability = (company.mart369_wallet_account_id
                     or self._mart369_account_for('wallet_liability', company))
        rewards = (company.mart369_wallet_reward_account_id
                   or self._mart369_account_for('wallet_rewards', company))
        if not company.mart369_wallet_account_id:
            company.mart369_wallet_account_id = liability
        if not company.mart369_wallet_reward_account_id:
            company.mart369_wallet_reward_account_id = rewards
        # The liability is the journal's own account. Odoo lets a payment
        # account be non-reconcilable only when it is the journal's default
        # (account._check_used_as_journal_default_debit_credit_account), and
        # it must be non-reconcilable: otherwise every wallet payment waits
        # for a bank statement that never comes and its invoice sits
        # In payment for ever.
        if wallet.default_account_id != liability:
            old = wallet.default_account_id
            if old and self.env['account.move.line'].sudo().search_count(
                    [('account_id', '=', old.id)], limit=1):
                _logger.warning('mart369: %s already has entries on %s; left as it is',
                                wallet.display_name, old.display_name)
                return
            wallet.sudo().default_account_id = liability
        wallet._mart369_give_lines_an_account(liability)
        if liability.reconcile:
            # Switched on by Odoo when it became a payment account
            # (account_payment_method._auto_toggle_account_to_reconcile).
            liability.sudo().reconcile = False

    @api.model
    def _mart369_books_catch_up(self, company):
        """Payments posted before the lines had an account have no entry:
        make it, post it, and match it with its invoice."""
        journals = self.sudo().search([
            ('id', 'in', [r.res_id for r in self.env['ir.model.data'].sudo().search([
                ('module', '=', 'mart369_order'), ('model', '=', 'account.journal'),
                ('name', 'in', ['journal_cod_company_%s' % company.id,
                                'journal_wallet_company_%s' % company.id])])]),
        ])
        stuck = self.env['account.payment'].sudo().search([
            ('journal_id', 'in', journals.ids),
            ('state', '=', 'in_process'),
            ('move_id', '=', False),
        ])
        done = 0
        for payment in stuck:
            try:
                with self.env.cr.savepoint():
                    account = payment.payment_method_line_id.payment_account_id
                    if not account:
                        continue
                    payment.outstanding_account_id = account
                    # Odoo's own path: writing the state makes and posts the
                    # entry for a payment that has none (account_payment.write).
                    payment.write({'state': 'in_process'})
                    if not payment.move_id:
                        continue
                    invoices = payment.invoice_ids.filtered(
                        lambda m: m.move_type == 'out_invoice' and m.state == 'posted')
                    if not invoices:
                        # Tied by the order's number, not by Odoo's own
                        # link (order_accounting.py).
                        refs = self.env['payment.transaction'].sudo().search([
                            ('payment_id', '=', payment.id)]).mapped('mart369_order_ref')
                        orders = self.env['sale.order'].sudo().search([
                            ('mart369_ref', 'in', [r for r in refs if r])])
                        invoices = orders.invoice_ids.filtered(
                            lambda m: m.move_type == 'out_invoice' and m.state == 'posted')
                    self.env['sale.order']._mart369_reconcile(payment, invoices)
                    done += 1
            except Exception:  # noqa: BLE001 - one bad payment must not stop the rest
                _logger.exception('mart369: could not book payment %s', payment.name)
        if done:
            _logger.info('mart369: booked %d payment(s) that had no entry for %s',
                         done, company.name)
        return done

    @api.model
    def _mart369_wallet_opening(self, company):
        """The balances that predate the books, as one DRAFT entry for the
        accountant to check and post. Made once per company."""
        xmlid = 'wallet_opening_company_%s' % company.id
        if self.env.ref('mart369_order.%s' % xmlid, raise_if_not_found=False):
            return False
        wallet = self._mart369_journal_for('mart369_wallet', company)
        liability = company.mart369_wallet_account_id
        other = company.account_journal_suspense_account_id or company.mart369_wallet_reward_account_id
        if not (wallet and liability and other):
            return False
        Card = self.env['loyalty.card'].sudo()
        program = Card._mart369_program()
        cards = Card.search([
            ('program_id', '=', program.id), ('points', '>', 0),
            '|', ('company_id', '=', company.id), ('company_id', '=', False),
        ])
        total = company.currency_id.round(sum(cards.mapped('points')))
        record = self.env['account.move']
        if not company.currency_id.is_zero(total):
            record = self.env['account.move'].sudo().create({
                'move_type': 'entry',
                'journal_id': wallet.id,
                'company_id': company.id,
                'date': fields.Date.context_today(self),
                'ref': '369 Wallet opening balances',
                'line_ids': [
                    (0, 0, {'account_id': other.id, 'debit': total,
                            'name': '369 Wallet opening balances (%d wallets)' % len(cards)}),
                    (0, 0, {'account_id': liability.id, 'credit': total,
                            'name': '369 Wallet opening balances (%d wallets)' % len(cards)}),
                ],
            })
        # The marker is made even when there was nothing to open, so a wallet
        # funded later is never counted twice.
        self.env['ir.model.data'].sudo().create({
            'module': 'mart369_order',
            'name': xmlid,
            'model': 'account.move' if record else 'res.company',
            'res_id': record.id if record else company.id,
            'noupdate': True,
        })
        return record


class LoyaltyHistory(models.Model):
    _inherit = 'loyalty.history'

    mart369_move_id = fields.Many2one(
        'account.move', string='Journal entry', readonly=True, copy=False,
        index='btree_not_null',
        help="What this wallet movement booked in the 369 Wallet journal. "
             "Set once, so booking it again does nothing.")


class LoyaltyCard(models.Model):
    _inherit = 'loyalty.card'

    def _mart369_move(self, amount, kind, title, sub='', order=None, transaction=None):
        history = super()._mart369_move(
            amount, kind, title, sub=sub, order=order, transaction=transaction)
        try:
            with self.env.cr.savepoint():
                self._mart369_book(history, order=order, transaction=transaction)
        except Exception:  # noqa: BLE001 - see the module docstring
            _logger.exception('mart369: could not book wallet movement %s', history.id)
        return history

    def _mart369_book(self, history, order=None, transaction=None):
        """The entry for one ledger row, when it moves money into a wallet."""
        self.ensure_one()
        if history.mart369_move_id:
            return history.mart369_move_id
        kind = history.mart369_kind
        amount = history.issued
        company = ((order and order.company_id) or (transaction and transaction.company_id)
                   or self.company_id or self.env.company)
        partner = self.partner_id.commercial_partner_id
        memo = ' - '.join(p for p in (history.mart369_title, history.mart369_sub) if p)
        Journal = self.env['account.journal']
        if kind == 'refund' and order:
            move = self._mart369_book_wallet_out(amount, partner, memo, company)
            history.sudo().mart369_move_id = move
            order._mart369_reconcile_wallet_refunds()
        elif kind == 'add' and transaction:
            move = self._mart369_book_wallet_out(amount, partner, memo, company)
            history.sudo().mart369_move_id = move
            transaction._mart369_reconcile_topup()
        elif kind == 'reward':
            wallet = Journal._mart369_journal_for('mart369_wallet', company)
            liability = company.mart369_wallet_account_id
            rewards = company.mart369_wallet_reward_account_id
            if not (wallet and liability and rewards):
                return False
            move = self.env['account.move'].sudo().create({
                'move_type': 'entry',
                'journal_id': wallet.id,
                'company_id': company.id,
                'date': fields.Date.context_today(self),
                'ref': memo,
                'line_ids': [
                    (0, 0, {'account_id': rewards.id, 'partner_id': partner.id,
                            'debit': amount, 'name': memo}),
                    (0, 0, {'account_id': liability.id, 'partner_id': partner.id,
                            'credit': amount, 'name': memo}),
                ],
            })
            move.action_post()
            history.sudo().mart369_move_id = move
        else:
            # spend: booked by the order's own payment. A refund with no order
            # is a failed split leg given back - its spend was never booked.
            return False
        return history.mart369_move_id

    def _mart369_book_wallet_out(self, amount, partner, memo, company):
        """Money into a customer's wallet: Dr receivable / Cr Wallet balances."""
        wallet = self.env['account.journal']._mart369_journal_for('mart369_wallet', company)
        if not wallet or not company.mart369_wallet_account_id:
            return self.env['account.move']
        values = {
            'amount': amount,
            'payment_type': 'outbound',
            'partner_type': 'customer',
            'partner_id': partner.id,
            'currency_id': company.currency_id.id,
            'journal_id': wallet.id,
            'company_id': company.id,
            'memo': memo,
        }
        line = wallet.outbound_payment_method_line_ids[:1]
        if line:
            values['payment_method_line_id'] = line.id
        payment = self.env['account.payment'].sudo().with_company(company).create(values)
        payment.action_post()
        return payment.move_id


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _mart369_reconcile_wallet_refunds(self):
        """Match the order's credit notes with the wallet refunds that paid
        them out. Called after either side appears, since callers move the
        wallet first and write the credit note second."""
        for order in self:
            moves = self.env['loyalty.history'].sudo().search([
                ('order_model', '=', 'sale.order'), ('order_id', '=', order.id),
                ('mart369_kind', '=', 'refund'), ('mart369_move_id', '!=', False),
            ]).mapped('mart369_move_id')
            notes = order.invoice_ids.filtered(
                lambda m: m.move_type == 'out_refund' and m.state == 'posted')
            lines = (moves + notes).line_ids.filtered(
                lambda l: l.account_id.account_type == 'asset_receivable'
                and not l.reconciled)
            for account in lines.account_id:
                group = lines.filtered(lambda l: l.account_id == account)
                if group.filtered(lambda l: l.debit) and group.filtered(lambda l: l.credit):
                    group.reconcile()
        return True


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    def _mart369_reconcile_topup(self):
        """A top-up's gateway payment (Cr receivable) against the wallet
        payment that moved it into the wallet (Dr receivable)."""
        for tx in self:
            if tx.mart369_kind != 'topup' or not tx.payment_id or not tx.mart369_history_id:
                continue
            moves = tx.payment_id.move_id + tx.mart369_history_id.mart369_move_id
            lines = moves.line_ids.filtered(
                lambda l: l.account_id.account_type == 'asset_receivable'
                and not l.reconciled)
            if lines.filtered(lambda l: l.debit) and lines.filtered(lambda l: l.credit):
                lines.reconcile()
        return True

    def _create_payment(self, **extra_create_values):
        payment = super()._create_payment(**extra_create_values)
        if self.mart369_kind == 'topup':
            try:
                with self.env.cr.savepoint():
                    self._mart369_reconcile_topup()
            except Exception:  # noqa: BLE001
                _logger.exception('mart369: could not match top-up %s', self.reference)
        return payment
