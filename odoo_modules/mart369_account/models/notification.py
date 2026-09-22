"""The notification list.

The app did not store notifications. It *computed* them on every render -
`orderNotifs(orders)` in accountStore.js:102-113 turned each order into one
notification based on its current status, and concatenated three hardcoded
promotional ones. Only which ids had been read or dismissed was kept.

So this is not a matter of moving a table across: the server has to build the
same list, from real orders, and keep the ids byte-identical to the ones the
browser was generating - `n-<order ref>-<status>` - or every customer's read
state is lost the day this is switched on.

Promotional notifications are records, because somebody has to write them.
Order notifications are derived, because an order already knows where it is.
"""

from odoo import api, fields, models

TYPE_CHOICES = [
    ('offer', 'Offer'),
    ('order', 'Order'),
    ('wallet', 'Wallet'),
]

# status -> (suffix, title, text template, where tapping it goes).
# Straight from accountStore.js:106-110, wording included: a customer should not
# be able to tell the day this stopped being computed in their browser.
ORDER_NOTES = {
    'out': ('out', "Your order is on the way",
            "%(ref)s is out for delivery. %(eta)s", 'track'),
    'shipped': ('shipped', "Order shipped",
                "%(ref)s has been handed to our delivery partner.", 'track'),
    'delivered': ('delivered', "Delivered · rate your order",
                  "How was %(ref)s? Tell us in a moment.", 'reviews'),
    'cancelled': ('cancelled', "Order cancelled",
                  "%(ref)s was cancelled. Any refund is on its way.", 'track'),
    'placed': ('placed', "Order confirmed",
               "%(ref)s is confirmed. %(eta)s", 'track'),
    'packed': ('placed', "Order confirmed",
               "%(ref)s is confirmed. %(eta)s", 'track'),
}


class Mart369Notice(models.Model):
    """A promotional notification an operator writes."""
    _name = 'mart369.notice'
    _description = '369 Mart Notification'
    _order = 'publish_at desc, id desc'

    name = fields.Char(string='Title', required=True)
    text = fields.Text(string='Text', required=True)
    kind = fields.Selection(TYPE_CHOICES, string='Kind', required=True, default='offer')
    publish_at = fields.Datetime(
        string='Show from', required=True, default=fields.Datetime.now)
    until = fields.Datetime(string='Show until')
    active = fields.Boolean(default=True)

    go_view = fields.Char(
        string='Opens', default='offers',
        help="Which app screen tapping it opens, e.g. offers, or account.")
    go_param = fields.Char(
        string='Opens with', help="The second part, e.g. rewards for account.")

    def _mart369_serialize(self):
        self.ensure_one()
        go = [self.go_view or 'offers']
        if self.go_param:
            go.append(self.go_param)
        return {
            'id': 'n-notice-%s' % self.id,
            'type': self.kind,
            'title': self.name or '',
            'text': self.text or '',
            'at': int(self.publish_at.timestamp() * 1000) if self.publish_at else None,
            'go': go,
        }


class Mart369Notifications(models.AbstractModel):
    """Builds the list the app draws."""
    _name = 'mart369.notifications'
    _description = '369 Mart Notification Feed'

    @api.model
    def _mart369_for(self, partner, limit=60):
        """Everything this customer should see, newest first."""
        state = {
            'read': partner._mart369_ids('mart369_read_ids'),
            'dismissed': partner._mart369_ids('mart369_dismissed_ids'),
        }
        rows = self._mart369_order_notes(partner) + self._mart369_notices(partner)
        rows = [row for row in rows if row['id'] not in state['dismissed']]
        rows.sort(key=lambda r: r['at'] or 0, reverse=True)
        rows = rows[:limit]
        for row in rows:
            row['read'] = row['id'] in state['read']
        return {'notifications': rows, 'read': state['read'],
                'dismissed': state['dismissed']}

    @api.model
    def _mart369_order_notes(self, partner):
        """One notification per order, from where the order really is."""
        orders = self.env['sale.order'].sudo().search([
            ('partner_id', '=', partner.id),
            ('mart369_ref', '!=', False),
            ('mart369_state', 'not in', (False, 'draft')),
        ], order='mart369_placed_at desc', limit=40)

        out = []
        for order in orders:
            note = ORDER_NOTES.get(order.mart369_state)
            if not note:
                continue
            suffix, title, template, goes = note
            when = order.mart369_placed_at or order.create_date
            stamp = order.mart369_stamp_ids.filtered(
                lambda s: s.state == order.mart369_state)[:1]
            if stamp and stamp.at:
                # When it really reached this step, rather than the app's guess
                # of "placed plus six minutes".
                when = stamp.at
            go = ['track', order.mart369_ref]
            if goes == 'reviews':
                go = ['account', 'reviews']
            out.append({
                'id': 'n-%s-%s' % (order.mart369_ref, suffix),
                'type': 'order',
                'title': title,
                'text': template % {'ref': order.mart369_ref or '',
                                    'eta': order.mart369_eta or ''},
                'at': int(when.timestamp() * 1000) if when else None,
                'go': go,
            })
        return out

    @api.model
    def _mart369_notices(self, partner):
        """The promotional ones, honouring what the customer asked not to see."""
        now = fields.Datetime.now()
        domain = [('publish_at', '<=', now),
                  '|', ('until', '=', False), ('until', '>=', now)]
        # 'order' carries no preference and never did, so it was never in
        # this list - which meant a notice staff saved as an order one was
        # filtered out for every customer, silently, with a screen offering
        # them the kind. It belongs here because it is operational rather than
        # marketing: the order notes above are already shown to everybody, and
        # a notice about orders follows the same rule. The two that a customer
        # can switch off stay switched off.
        allowed = ['order']
        if partner.mart369_notify_offers:
            allowed.append('offer')
        if partner.mart369_notify_wallet:
            allowed.append('wallet')
        domain.append(('kind', 'in', allowed))
        return [notice._mart369_serialize()
                for notice in self.env['mart369.notice'].sudo().search(domain, limit=20)]
