"""The 369 Wallet - one balance, one ledger, and no way to move one without the other.

The storefront keeps the wallet as two separate localStorage keys: `369mart.wallet`
holds a bare number, `369mart.walletLog` holds the list of movements, and they are
written by two different helpers with no reconciliation between them. A quota error
on either one leaves a customer's balance disagreeing with their own history for
ever, and nothing in the app would ever notice.

Here they are one thing. The balance is ``loyalty.card.points``; every movement is a
``loyalty.history`` row; and the only way to change the first is to write the second,
through :meth:`_mart369_move`. Three independent mechanisms keep that true, because
this number is the customer's money:

* a partial unique index, so a customer cannot end up with two wallets;
* a ``write()`` guard, so ``points`` cannot be touched outside the helper - not by a
  later module, not by an operator, not by a stray ``sudo().write()``;
* an advisory lock inside the helper, so two tabs paying at once serialise.
"""

import logging

from odoo import _, api, fields, models, tools
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

WALLET_XMLID = 'mart369_payment.loyalty_program_369_wallet'

# The four words the app's ledger already uses (accountStore.js:52). The kind
# carries the sign; the amount is always positive, because that is how the UI
# renders it (KIND_META, AccountExtras.jsx:129).
KINDS = [
    ('add', "Money added"),
    ('spend', "Spent"),
    ('refund', "Refund"),
    ('reward', "Reward"),
]
CREDIT_KINDS = ('add', 'refund', 'reward')

# Arbitrary but fixed: the first key of the advisory lock. The second is the
# partner id, so customers never block each other.
_LOCK_CLASS = 369369


class LoyaltyCard(models.Model):
    _inherit = 'loyalty.card'

    mart369_is_wallet = fields.Boolean(
        string="369 Wallet",
        compute='_compute_mart369_is_wallet', store=True, index='btree_not_null',
        help="This card is a customer's 369 Wallet rather than an ordinary coupon.")
    mart369_ledger_total = fields.Float(
        string="Ledger total", compute='_compute_mart369_ledger_total',
        help="What the movements add up to. It must equal the balance.")
    mart369_consistent = fields.Boolean(
        string="Balance agrees with the ledger", compute='_compute_mart369_ledger_total')

    # ------------------------------------------------------------------ setup

    def _auto_init(self):
        result = super()._auto_init()
        # One wallet per customer, enforced by Postgres rather than by a search
        # that two concurrent signups could both pass.
        tools.create_index(
            self.env.cr,
            'loyalty_card_mart369_wallet_partner_uniq',
            self._table,
            ['partner_id'],
            where='mart369_is_wallet IS TRUE AND partner_id IS NOT NULL',
            unique=True,
        )
        return result

    # --------------------------------------------------------------- computes

    @api.depends('program_id')
    def _compute_mart369_is_wallet(self):
        program = self.env.ref(WALLET_XMLID, raise_if_not_found=False)
        for card in self:
            card.mart369_is_wallet = bool(program) and card.program_id == program

    @api.depends('mart369_is_wallet', 'points',
                 'history_ids.issued', 'history_ids.used')
    def _compute_mart369_ledger_total(self):
        for card in self:
            if not card.mart369_is_wallet:
                card.mart369_ledger_total = 0.0
                card.mart369_consistent = True
                continue
            total = sum(card.history_ids.mapped('issued')) - sum(card.history_ids.mapped('used'))
            card.mart369_ledger_total = total
            currency = card.currency_id or self.env.company.currency_id
            # Never ==. These are Floats and the balance is money.
            card.mart369_consistent = currency.compare_amounts(card.points, total) == 0

    # ------------------------------------------------------------------ guard

    def write(self, vals):
        """Refuse a bare balance change on a wallet.

        Without this the module reproduces the exact bug it was written to fix:
        loyalty.card.write() does not create a history row, so any code that sets
        `points` directly silently desynchronises the ledger.
        """
        if 'points' in vals and not self.env.context.get('mart369_wallet_move'):
            if self.filtered('mart369_is_wallet'):
                raise UserError(_(
                    "The 369 Wallet balance can only change through a wallet movement, "
                    "so that every change leaves a record the customer can see."))
        return super().write(vals)

    # ---------------------------------------------------------------- helpers

    @api.model
    def _mart369_program(self):
        program = self.env.ref(WALLET_XMLID, raise_if_not_found=False)
        if not program:
            raise UserError(_("The 369 Wallet programme is missing. Reinstall 369 Mart Payments."))
        return program

    @api.model
    def _mart369_limit(self):
        """The most a wallet may hold. WALLET_LIMIT in accountStore.js:18."""
        param = self.env['ir.config_parameter'].sudo().get_param('mart369.wallet.limit', '10000')
        try:
            return float(param)
        except (TypeError, ValueError):
            return 10000.0

    @api.model
    def _mart369_topup_min(self):
        """The smallest top-up the app offers - AccountExtras.jsx:142."""
        param = self.env['ir.config_parameter'].sudo().get_param('mart369.wallet.topup_min', '10')
        try:
            return float(param)
        except (TypeError, ValueError):
            return 10.0

    @api.model
    def _mart369_wallet(self, partner):
        """This customer's wallet, made on first use.

        Takes the advisory lock before looking, so two simultaneous first-ever
        requests cannot both decide the wallet does not exist yet. The unique
        index is the backstop if they somehow do.
        """
        if not partner:
            raise UserError(_("A wallet needs a customer."))
        partner = partner.commercial_partner_id
        self.env.cr.execute('SELECT pg_advisory_xact_lock(%s, %s)', (_LOCK_CLASS, partner.id))
        program = self._mart369_program()
        card = self.sudo().search([
            ('program_id', '=', program.id), ('partner_id', '=', partner.id),
        ], limit=1)
        if card:
            return card
        return self.sudo().create({
            'program_id': program.id,
            'partner_id': partner.id,
            'points': 0.0,
        })

    def _mart369_balance(self):
        self.ensure_one()
        currency = self.currency_id or self.env.company.currency_id
        return currency.round(self.points)

    def _mart369_ledger(self, limit=200, before=None):
        """The movements, newest first - the app caps its own log at 200."""
        self.ensure_one()
        domain = [('card_id', '=', self.id)]
        if before:
            domain.append(('id', '<', int(before)))
        return self.env['loyalty.history'].sudo().search(
            domain, order='id desc', limit=limit)

    # ------------------------------------------------------------- the writer

    def _mart369_move(self, amount, kind, title, sub='', order=None, transaction=None):
        """Move money, and write the row that says so. The only way in.

        Returns the loyalty.history record. Raises rather than clamping: the app
        currently does ``Math.max(0, wallet - used)`` (Home.jsx:443), which silently
        absorbs an overdraft and leaves the customer's money wrong in our favour.
        """
        self.ensure_one()
        if kind not in dict(KINDS):
            raise UserError(_("%s is not a kind of wallet movement.", kind))

        currency = self.currency_id or self.env.company.currency_id
        amount = currency.round(abs(float(amount or 0.0)))
        if currency.is_zero(amount):
            raise UserError(_("A wallet movement needs an amount."))

        # Serialise against the same customer's other tabs, then re-read: the
        # balance we validate against must be the one we are about to write.
        self.env.cr.execute('SELECT pg_advisory_xact_lock(%s, %s)',
                            (_LOCK_CLASS, self.partner_id.id))
        self.invalidate_recordset(['points'])
        balance = self.points

        credit = kind in CREDIT_KINDS
        if credit:
            limit = self._mart369_limit()
            if currency.compare_amounts(balance + amount, limit) > 0:
                room = max(0.0, limit - balance)
                raise UserError(_(
                    "You can add up to %(room)s more (wallet limit %(limit)s).",
                    room=currency.format(room), limit=currency.format(limit)))
            new_balance = balance + amount
        else:
            if currency.compare_amounts(amount, balance) > 0:
                raise UserError(_("Your 369 Wallet doesn't have enough balance."))
            new_balance = balance - amount

        values = {
            'card_id': self.id,
            'issued': amount if credit else 0.0,
            'used': 0.0 if credit else amount,
            'mart369_kind': kind,
            'mart369_title': title,
            'mart369_sub': sub or '',
        }
        if order:
            values.update({'order_model': order._name, 'order_id': order.id})
        history = self.env['loyalty.history'].sudo().create(values)

        # Same transaction, immediately after the row. If either statement fails
        # the request rolls back and the customer sees neither.
        self.sudo().with_context(mart369_wallet_move=True).write({'points': new_balance})

        if transaction is not None and 'mart369_history_id' in transaction._fields:
            transaction.sudo().write({'mart369_history_id': history.id})

        _logger.info(
            'mart369 wallet %s: %s %s for partner %s (balance %s -> %s)',
            self.id, kind, amount, self.partner_id.id, balance, new_balance)
        return history
