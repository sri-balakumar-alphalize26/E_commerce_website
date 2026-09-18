"""What the bot knows.

`botReplies.js` was sixteen regexes and their answers compiled into the
storefront bundle, and `OrderTrack.jsx` had six more of its own. Changing a
delivery fee meant a deployment, and because nobody wanted to do that twice the
two scripts drifted: one bot said an order was "being packed", the other "being
prepared"; one promised an agent in two minutes, the other in thirty.

A rule is a record here, so there is one set of answers and an operator can fix
a wrong one without waiting for anybody.

Two kinds of rule:

* **`static`** - the answer is the text on the record. Most of them.
* **everything else** - the answer is computed, because it depends on this
  customer's orders, their wallet, or what delivery actually costs today. The
  `kind` names a handler on `mart369.bot`; the record still holds the wording
  around the numbers.
"""

from odoo import api, fields, models

# A handler for each of these lives on mart369.bot as _mart369_answer_<kind>.
KIND_CHOICES = [
    ('static', 'Fixed answer'),
    ('order', 'About one order they named'),
    ('track', 'Where their orders are'),
    ('refund', 'A refund they are waiting for'),
    ('cancel', 'Cancelling an order'),
    ('return', 'Returning something'),
    ('payment', 'A payment problem'),
    ('delivery', 'Delivery charges and minimums'),
    ('coupons', 'Current coupon codes'),
    ('wallet', 'Their wallet balance'),
    ('agent', 'Hand over to a person'),
]


class Mart369BotRule(models.Model):
    _name = 'mart369.bot.rule'
    _description = '369 Mart Support Answer'
    _order = 'sequence, id'
    _rec_name = 'title'

    sequence = fields.Integer(
        default=10,
        help="First match wins, so the order matters. A broad rule placed high "
             "will swallow the narrow ones under it.")
    title = fields.Char(
        string='What it covers', required=True,
        help="For operators reading this list. The customer never sees it.")
    pattern = fields.Char(
        string='Matches', required=True,
        help="A regular expression, tested against what the customer typed in "
             "lower case. For example: refund|money back")
    kind = fields.Selection(
        KIND_CHOICES, string='Answer', required=True, default='static')
    reply = fields.Text(
        string='Says',
        help="What the bot replies. For a computed answer this is the wording "
             "around the numbers; %(…)s placeholders are filled in.")
    reply_alt = fields.Text(
        string='Says instead',
        help="The other branch of a computed answer - for instance when they "
             "have no orders on the way, or no refund is pending.")

    chips = fields.Char(
        string='Suggestions',
        help="Comma separated. They appear as tappable chips, and tapping one "
             "sends that exact text back - so each must be something these "
             "rules can match.")
    action_label = fields.Char(string='Button')
    action_view = fields.Char(
        string='Button opens',
        help="An app screen: track, account, offers.")
    action_param = fields.Char(
        string='Button opens with',
        help="For account: wallet, orders, payments, address, reviews.")

    active = fields.Boolean(default=True)

    @api.model
    def _mart369_rules(self):
        """Every live rule, in the order they are tried."""
        return self.sudo().search([])

    def _mart369_chips(self):
        self.ensure_one()
        return [chip.strip() for chip in (self.chips or '').split(',') if chip.strip()]

    def _mart369_action(self, param=None):
        """The one button this rule offers, if it offers one.

        `go` is [view] or [view, param] - the shape onNav() is called with.
        """
        self.ensure_one()
        if not self.action_label or not self.action_view:
            return None
        go = [self.action_view]
        value = param if param is not None else self.action_param
        if value:
            go.append(value)
        return {'label': self.action_label, 'go': go}
