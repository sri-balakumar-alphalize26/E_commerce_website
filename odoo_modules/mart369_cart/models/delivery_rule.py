"""What a delivery costs, and when the customer stops paying for it.

Replaces CART_RULES in components/home/Cart.jsx, which is four numbers per
storefront hard-coded into the bundle:

    quick: { minOrder: 99, freeAbove: 499, fee: 30, eta: "Delivery in 13 mins" }
    all:   { minOrder: 0,  freeAbove: 999, fee: 49, eta: "Delivery in 2-3 days" }

Not a ``delivery.carrier``. A carrier knows `free_over` and a price, but it has
no idea of a *minimum order*, and the app needs all four numbers together, per
storefront, before any order exists - on the cart page, where there is nothing
for a carrier to attach to. So the app-facing numbers live here, and a carrier
can be pointed at for when an order is really shipped.
"""

from odoo import api, fields, models
from odoo.exceptions import ValidationError

MODE_CHOICES = [
    ('quick', 'Quick'),
    ('all', 'Express'),
]


class Mart369DeliveryRule(models.Model):
    _name = 'mart369.delivery.rule'
    _description = '369 Mart Delivery Rule'
    _order = 'mode'
    _rec_name = 'label'

    mode = fields.Selection(
        MODE_CHOICES, string='Storefront', required=True,
        help="Quick is the 10-minute grocery run; Express ships over days.")
    label = fields.Char(
        string='Shown as', required=True, default='Quick',
        help="The word the app puts on the basket, e.g. Quick.")
    eta = fields.Char(
        string='Delivery promise', required=True, default='Delivery in 13 mins',
        help="The line under the basket heading, e.g. Delivery in 13 mins. "
             "A pincode with its own promise overrides this.")
    min_order = fields.Float(
        string='Minimum order', default=0.0,
        help="Below this the customer cannot pay. 0 means no minimum.")
    free_above = fields.Float(
        string='Free delivery above', default=0.0,
        help="Spend this much in this storefront and delivery is free. "
             "0 means delivery is never free.")
    fee = fields.Float(
        string='Delivery fee', default=0.0,
        help="Charged once per storefront when the basket is below the "
             "free-delivery amount.")
    carrier_id = fields.Many2one(
        'delivery.carrier', string='Carrier', ondelete='set null',
        help="Optional. Which Odoo carrier actually ships this, once an order "
             "exists. The numbers above are what the app shows.")
    active = fields.Boolean(default=True)

    _mode_uniq = models.Constraint(
        'unique (mode)',
        'There is already a rule for that storefront.',
    )

    @api.constrains('min_order', 'free_above', 'fee')
    def _check_amounts(self):
        for rule in self:
            if rule.min_order < 0 or rule.free_above < 0 or rule.fee < 0:
                raise ValidationError(self.env._(
                    'Delivery amounts cannot be negative.'))

    # -------------------------------------------------------------- reading

    @api.model
    def _mart369_rules(self):
        """{'quick': rule, 'all': rule} - every storefront the app knows."""
        found = {}
        for rule in self.sudo().search([]):
            found[rule.mode] = rule
        return found

    def _mart369_serialize(self):
        """One entry of CART_RULES, field for field."""
        self.ensure_one()
        return {
            'label': self.label or '',
            'eta': self.eta or '',
            'minOrder': round(self.min_order or 0.0, 2),
            'freeAbove': round(self.free_above or 0.0, 2),
            'fee': round(self.fee or 0.0, 2),
        }

    # -------------------------------------------------------- the console

    def _mart369_admin_row(self):
        """One rule as the app's own admin console draws it.

        Not `_mart369_serialize`. That is the shopper's shape - four numbers
        and two lines of text, with no id and no notion of being switched off,
        because a customer has no use for either. A screen that edits the
        record needs both, and widening the shopper's serializer to carry them
        would put a storefront's internals in every basket response.
        """
        self.ensure_one()
        return {
            'id': self.id,
            'mode': self.mode,
            'modeLabel': dict(MODE_CHOICES).get(self.mode, self.mode or ''),
            'label': self.label or '',
            'eta': self.eta or '',
            'minOrder': round(self.min_order or 0.0, 2),
            'freeAbove': round(self.free_above or 0.0, 2),
            'fee': round(self.fee or 0.0, 2),
            'active': self.active,
        }

    @api.model
    def mart369_admin_list(self):
        """Everything the delivery screens draw, in one answer.

        Read by both of them - the desk in Odoo through the ORM, the app's
        admin console through `/369mart/admin/delivery` - on purpose, and for
        the reason the deals desk gives: staff who work in Odoo must not get a
        different answer to "what does delivery cost" than staff who work in
        the console. Two assemblers would drift the first time one of them
        learned to count something.

        All three lists come back together because they are one screen. Fees,
        slots and areas are three tabs of it, none of them long, and fetching
        them apart would mean three round trips and three chances for the tabs
        to disagree about how fresh they are.

        On the rule model rather than a model of its own: something has to own
        the assembling, and delivery starts with what it costs. Each record
        still serializes itself - this only puts the three lists in one
        envelope.
        """
        slots = self.env['mart369.delivery.slot'].with_context(active_test=False)
        areas = self.env['mart369.service.area'].with_context(active_test=False)
        rules = self.with_context(active_test=False).search([])
        slot_rows = slots.search([])
        area_rows = areas.search([])
        return {
            'rules': [r._mart369_admin_row() for r in rules],
            'slots': [s._mart369_admin_row() for s in slot_rows],
            'areas': [a._mart369_admin_row() for a in area_rows],
            # The words for the two choice rows travel with the lists, so
            # neither screen keeps its own copy of what a storefront is
            # called - and a third storefront would appear in both at once.
            'modes': [{'key': key, 'label': label} for key, label in MODE_CHOICES],
            'kinds': [{'key': key, 'label': label}
                      for key, label in self.env['mart369.delivery.slot']._fields['kind'].selection],
            # Which money these amounts are in, travelling with them.
            'currency': self.env['mart369.serializable']._mart369_currency(),
            'counts': {
                'rules': len(rules.filtered('active')),
                'slots': len(slot_rows.filtered('active')),
                'areas': len(area_rows.filtered('active')),
            },
        }
