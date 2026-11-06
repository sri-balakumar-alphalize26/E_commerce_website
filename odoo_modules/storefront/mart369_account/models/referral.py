"""Invites.

In the app an invite was a row pushed into localStorage that said "Invite sent
to X" and sent nothing (AccountExtras.jsx:856-864). Nothing ever moved it on
either: the three statuses existed in the UI but only `invited` could ever be
written, so no invite in the history could become a reward.

Here the customer can still only create an `invited` row. The two transitions
that matter belong to the server, because they are claims about things the
customer cannot vouch for: `joined` when somebody signs up with their code, and
`ordered` when that person's first order is really paid for.
"""

from odoo import api, fields, models

# The app's own three (REF_STATUS, AccountExtras.jsx:831-835). An unknown status
# crashes its row renderer, so nothing outside this list may ever be serialized.
STATE_CHOICES = [
    ('invited', 'Invited'),
    ('joined', 'Joined'),
    ('ordered', 'Ordered'),
]

REWARD_PARAM = 'mart369_account.referral_reward'
DEFAULT_REWARD = 100.0


class Mart369Referral(models.Model):
    _name = 'mart369.referral'
    _description = '369 Mart Referral'
    _order = 'create_date desc, id desc'
    _rec_name = 'name'

    partner_id = fields.Many2one(
        'res.partner', string='Invited by', required=True, ondelete='cascade', index=True)
    name = fields.Char(string='Friend', required=True)
    contact = fields.Char(
        string='Phone or email', help="How the invite was sent, when the app said.")
    state = fields.Selection(
        STATE_CHOICES, string='Status', required=True, default='invited', index=True,
        group_expand='_mart369_state_groups')
    joined_partner_id = fields.Many2one(
        'res.partner', string='Signed up as', ondelete='set null', copy=False)
    order_id = fields.Many2one(
        'sale.order', string='First order', ondelete='set null', copy=False)
    reward = fields.Float(string='Reward', default=0.0)
    currency_id = fields.Many2one(
        'res.currency', default=lambda self: self.env.company.currency_id)

    @api.model
    def _mart369_state_groups(self, states, domain):
        """Columns in the order an invite really progresses."""
        return [key for key, __ in STATE_CHOICES]

    # ------------------------------------------------------------- the money

    @api.model
    def _mart369_reward(self):
        """What one successful referral is worth.

        A setting rather than the constant the app hardcoded (REFER_REWARD = 100,
        accountStore.js:116), because it is the kind of number marketing changes
        without wanting a deployment.
        """
        raw = self.env['ir.config_parameter'].sudo().get_param(REWARD_PARAM)
        try:
            return float(raw) if raw else DEFAULT_REWARD
        except (TypeError, ValueError):
            return DEFAULT_REWARD

    # -------------------------------------------------------- transitions

    @api.model
    def _mart369_on_signup(self, partner, code):
        """Somebody signed up with a code: mark the inviter's row joined.

        Matched on the new customer rather than the name typed into the invite
        form, because those names are free text and two friends called Priya are
        not a reason to pay the wrong reward.
        """
        inviter = self.env['res.partner']._mart369_by_code(code)
        if not inviter or inviter == partner:
            return self.browse()
        partner.sudo().write({'mart369_referred_by_id': inviter.id})
        row = self.sudo().search([
            ('partner_id', '=', inviter.id),
            ('joined_partner_id', '=', partner.id),
        ], limit=1)
        if not row:
            row = self.sudo().search([
                ('partner_id', '=', inviter.id),
                ('state', '=', 'invited'),
                ('joined_partner_id', '=', False),
            ], limit=1)
        if row:
            row.sudo().write({'state': 'joined', 'joined_partner_id': partner.id})
            return row
        # Invited by word of mouth rather than through the app's form.
        return self.sudo().create({
            'partner_id': inviter.id,
            'name': partner.name or 'A friend',
            'state': 'joined',
            'joined_partner_id': partner.id,
        })

    @api.model
    def _mart369_on_first_order(self, order):
        """Their first paid order turns a joined invite into a rewarded one."""
        partner = order.partner_id
        if not partner or not partner.mart369_referred_by_id:
            return self.browse()
        row = self.sudo().search([
            ('joined_partner_id', '=', partner.id),
            ('state', '=', 'joined'),
        ], limit=1)
        if not row:
            return self.browse()
        reward = self._mart369_reward()
        row.sudo().write({'state': 'ordered', 'order_id': order.id, 'reward': reward})
        row._mart369_pay(reward)
        return row

    def _mart369_pay(self, amount):
        """Put the reward in the inviter's wallet, once."""
        self.ensure_one()
        if not amount:
            return False
        card = self.env['loyalty.card'].sudo()._mart369_wallet(self.partner_id)
        if not card:
            return False
        card._mart369_move(
            amount, 'reward', self.env._('Referral reward'),
            sub=self.env._('%s placed their first order', self.name or ''))
        return True

    # --------------------------------------------------------- serializing

    def _mart369_serialize(self):
        """One row of the app's `369mart.referrals` array."""
        self.ensure_one()
        return {
            'id': str(self.id),
            'name': self.name or '',
            'status': self.state,
            'at': int(self.create_date.timestamp() * 1000) if self.create_date else None,
        }
