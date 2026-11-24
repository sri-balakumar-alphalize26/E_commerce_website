# -*- coding: utf-8 -*-
"""One enquiry's share of one paid order line that a vendor has to supply.

Per enquiry, not per order line: the cart puts several enquiries of the same
product on one line, and each was asked of its own vendors."""
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

STATES = [
    ('waiting', 'Waiting for prices'), ('review', 'To review'), ('no_vendor', 'Nobody can supply'),
    ('selected', 'Vendor chosen'), ('po_draft', 'Draft order'), ('ordered', 'Ordered'),
    ('received', 'Received'), ('cancelled', 'Cancelled')]

# state -> the states it may go to
MOVES = {
    'waiting': ('review', 'cancelled'),
    'review': ('selected', 'no_vendor', 'waiting', 'cancelled'),
    'no_vendor': ('review', 'cancelled'),
    'selected': ('po_draft', 'review', 'cancelled'),
    'po_draft': ('ordered', 'selected', 'cancelled'),
    'ordered': ('received', 'review', 'cancelled'),
    'received': (),
    'cancelled': (),
}
# no vendor has been told anything yet
NOT_ORDERED = ('waiting', 'review', 'no_vendor', 'selected')
# what the customer paid for is settled when the line is made
FROZEN = ('request_id', 'sale_line_id', 'product_id', 'sell_unit', 'sell_currency_id', 'paid_on', 'company_id')
SWEEP_DAYS = 2


class SaBuyLine(models.Model):
    _name = 'sa.buy.line'
    _description = 'Item to Buy from a Vendor'
    _order = 'paid_on desc, id desc'

    request_id = fields.Many2one('sa.group.request', 'Enquiry', required=True, ondelete='cascade', index=True)
    sale_line_id = fields.Many2one('sale.order.line', 'Order Line', required=True, ondelete='cascade', index=True)
    order_id = fields.Many2one(related='sale_line_id.order_id', store=True, index=True)
    product_id = fields.Many2one('product.product', 'Product', required=True, ondelete='restrict')
    qty = fields.Float('Quantity to Buy', required=True, digits='Product Unit')
    uom_id = fields.Many2one('uom.uom', 'Unit', required=True)
    sell_unit = fields.Float('Customer Paid per Unit', digits='Product Price', readonly=True,
                             help="Without tax. Settled at the payment; nothing here changes it.")
    sell_currency_id = fields.Many2one('res.currency', required=True)
    paid_on = fields.Datetime(index=True)
    state = fields.Selection(STATES, default='waiting', required=True, index=True)
    company_id = fields.Many2one('res.company', required=True, index=True)

    _line_request_uniq = models.Constraint('unique(sale_line_id, request_id)', 'This item is already on the list.')

    def write(self, vals):
        for rec in self:
            new = vals.get('state', rec.state)
            if new != rec.state and new not in MOVES[rec.state]:
                names = dict(self._fields['state']._description_selection(self.env))
                raise UserError(_("This item cannot go from \"%(old)s\" to \"%(new)s\".",
                                  old=names.get(rec.state), new=names.get(new, new)))
            for name in FROZEN:
                if name in vals and not rec._sa_same(name, vals[name]):
                    raise UserError(_("What the customer paid for is settled and cannot be changed here."))
        return super().write(vals)

    def _sa_same(self, name, value):
        self.ensure_one()
        kind = self._fields[name].type
        if kind == 'many2one':
            return (self[name].id or False) == (value or False)
        if kind == 'datetime':
            value = fields.Datetime.to_datetime(value)
        return (self[name] or False) == (value or False)

    @api.model
    def _cron_buy_sweep(self):
        """Paid orders whose own moment was missed. Each on its own."""
        since = fields.Datetime.now() - timedelta(days=SWEEP_DAYS)
        requests = self.env['sa.group.request'].sudo().search(
            [('sa_paid_on', '>=', since), ('sa_buy_checked_on', '=', False), ('order_id', '!=', False),
             ('state', '!=', 'dropped')], order='id', limit=100)
        for order in requests.order_id:
            requests.filtered(lambda r: r.order_id == order)[:1]._sa_buy_check(order)
        return True
