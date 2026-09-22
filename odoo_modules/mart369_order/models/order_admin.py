"""What the app's own admin console reads.

The console at /admin/orders is not the backend board. It is the screen a store
manager keeps open all morning, on a phone or a laptop in the shop, and it asks
a different question: not "show me the orders" but "what do I pack next".

Two things are kept apart here on purpose.

**The shopper's serializer is not widened.** `_mart369_serialize()` is what a
customer's own app receives; growing it to carry a phone number and a delivery
promise so that one staff screen can read them is how a customer payload ends
up leaking the next customer's. The console gets its own shape, built here.

**The ladder is the server's.** A quick order goes placed -> packed -> out and
an express one placed -> shipped -> out; a flat list of statuses cannot say
that, and a console that guesses the next step will be refused by the
constraint on `sale.order`. So the payload tells the screen what the next step
is called, and the screen only draws it.
"""

from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError

from .sale_order import LIVE_STATES

# The label for the button that moves an order on one step, by the state it is
# in now. Two of them read the same because "out for delivery" follows both
# packing (quick) and shipping (express) - the difference is which one the
# order's own flow offers, and that is decided by `_mart369_next_state`.
NEXT_LABEL = {
    'placed': {'quick': 'Start packing', 'all': 'Mark shipped'},
    'packed': {'quick': 'Send out', 'all': 'Send out'},
    'shipped': {'quick': 'Send out', 'all': 'Send out'},
    'out': {'quick': 'Mark delivered', 'all': 'Mark delivered'},
}

# Which orders each tab of the console is asking for. 'needs' is the one the
# screen opens on: everything still on its way, oldest first.
TABS = {
    'needs': [('mart369_state', 'in', list(LIVE_STATES))],
    'placed': [('mart369_state', '=', 'placed')],
    'packing': [('mart369_state', 'in', ('packed', 'shipped'))],
    'out': [('mart369_state', '=', 'out')],
    'late': [('mart369_late', '=', True)],
    'cash': [('mart369_state', 'in', list(LIVE_STATES)), ('mart369_method', '=', 'cod')],
    'delivered': [('mart369_state', '=', 'delivered')],
    'cancelled': [('mart369_state', '=', 'cancelled')],
    # The board's `has_return` filter, as a tab. The one named filter on the
    # backend search view that the queue had no answer for.
    'returns': [('mart369_return_count', '>', 0)],
    'all': [],
}

SORTS = {
    'old': 'mart369_placed_at asc, id asc',
    'new': 'mart369_placed_at desc, id desc',
    'value': 'amount_total desc, id desc',
}

MAX_ROWS = 100

# What an operator may pick from when cancelling. A free-text box would put
# whatever was typed onto the customer's own tracking screen. Here rather than
# in the controller because both front ends offer the same list.
CANCEL_REASONS = [
    'Item out of stock',
    'Customer asked to cancel',
    'Address not reachable',
    'Payment not confirmed',
    'Store closed',
]


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # ------------------------------------------------------------- searching

    @api.model
    def _mart369_admin_domain(self, tab=None, mode=None, when=None, q=None):
        """The console's list, as a domain.

        Filtered here rather than in the browser. The sample screen this
        replaces shipped every order to the client and filtered there, which
        works at three hundred orders and stops working at three thousand.
        """
        domain = self._mart369_board_domain()
        domain += TABS.get(tab or 'needs', TABS['needs'])
        if mode in ('quick', 'all'):
            domain += [('mart369_mode', '=', mode)]
        if when in ('today', '7d'):
            today = fields.Date.context_today(self)
            days = 0 if when == 'today' else 6
            since = fields.Datetime.to_datetime(today - timedelta(days=days))
            domain += [('mart369_placed_at', '>=', since)]
        term = (q or '').strip()
        if term:
            domain += ['|', '|',
                       ('mart369_ref', 'ilike', term),
                       ('partner_id.name', 'ilike', term),
                       ('partner_id.phone', 'ilike', term)]
        return domain

    @api.model
    def mart369_admin_list(self, tab=None, mode=None, when=None, q=None,
                           sort=None, limit=30, offset=0):
        """One page of the console's list, plus how many there are in total."""
        domain = self._mart369_admin_domain(tab=tab, mode=mode, when=when, q=q)
        limit = max(1, min(int(limit or 30), MAX_ROWS))
        offset = max(0, int(offset or 0))
        order = SORTS.get(sort or 'old', SORTS['old'])
        orders = self.search(domain, limit=limit, offset=offset, order=order)
        return {
            'orders': [o._mart369_admin_row() for o in orders],
            'total': self.search_count(domain),
            'limit': limit,
            'offset': offset,
            # Shipped with the list so neither screen keeps its own copy.
            'reasons': CANCEL_REASONS,
        }

    @api.model
    def mart369_admin_counts(self):
        """The five tiles, and the number on each tab.

        Counted the same way the backend board counts them - same base domain,
        same states - so a manager who has both open is never told two
        different numbers for the same thing.
        """
        base = self._mart369_board_domain()
        currency = self.env.company.currency_id
        cash = self.search(base + TABS['cash'])
        counts = {
            key: self.search_count(base + where)
            for key, where in TABS.items() if key != 'cash'
        }
        counts['cash'] = len(cash)
        return {
            'counts': counts,
            'cashDue': currency.format(self._mart369_in_company_currency(cash)),
            # How many of those returns are still open, which is not the same
            # as how many orders have one - hence its own name.
            'returnsOpen': self.env['mart369.order.return'].search_count(
                [('state', 'in', ('requested', 'pickup', 'picked'))]),
        }

    # ------------------------------------------------------------- one order

    @api.model
    def _mart369_admin_find(self, ref):
        """One order by the number both screens show.

        By reference rather than id for the same reason the shopper API does
        it: that is what is on the screen, in the URL and on the label, and it
        does not walk 1, 2, 3. Not sudo'd, so Odoo's access rules apply.
        """
        if not ref or not isinstance(ref, str):
            return self.browse()
        return self.search(
            self._mart369_board_domain() + [('mart369_ref', '=', ref)], limit=1)

    @api.model
    def mart369_admin_detail(self, ref):
        """Everything the panel draws, or {} if there is no such order.

        Public because the backend screen reaches these over `orm.call`, which
        refuses a name starting with an underscore.
        """
        order = self._mart369_admin_find(ref)
        return order._mart369_admin_detail() if order else {}

    @api.model
    def mart369_admin_advance(self, ref):
        """Move the order on by one step and hand back what it became.

        Which step that is belongs to the order. This does not know the ladder
        and must not learn it - a second copy is a second thing to get wrong.
        """
        order = self._mart369_admin_find(ref)
        if not order:
            raise UserError(self.env._('There is no such order.'))
        order.mart369_action_advance()
        return order._mart369_admin_detail()

    @api.model
    def mart369_admin_cancel(self, ref, reason=None):
        """Cancel the order and give the money back."""
        order = self._mart369_admin_find(ref)
        if not order:
            raise UserError(self.env._('There is no such order.'))
        if reason not in CANCEL_REASONS:
            raise UserError(self.env._('Pick a reason for the cancellation.'))
        order._mart369_cancel(reason=reason)
        return order._mart369_admin_detail()

    # ----------------------------------------------------------- serializing

    def _mart369_admin_row(self):
        """One line of the list. Everything the row draws, and nothing more."""
        self.ensure_one()
        placed = self.mart369_placed_at or self.create_date
        partner = self.partner_shipping_id or self.partner_id
        return {
            'ref': self.mart369_ref or str(self.id),
            'at': int(placed.timestamp() * 1000) if placed else None,
            'mode': self.mart369_mode or 'quick',
            'state': self.mart369_state or 'placed',
            'late': bool(self.mart369_late),
            'dueAt': (int(self.mart369_due_at.timestamp() * 1000)
                      if self.mart369_due_at else None),
            'customer': {
                'name': self.partner_id.name or '',
                'phone': self.partner_id.phone or '',
                'area': partner.street2 or partner.city or '',
            },
            'itemCount': len(self._mart369_app_lines()),
            'total': self.currency_id.round(self.amount_total),
            'currency': self.env['mart369.serializable']._mart369_currency(
                self.currency_id),
            'method': self.mart369_method or '',
            'payNote': self.mart369_pay_note or '',
            'slot': self.mart369_slot_label or '',
            'eta': self.mart369_eta or '',
            # Worked out here because only the order knows its own flow.
            'next': self._mart369_admin_next(),
            'canCancel': self.mart369_state == 'placed',
        }

    def _mart369_admin_next(self):
        """{state, label} for the row's button, or None at the end of the line."""
        self.ensure_one()
        if self.mart369_state == 'cancelled':
            return None
        nxt = self._mart369_next_state()
        if not nxt:
            return None
        mode = self.mart369_mode or 'quick'
        label = NEXT_LABEL.get(self.mart369_state or '', {}).get(mode)
        return {'state': nxt, 'label': label or 'Move on'}

    def _mart369_admin_detail(self):
        """The drawer: the row, plus everything worth opening it for."""
        self.ensure_one()
        row = self._mart369_admin_row()
        partner = self.partner_shipping_id
        row.update({
            'items': [{'name': snap['name'], 'price': snap['price'], 'qty': qty}
                      for __, qty, snap in self._mart369_app_lines()],
            'bill': self._mart369_bill_snapshot(),
            'paid': self.currency_id.round(self.mart369_paid or 0.0),
            'walletUsed': self.currency_id.round(self.mart369_wallet_used or 0.0),
            'txn': self.mart369_txn or '',
            'coupon': self.mart369_coupon_id.code if self.mart369_coupon_id else None,
            'address': partner._mart369_serialize() if partner else None,
            'instructions': self.mart369_instructions or '',
            'whatsapp': bool(self.mart369_whatsapp),
            # The ladder this order is actually on, so the drawer draws four
            # steps with the right middle one rather than guessing from `mode`.
            'flow': self._mart369_flow(),
            'timeline': [s._mart369_serialize() for s in self.mart369_stamp_ids],
            'returns': [r._mart369_serialize() for r in self.mart369_return_ids],
            # When the code was issued and whether it has been used. Never the
            # code, and never the hash: a manager needs to know the customer
            # has one, not to be able to open their own door with it.
            'otp': {
                'issuedAt': (int(self.mart369_otp_at.timestamp() * 1000)
                             if self.mart369_otp_at else None),
                'usedAt': (int(self.mart369_otp_used_at.timestamp() * 1000)
                           if self.mart369_otp_used_at else None),
            },
            'hasInvoice': bool(self.invoice_ids.filtered(
                lambda m: m.state == 'posted')),
        })
        # One extra query, and only when somebody opened the drawer - not once
        # per row of a list nobody has clicked on.
        row['customer']['orderCount'] = self.search_count(
            self._mart369_board_domain() + [('partner_id', '=', self.partner_id.id)])
        return row
