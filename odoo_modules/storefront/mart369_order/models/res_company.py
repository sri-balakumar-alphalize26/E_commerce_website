"""Which tax 369 Mart orders carry.

Deliberately a setting rather than a guess. The app quotes prices with tax in
them, the way Indian retail does, so the order total has to equal the number the
customer was shown to the paisa. Picking a tax automatically would either break
that equality or put the wrong rate on an invoice, and both are worse than
asking once.

Left empty, orders carry no tax and the invoice carries no GST - exactly where
things stood before this module. Set to a price-included tax, GST is split out
on the invoice and the customer still pays what the app said.
"""

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    mart369_tax_id = fields.Many2one(
        'account.tax', string='369 Mart tax',
        domain="[('type_tax_use', '=', 'sale'), ('company_id', '=', id)]",
        help="The tax put on 369 Mart order lines. It must be set to "
             "'Included in price'. Leave empty for no tax.")

    # The 369 Wallet in the books (wallet_books.py). Filled in on install with
    # accounts of its own; an accountant may point them elsewhere.
    mart369_wallet_account_id = fields.Many2one(
        'account.account', string='369 Wallet balances account',
        domain="[('account_type', '=', 'liability_current')]",
        help="What the shop owes its customers in their 369 Wallets. Every "
             "wallet top-up, refund and reward is credited here; spending is "
             "debited.")
    mart369_wallet_reward_account_id = fields.Many2one(
        'account.account', string='369 Wallet rewards account',
        domain="[('account_type', 'in', ('expense', 'expense_direct_cost'))]",
        help="Where scratch-card prizes, referral rewards and goodwill credits "
             "paid into wallets are charged.")
