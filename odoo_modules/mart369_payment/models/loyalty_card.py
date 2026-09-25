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
from odoo.exceptions import AccessError, UserError

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
        string="Balance agrees with the ledger",
        compute='_compute_mart369_ledger_total', search='_search_mart369_consistent')

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

    def _search_mart369_consistent(self, operator, value):
        """Find the wallets whose balance and ledger disagree.

        A computed field is not searchable by itself, and an operator screen that
        cannot filter for a broken wallet would make the check decorative. Done in
        SQL because the alternative is reading every card in Python.
        """
        self.env.cr.execute("""
            SELECT c.id
              FROM loyalty_card c
              LEFT JOIN loyalty_history h ON h.card_id = c.id
             WHERE c.mart369_is_wallet IS TRUE
             GROUP BY c.id, c.points
            HAVING ROUND(c.points::numeric, 2)
                 <> ROUND(COALESCE(SUM(h.issued), 0)::numeric - COALESCE(SUM(h.used), 0)::numeric, 2)
        """)
        broken = [row[0] for row in self.env.cr.fetchall()]
        wants_broken = (operator in ('=', '==')) == (not value)
        return [('id', 'in' if wants_broken else 'not in', broken)]

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
            # The limit is on money *added*. A refund is the customer's own
            # money coming back - refusing it because the wallet is full
            # would keep it.
            limit = self._mart369_limit()
            if kind != 'refund' and currency.compare_amounts(balance + amount, limit) > 0:
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

    # ------------------------------------------------------- the staff screen

    ADMIN_TABS = ('all', 'money', 'empty', 'broken')

    @api.model
    def _mart369_admin_may_read(self):
        """Who may read the wallet screens.

        Either group, because the two front ends are fenced differently: the
        backend desk sits behind the system group its menu has always used,
        and the app console behind the website designer group every admin
        controller in the suite checks. One check, shared, is how the two stay
        agreed about who may look.
        """
        if not (self.env.user.has_group('base.group_system')
                or self.env.user.has_group('website.group_website_designer')):
            raise AccessError(_("You do not have access to this."))
        return True

    @api.model
    def mart369_admin_list(self, tab='all', q='', limit=200):
        """Every 369 Wallet, with what the shop is holding in them.

        Read-only, and there is nothing here that writes. A wallet is real
        money the shop owes a customer; the only way its balance ever moves is
        `_mart369_move`, called by a top-up, an order, a refund or a reward -
        each of which is a thing that actually happened.
        """
        self._mart369_admin_may_read()
        domain = [('mart369_is_wallet', '=', True)]
        if tab == 'money':
            domain += [('points', '>', 0)]
        elif tab == 'empty':
            domain += [('points', '<=', 0)]
        elif tab == 'broken':
            domain += [('mart369_consistent', '=', False)]
        q = (q or '').strip()
        if q:
            domain += ['|', '|',
                       ('partner_id.name', 'ilike', q),
                       ('partner_id.email', 'ilike', q),
                       ('partner_id.phone', 'ilike', q)]

        cards = self.sudo().search(domain, order='points desc, id desc', limit=limit)

        every = self.sudo().search([('mart369_is_wallet', '=', True)])
        with_money = every.filtered(lambda c: c.points > 0)
        broken = every.filtered(lambda c: not c.mart369_consistent)
        held = sum(every.mapped('points'))
        biggest = max(every.mapped('points')) if every else 0.0
        top = every.filtered(lambda c: c.points == biggest)[:1] if every else every
        currency = self.env.company.currency_id
        return {
            'rows': [card._mart369_admin_row() for card in cards],
            'counts': {
                'all': len(every),
                'money': len(with_money),
                'empty': len(every) - len(with_money),
                'broken': len(broken),
            },
            'tiles': {
                'wallets': len(every),
                # Money the shop is holding for customers. A liability, not
                # takings - it has already been paid for, and every rupee of
                # it will be spent or asked for back.
                'held': currency.format(held),
                'held_amount': float(held),
                'biggest': currency.format(biggest),
                'biggest_amount': float(biggest),
                'biggest_who': top.partner_id.display_name if top else '',
                'broken': len(broken),
                'currency': currency.name,
            },
        }

    def _mart369_admin_row(self):
        self.ensure_one()
        last = self.env['loyalty.history'].sudo().search(
            [('card_id', '=', self.id)], order='id desc', limit=1)
        currency = self.currency_id or self.env.company.currency_id
        return {
            'id': self.id,
            'customer': self.partner_id.display_name or '',
            'email': self.partner_id.email or '',
            'balance': self.points,
            'balanceText': currency.format(self.points),
            # Only meaningful when it differs from the balance, and the screens
            # say so by drawing it only then.
            'ledger': self.mart369_ledger_total,
            'ledgerText': currency.format(self.mart369_ledger_total),
            'consistent': self.mart369_consistent,
            'moves': self.env['loyalty.history'].sudo().search_count(
                [('card_id', '=', self.id)]),
            'lastKind': last.mart369_kind or '',
            'lastTitle': last.mart369_title or '',
            'lastAt': int(last.create_date.timestamp() * 1000) if last.create_date else None,
            'currency': currency.name,
        }

    @api.model
    def mart369_admin_ledger(self, card_id, before=None, limit=50):
        """One wallet's movements, for the drawer and the dialog.

        A public wrapper over `_mart369_ledger` so the console, the desk and
        the controller all go through the same access check and come back with
        the same rows. Those rows are `loyalty.history._mart369_serialize()`
        verbatim - the same six fields the customer sees in their own app, so
        staff and customer are never reading different stories about the same
        money.
        """
        self._mart369_admin_may_read()
        card = self.sudo().browse(int(card_id)).exists()
        if not card or not card.mart369_is_wallet:
            raise UserError(_("That is not a 369 Wallet."))
        rows = card._mart369_ledger(limit=limit, before=before)
        currency = card.currency_id or self.env.company.currency_id
        moves = []
        for row in rows:
            # The customer's own six keys, untouched, with the formatted amount
            # added beside them for the backend desk. `_mart369_serialize` keeps
            # its exact shape because the app parses it.
            move = row._mart369_serialize()
            move['amountText'] = currency.format(move['amount'])
            moves.append(move)
        return {
            'card': card._mart369_admin_row(),
            'moves': moves,
            # The id to ask from next. None once the page came back short,
            # which is how the screens know to stop offering "show older".
            'before': rows[-1].id if len(rows) == limit else None,
        }

    # ------------------------------------------------------------ demo data

    @api.model
    def _mart369_load_demo(self):
        """A couple of empty wallets, on a shop where nobody has one yet.

        **No balances, and no payments anywhere.** A seeded balance is money
        the shop would owe a real customer, and it would show up under "Money
        we hold"; a seeded `payment.transaction` would land in today's
        takings, the success rate and the sparkline, on the very screen staff
        would use to check the bank. Neither has an honest version.

        An empty wallet is not a claim about money. It is true in the ordinary
        way - a wallet is made for a customer the first time one is needed -
        and it lets the screen and the movements dialog be seen with every
        number still correct.

        Does nothing once any wallet exists, so a shop with real ones never
        has examples added to the list it is reconciling.
        """
        if self.sudo().search_count([('mart369_is_wallet', '=', True)]):
            return False
        partners = self.env['res.partner'].sudo().search([
            ('is_company', '=', False),
            ('parent_id', '=', False),
            ('name', '!=', False),
            '|', ('customer_rank', '>', 0), ('user_ids.share', '=', True),
        ], order='customer_rank desc, id', limit=2)
        if not partners:
            # No customers, so no wallets. The empty state explains itself.
            return False
        for partner in partners:
            self._mart369_wallet(partner)
        return True
