"""Which journal a 369 Mart payment lands in.

Odoo books a settled transaction as an `account.payment` in its provider's
journal. The two providers the shop runs itself - cash on delivery and the 369
Wallet - are `custom` providers, and Odoo 19 has no payment method for `custom`,
so they can never be given a journal the usual way: their `journal_id` falls
back to the company's first bank journal. Cash a rider carried back would read
as money in the bank, and wallet money as the same.

So each company gets two journals of its own, *Cash on delivery* and *369
Wallet*, and `_create_payment` is told to use them. Gateways (UPI, card) are
left on whatever journal Odoo gives them - that is their bank.
"""

import logging

from odoo import api, models

_logger = logging.getLogger(__name__)

# custom_mode -> (xmlid stem, journal name, codes to try)
JOURNALS = {
    'cash_on_delivery': ('journal_cod', 'Cash on delivery', ('COD', 'CODM')),
    'mart369_wallet': ('journal_wallet', '369 Wallet', ('WLT', 'WLTM')),
}


class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    def _mart369_journal_kind(self):
        self.ensure_one()
        if self.code != 'custom':
            return None
        return self.custom_mode if self.custom_mode in JOURNALS else None

    def _mart369_journal(self):
        """This provider's own journal, made the first time it is needed.

        None for a gateway: Odoo's choice stands for those.
        """
        self.ensure_one()
        kind = self._mart369_journal_kind()
        if not kind:
            return self.env['account.journal']
        return self.env['account.journal']._mart369_journal_for(kind, self.company_id)

    @api.model
    def _mart369_setup_journals(self):
        """Make the journals up front, for every company running either provider.

        Called from data on every update. Lazy creation in `_mart369_journal`
        would do on its own, but then the journals would only appear after the
        first cash order - and an accountant looking for them before that would
        reasonably conclude they do not exist.
        """
        providers = self.sudo().search([
            ('code', '=', 'custom'),
            ('custom_mode', 'in', list(JOURNALS)),
        ])
        for provider in providers:
            provider._mart369_journal()
        # And give them the accounts that make their payments real entries
        # (wallet_books.py).
        Journal = self.env['account.journal']
        for company in providers.mapped('company_id'):
            kinds = {p._mart369_journal_kind() for p in providers
                     if p.company_id == company}
            try:
                with self.env.cr.savepoint():
                    Journal._mart369_setup_books(company, kinds)
            except Exception:  # noqa: BLE001 - an update must not fail on the books
                _logger.exception('mart369: could not set up the books for %s', company.name)
        return True


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    @api.model
    def _mart369_journal_for(self, kind, company):
        """The company's journal for `kind`, found by its xmlid or created once."""
        stem, name, codes = JOURNALS[kind]
        company = company or self.env.company
        xmlid = '%s_company_%s' % (stem, company.id)
        journal = self.env.ref('mart369_order.%s' % xmlid, raise_if_not_found=False)
        if journal:
            return journal.sudo()

        Journal = self.sudo().with_company(company)
        taken = set(Journal.search([('company_id', '=', company.id)]).mapped('code'))
        code = next((c for c in codes if c not in taken), None)
        if not code:
            _logger.warning('mart369: no free journal code for %s in %s', name, company.name)
            return self.env['account.journal']
        journal = Journal.create({
            'name': name,
            'type': 'cash',
            'code': code,
            'company_id': company.id,
        })
        # noupdate, so a module update never removes a journal it did not load
        # from XML - it holds the shop's money.
        self.env['ir.model.data'].sudo().create({
            'module': 'mart369_order',
            'name': xmlid,
            'model': 'account.journal',
            'res_id': journal.id,
            'noupdate': True,
        })
        _logger.info('mart369: created journal %s (%s) for %s', name, code, company.name)
        # Without accounts on its method lines, Odoo 19 books its payments as
        # nothing at all (wallet_books.py).
        journal._mart369_setup_journal_books()
        return journal


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    def _create_payment(self, **extra_create_values):
        """Book cash and wallet payments in their own journals.

        Everything else about the payment is Odoo's - including reconciling it
        with `invoice_ids`, which `sale.order._mart369_settle_invoice` fills in.
        """
        if not self.mart369_kind:
            return super()._create_payment(**extra_create_values)
        provider = self.provider_id.sudo()
        journal = provider._mart369_journal() or provider.journal_id or self.env[
            'account.journal'].sudo().search([
                ('company_id', '=', provider.company_id.id), ('type', '=', 'bank')], limit=1)
        if journal:
            extra_create_values.setdefault('journal_id', journal.id)
            # The provider's own line when it has one; otherwise the journal's
            # plain inbound method. A gateway whose module registered no
            # payment method would otherwise fail with "Please define a
            # payment method line" and leave the invoice unpaid.
            lines = journal.inbound_payment_method_line_ids
            line = lines.filtered(lambda l: l.payment_provider_id == provider)[:1] or lines[:1]
            if line:
                extra_create_values.setdefault('payment_method_line_id', line.id)
        return super()._create_payment(**extra_create_values)
