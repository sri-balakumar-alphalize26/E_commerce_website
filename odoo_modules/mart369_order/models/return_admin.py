"""Returns, as a queue somebody works through.

The model next door (order_return.py) knows how a return moves. What it does
not have is a shape any screen can list: `_mart369_serialize` is written for
the customer's own tracking page, so it carries no order number, no customer
and no idea what the next step is called. A queue needs all three.

The one rule worth repeating from the orders desk: **the screen never works
out what happens next**. `next: {state, label}` and `flow` come from here, so
the button's words and the ladder it draws cannot drift from what pressing it
actually does.

In its own file rather than inside order_admin.py, because that file is being
worked on elsewhere and two people editing one file is how a morning is lost.
"""

from odoo import api, models

from odoo.addons.mart369_order.models.order_return import (
    RETURN_FLOW, RETURN_STATES,
)

# What the button says at each step. The label describes the *action*, not the
# state it lands in: an operator presses "Send to pickup", they do not press
# "Pickup scheduled".
NEXT_LABEL = {
    'requested': 'Schedule pickup',
    'pickup': 'Mark picked up',
    'picked': 'Issue refund',
}

STATE_LABEL = dict(RETURN_STATES)

# The states a return is still somebody's problem.
OPEN_STATES = ('requested', 'pickup', 'picked')

TABS = {
    'needs': [('state', 'in', list(OPEN_STATES))],
    'requested': [('state', '=', 'requested')],
    'pickup': [('state', '=', 'pickup')],
    'picked': [('state', '=', 'picked')],
    'done': [('state', '=', 'done')],
    'refused': [('state', '=', 'refused')],
    'all': [],
}

MAX_ROWS = 100


class Mart369OrderReturnAdmin(models.Model):
    _inherit = 'mart369.order.return'

    # ------------------------------------------------------------ one return

    def _mart369_admin_next(self):
        """The step after this one, as the screen should offer it."""
        self.ensure_one()
        nxt = self._mart369_next_state()
        if not nxt:
            return None
        # Keyed by the state being *left*, because the label is the action
        # taken from here. Looking it up by the state it lands in shifts every
        # button one step: a return still waiting to be collected offered
        # "Mark picked up", which is the step after the one it needs.
        return {'state': nxt,
                'label': self.env._(NEXT_LABEL.get(self.state, 'Move on'))}

    def _mart369_refund_split(self):
        """How much of the money this screen can actually put back.

        `_mart369_refund` returns the wallet leg and leaves anything taken by a
        gateway to the gateway's own refund - a finance decision, deliberately
        not an operator's button. So the screen has to say which is which, or
        somebody reads "refunded", closes the ticket, and the customer is still
        out of pocket.
        """
        self.ensure_one()
        order = self.order_id
        amount = self.amount or order.amount_total
        wallet = min(amount, order.mart369_wallet_used or 0.0)
        return {
            'total': order.currency_id.round(amount),
            'wallet': order.currency_id.round(wallet),
            'gateway': order.currency_id.round(max(0.0, amount - wallet)),
            'method': order.mart369_method or '',
        }

    def _mart369_admin_row(self):
        """One return, as the queue lists it."""
        self.ensure_one()
        order = self.order_id
        partner = self.partner_id
        return {
            'id': str(self.id),
            'ref': order.mart369_ref or '',
            'who': partner.display_name or '',
            'phone': partner.phone or '',
            'kind': self.kind,
            'state': self.state,
            'stateLabel': self.env._(STATE_LABEL.get(self.state, self.state)),
            'reason': self.reason or '',
            'photos': len(self.photo_ids),
            'amount': order.currency_id.round(self.amount or 0.0),
            # The whole currency, not its name. The app formats what it is
            # told to - code, symbol, position, decimals - so a bare string
            # prints an amount with no symbol at all. Built by the same helper
            # the orders board uses, so the two screens cannot disagree about
            # what money looks like.
            'currency': self.env['mart369.serializable']._mart369_currency(
                order.currency_id),
            'at': int(self.create_date.timestamp() * 1000) if self.create_date else None,
            'next': self._mart369_admin_next(),
            # Refusing is refused once the money has gone back, so the screen
            # hides the button rather than offering one the model will reject.
            'canRefuse': self.state != 'done',
        }

    def _mart369_admin_detail(self):
        """One return, opened."""
        self.ensure_one()
        order = self.order_id
        row = self._mart369_admin_row()
        row.update({
            # Free text on purpose: the app flattens the chosen items and the
            # pickup slot into this one string, so there is nothing structured
            # to offer and pretending otherwise would invent data.
            'detail': self.detail or '',
            'flow': [{'state': s, 'label': self.env._(STATE_LABEL.get(s, s))}
                     for s in RETURN_FLOW],
            'refund': self._mart369_refund_split(),
            'order': {
                'ref': order.mart369_ref or '',
                'state': order.mart369_state or '',
                'total': order.currency_id.round(order.amount_total),
                'at': int(order.create_date.timestamp() * 1000)
                      if order.create_date else None,
            },
            'photoIds': self.photo_ids.ids,
        })
        return row

    # ----------------------------------------------------------- the queue

    @api.model
    def _mart369_admin_find(self, return_id):
        """One return by id, or an empty recordset. Never raises on rubbish."""
        try:
            ident = int(return_id)
        except (TypeError, ValueError):
            return self.browse()
        return self.browse(ident).exists()

    @api.model
    def mart369_returns_counts(self):
        """A number per tile. The orders board has one flat `returnsOpen`,
        which cannot fill five tiles."""
        counts = {}
        for tab, domain in TABS.items():
            counts[tab] = self.search_count(domain)
        return counts

    @api.model
    def mart369_returns_list(self, tab='needs', kind=None, q='',
                             sort='old', limit=25, offset=0):
        """The queue, as the screen asks for it."""
        domain = list(TABS.get(tab or 'needs', TABS['needs']))
        if kind in ('refund', 'replace'):
            domain += [('kind', '=', kind)]
        term = (q or '').strip()
        if term:
            domain += ['|', '|',
                       ('order_ref', 'ilike', term),
                       ('partner_id.name', 'ilike', term),
                       ('reason', 'ilike', term)]
        order = 'create_date asc, id asc' if sort == 'old' else 'create_date desc, id desc'
        count = min(max(int(limit or 25), 1), MAX_ROWS)
        found = self.search(domain, order=order, limit=count, offset=max(int(offset or 0), 0))
        return {
            'returns': [r._mart369_admin_row() for r in found],
            'total': self.search_count(domain),
            'counts': self.mart369_returns_counts(),
            'limit': count,
            'offset': int(offset or 0),
        }

    # ----------------------------------------------------------- the writes

    @api.model
    def mart369_returns_detail(self, return_id):
        record = self._mart369_admin_find(return_id)
        return record._mart369_admin_detail() if record else {}

    @api.model
    def mart369_returns_advance(self, return_id):
        """Move a return on a step. Raises what the model raises."""
        record = self._mart369_admin_find(return_id)
        if not record:
            raise ValueError(self.env._('No such return.'))
        record.mart369_action_advance()
        return record._mart369_admin_detail()

    @api.model
    def mart369_returns_refuse(self, return_id):
        record = self._mart369_admin_find(return_id)
        if not record:
            raise ValueError(self.env._('No such return.'))
        record.mart369_action_refuse()
        return record._mart369_admin_detail()
