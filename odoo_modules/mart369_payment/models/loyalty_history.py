"""One line of the 369 Wallet ledger.

Odoo's own ``loyalty.history`` already carries the amounts and - importantly - an
``order_model``/``order_id`` reference pair. The app has no such field: it writes the
order into the free-text subtitle and then digs it back out with a regular
expression, ``/#(369[ME]-\\d+)/`` (AccountExtras.jsx:240), to make the row clickable.

So the subtitle keeps saying "Order #369M-...", because the app still reads it that
way and the UI must not change - but it stops being the only copy. The reference
fields are the real link, and the day the storefront is wired to them the regex can
go without anything else moving.
"""

from odoo import api, fields, models

from .loyalty_card import KINDS


class LoyaltyHistory(models.Model):
    _inherit = 'loyalty.history'

    mart369_kind = fields.Selection(
        KINDS, string="Kind", index='btree_not_null',
        help="Which of the app's four ledger words this movement is.")
    mart369_title = fields.Char(string="Title")
    mart369_sub = fields.Char(string="Subtitle")

    @api.model_create_multi
    def create(self, vals_list):
        # loyalty.history.description is required and shows on Odoo's own screens.
        # Build it from our two lines so an operator reading the standard view sees
        # the same sentence the customer sees in the app.
        for values in vals_list:
            if not values.get('description'):
                parts = [values.get('mart369_title'), values.get('mart369_sub')]
                description = ' - '.join(p for p in parts if p)
                if description:
                    values['description'] = description
        return super().create(vals_list)

    def unlink(self):
        """The wallet ledger is never deleted.

        `sale_loyalty` removes every history row pointing at an order when the
        order is cancelled - the right thing for points earned on it, and the
        wrong thing here: cancelling a paid order erased the customer's own
        "Order cancelled" refund row, so the app's history lost the money
        coming back and the balance no longer matched its ledger. Rows with a
        kind are the 369 Wallet's and are kept; everything else is Odoo's.
        """
        return super(LoyaltyHistory, self.filtered(lambda h: not h.mart369_kind)).unlink()

    def _mart369_serialize(self):
        """Exactly the six keys AccountExtras.jsx renders, and nothing else.

        `amount` is always positive and `kind` carries the sign, because that is
        what KIND_META (AccountExtras.jsx:129) expects. `id` is a string because
        the app compares ids with ===. `at` is milliseconds, for fmtDateTime.
        """
        self.ensure_one()
        return {
            'id': str(self.id),
            'kind': self.mart369_kind or 'add',
            'amount': self.issued or self.used,
            'title': self.mart369_title or self.description or '',
            'sub': self.mart369_sub or '',
            'at': int(self.create_date.timestamp() * 1000) if self.create_date else 0,
        }
