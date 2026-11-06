"""Settings > Loyalty: whether online orders earn and spend points, and when
an order has earned them.

The rule itself - spend so much, earn so many, so many points to the rupee - is
the loyalty card's (`pos.loyalty.rule`, 369 Mart -> Loyalty -> Points Rules in
Odoo) and is shown here read-only, so there is one place it is edited.

The same step applies to orders made in Odoo's Sales, which have no app steps:
"Order placed" is when they are confirmed, and packed, out for delivery and
delivered all mean when their delivery is done (sale_order.py).
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError

# When an online order has earned its points, in the order an order gets there.
# `sale_order.py` compares positions in the order's own flow, so "packed" also
# covers an Express order, which is shipped rather than packed.
EARN_ON = [
    ('placed', 'Order placed'),
    ('packed', 'Packed or shipped'),
    ('out', 'Out for delivery'),
    ('delivered', 'Delivered'),
    ('settled', 'Return window closed'),
]
EARN_HINTS = {
    'placed': "As soon as it is paid for, or cash on delivery is accepted. "
              "A cancellation takes the points back.",
    'packed': "Once the store has packed or shipped it.",
    'out': "When it leaves with the rider.",
    'delivered': "When the customer has it. Cancelled orders never earn.",
    'settled': "A set number of days after delivery, once a return is no longer "
               "likely. Returns before then simply earn less.",
}


class Mart369Config(models.Model):
    _inherit = 'mart369.config'

    loyalty_enabled = fields.Boolean(
        string='Loyalty points on online orders', default=True)
    loyalty_redeem = fields.Boolean(
        string='Customers can spend points at checkout', default=True)
    loyalty_earn_on = fields.Selection(
        EARN_ON, string='Points are earned when', default='delivered', required=True)
    loyalty_settle_days = fields.Integer(
        string='Days after delivery', default=7,
        help="Used when points are earned once the return window closes.")

    # ------------------------------------------------------ settings screen

    @api.model
    def _mart369_admin_settings_groups(self):
        groups = super()._mart369_admin_settings_groups()
        config = self._get()
        rule = self.env['pos.loyalty.rule'].sudo().get_active_rule()
        shop = self.env['pos.loyalty.card.settings'].sudo().get_settings()
        groups['loyalty'] = {
            'enabled': bool(config.loyalty_enabled),
            'redeem': bool(config.loyalty_redeem),
            'earnOn': config.loyalty_earn_on or 'delivered',
            'settleDays': config.loyalty_settle_days,
            'options': [{'key': key, 'label': label, 'hint': EARN_HINTS[key]}
                        for key, label in EARN_ON],
            # Read-only here: the counter's rule and its master switch.
            'rule': rule._mart369_serialize() if rule else None,
            'shopOn': bool(shop.enable_loyalty),
            'currency': self.env['mart369.serializable']._mart369_currency(
                self.env.company.currency_id),
        }
        return groups

    @api.model
    def _mart369_admin_save_group(self, group, values):
        if group != 'loyalty':
            return super()._mart369_admin_save_group(group, values)
        vals = {}
        if 'enabled' in values:
            vals['loyalty_enabled'] = bool(values['enabled'])
        if 'redeem' in values:
            vals['loyalty_redeem'] = bool(values['redeem'])
        if 'earnOn' in values:
            if values['earnOn'] not in dict(EARN_ON):
                raise UserError(_('That is not a step an order can earn points at.'))
            vals['loyalty_earn_on'] = values['earnOn']
        if 'settleDays' in values:
            try:
                days = int(values['settleDays'])
            except (TypeError, ValueError):
                raise UserError(_('The number of days must be a whole number.'))
            if not 1 <= days <= 90:
                raise UserError(_('The number of days must be between 1 and 90.'))
            vals['loyalty_settle_days'] = days
        if vals:
            self._get().write(vals)
        return True
