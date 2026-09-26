from odoo import models, fields, api


class LoyaltyHistory(models.Model):
    _name = 'pos.loyalty.history'
    _description = 'Loyalty Points History'
    _order = 'create_date desc'

    card_id = fields.Many2one('pos.loyalty.card', string='Card', required=True, 
                              ondelete='cascade', index=True)
    points = fields.Float(string='Points', required=True)
    type = fields.Selection([
        ('earned', 'Earned'),
        ('redeemed', 'Redeemed'),
        ('returned', 'Returned'),
        ('redeem_returned', 'Refunded'),
    ], string='Type', required=True, index=True)
    description = fields.Char(string='Description')
    amount = fields.Float(string='Order Amount')
    order_id = fields.Many2one('pos.order', string='POS Order', index=True)

    # Related fields for searching
    customer_name = fields.Char(related='card_id.name', string='Customer Name', store=True)
    customer_phone = fields.Char(related='card_id.phone', string='Phone', store=True)
    card_number = fields.Char(related='card_id.card_number', string='Card Number', store=True)

    def action_open_order(self):
        """Open the related POS order (from the row's button in Points History)."""
        self.ensure_one()
        if not self.order_id:
            return False
        return {
            'type': 'ir.actions.act_window',
            'name': self.order_id.name or 'POS Order',
            'res_model': 'pos.order',
            'res_id': self.order_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    @api.model
    def _name_search(self, name='', domain=None, operator='ilike', limit=None, order=None):
        domain = domain or []
        if name:
            domain = [
                '|', '|', '|', '|', '|',
                ('card_number', operator, name),
                ('customer_name', operator, name),
                ('customer_phone', operator, name),
                ('description', operator, name),
                ('order_id.name', operator, name),
                ('order_id.pos_reference', operator, name),
            ] + domain
        return self._search(domain, limit=limit, order=order)
