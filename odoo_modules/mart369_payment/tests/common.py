"""Shared fixtures.

One place that knows how to produce a usable provider and a transaction, because a
completed payment reaches into `account_payment` and wants a journal - and because
when mart369_order lands and changes how an order is priced, there should be exactly
one place in the tests to follow it.
"""

from odoo.tests import HttpCase, TransactionCase


class Mart369PaymentFixtures:
    """Mixin: a gateway that can actually take money, and transactions to test with."""

    @classmethod
    def _mart369_journal(cls, company):
        return cls.env['account.journal'].sudo().search([
            ('type', 'in', ('bank', 'cash')),
            ('company_id', '=', company.id),
        ], limit=1)

    @classmethod
    def _mart369_enable(cls, provider):
        """Switch a provider on, with a journal of its own company.

        This database has several companies, and Odoo refuses a provider whose
        journal belongs to somebody else - so the journal has to follow the
        provider, not env.company.
        """
        company = provider.company_id or cls.env.company
        journal = cls._mart369_journal(company)
        values = {'state': 'test'}
        if journal and 'journal_id' in provider._fields:
            values['journal_id'] = journal.id
        provider.sudo().write(values)
        return provider

    @classmethod
    def _mart369_gateway(cls):
        """A gateway that can take money, made for the test rather than found.

        Deliberately our own `code='none'` provider, the way payment's own test
        common does it. Picking a real one out of the database is what a first
        attempt does and it does not work: Stripe refuses to be enabled without
        API keys, and whichever provider a database happens to have configured
        makes the suite depend on that database.

        The module never names a provider anyway - it resolves through
        _get_compatible_providers - so a dummy exercises exactly the same path a
        real Razorpay would.
        """
        Provider = cls.env['payment.provider'].sudo()
        provider = Provider.search([('name', '=', "369 Mart Test Gateway")], limit=1)
        upi = cls.env.ref('payment.payment_method_upi')
        upi.sudo().write({'active': True})

        if not provider:
            form = cls.env['ir.ui.view'].sudo().create({
                'name': "369 Mart test redirect form",
                'type': 'qweb',
                'arch': '<form action="dummy" method="post"/>',
            })
            provider = Provider.create({
                'name': "369 Mart Test Gateway",
                'code': 'none',
                'state': 'test',
                'company_id': cls.env.company.id,
                'redirect_form_view_id': form.id,
                'payment_method_ids': [(6, 0, [upi.id])],
                'available_currency_ids': [(6, 0, [cls.env.company.currency_id.id])],
            })
        elif upi not in provider.payment_method_ids:
            provider.write({'payment_method_ids': [(4, upi.id)]})

        return cls._mart369_enable(provider)

    @classmethod
    def _mart369_wallet_provider(cls):
        return cls._mart369_enable(cls.env.ref('mart369_payment.payment_provider_wallet'))

    def _mart369_tx(self, partner, amount=100, kind='order', provider=None, method=None):
        provider = provider or self.gateway
        method = method or self.env.ref('payment.payment_method_upi')
        return self.env['payment.transaction'].sudo().create({
            'provider_id': provider.id,
            'payment_method_id': method.id,
            'partner_id': partner.id,
            'amount': amount,
            'currency_id': self.env.company.currency_id.id,
            'operation': 'online_direct',
            'mart369_kind': kind,
        })


class Mart369PaymentCase(Mart369PaymentFixtures, TransactionCase):
    pass


class Mart369PaymentHttpCase(Mart369PaymentFixtures, HttpCase):
    pass
