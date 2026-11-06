"""Where a payment goes, and the cash limit.

Two things only.

**Cash on delivery is Odoo's own.** ``delivery`` already ships the method, the
provider and a compatibility rule that refuses cash unless the chosen carrier allows
it, so there is nothing to build - only a limit to set. The app checks
``COD_LIMIT = 5000`` in the browser (Checkout.jsx:576) against the amount left after
the wallet is applied, and both halves of that are client-side: a caller can claim a
wallet balance it does not have and talk its way past the check. Odoo already has the
right field, ``payment.provider.maximum_amount``, which ``_get_compatible_providers``
applies for us - so the limit becomes configuration on a provider an operator can
edit, measured against the cash actually to be collected.

**The 369 Wallet is a provider with no gateway**, because the money moves inside our
own ledger and there is nothing external to confirm.
"""

import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    # Only the wallet. 'cash_on_delivery' already exists, added by `delivery`.
    custom_mode = fields.Selection(selection_add=[('mart369_wallet', "369 Wallet")])

    mart369_is_cod = fields.Boolean(
        string="Is cash on delivery",
        compute='_compute_mart369_kinds', store=True, index='btree_not_null')
    mart369_is_wallet = fields.Boolean(
        string="Is the 369 Wallet",
        compute='_compute_mart369_kinds', store=True, index='btree_not_null')

    @api.depends('code', 'custom_mode')
    def _compute_mart369_kinds(self):
        for provider in self:
            custom = provider.code == 'custom'
            provider.mart369_is_cod = custom and provider.custom_mode == 'cash_on_delivery'
            provider.mart369_is_wallet = custom and provider.custom_mode == 'mart369_wallet'

    def _get_default_payment_method_codes(self):
        self.ensure_one()
        if self.custom_mode == 'mart369_wallet':
            return ['wallet']
        return super()._get_default_payment_method_codes()

    @api.model
    def _mart369_apply_cod_limit(self):
        """Set the cash limit on Odoo's own cash-on-delivery provider.

        Like the method tags, this cannot be plain XML: `delivery` creates the
        provider with noupdate set. It is applied only when no limit has been set
        at all, because the whole point of keeping COD_LIMIT here is that an
        operator may change it - and an upgrade must not quietly put it back.
        """
        provider = self.env.ref('delivery.payment_provider_cod', raise_if_not_found=False)
        if provider and not provider.maximum_amount:
            provider.sudo().write({'maximum_amount': 5000})
            _logger.info('mart369: cash on delivery limited to 5000')

    # ---------------------------------------------------------------- lookup

    @api.model
    def _mart369_provider_for(self, app_method, partner, amount, currency=None, order=None):
        """The provider that should take this payment, or an empty recordset.

        This is the whole of "provider-agnostic". It asks Odoo which providers the
        basket may use - which is where maximum_amount, currency, country and the
        carrier's cash-on-delivery rule are already applied - and then keeps the ones
        offering the method the customer picked. Enable payment_razorpay and it
        starts winning upi/card/netbanking without a line changing here.

        `order` matters for cash: delivery's own override refuses cash on delivery
        unless the order's carrier allows it, and it needs the order to find out.
        """
        currency = currency or self.env.company.currency_id
        compatible = self.sudo()._get_compatible_providers(
            self.env.company.id, partner.id, amount,
            currency_id=currency.id,
            sale_order_id=order.id if order else None)
        if not compatible:
            return self.browse()
        methods = self.env['payment.method'].sudo().search([
            ('mart369_app_code', '=', app_method),
        ])
        if not methods:
            return self.browse()
        matching = compatible.filtered(lambda p: methods & p.payment_method_ids)
        return matching.sorted('sequence')[:1] if matching else self.browse()
