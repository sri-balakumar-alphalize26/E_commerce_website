# -*- coding: utf-8 -*-
import logging

from odoo import fields, models
from odoo.tools import float_compare

from .sa_buy_line import NOT_ORDERED

_logger = logging.getLogger(__name__)


class SaleOrderBuy(models.Model):
    _inherit = 'sale.order'

    def _sa_buy_paid(self):
        """The customer's money is here: the invoice is paid, or it was taken online."""
        self.ensure_one()
        order = self.sudo()
        if self.env['sa.group.request'].sudo()._sa_order_is_paid(order):
            return True
        total = order.amount_total or 0.0
        return total > 0 and (order.amount_paid or 0.0) + 0.005 >= total

    def _sa_buy_requests(self):
        """Every enquiry on this order: its own and the cart's."""
        self.ensure_one()
        Request = self.env['sa.group.request'].sudo()
        found = Request.search([('order_id', '=', self.id), ('state', '!=', 'dropped')], order='id')
        return (found | self.sudo().sa_group_request_id.filtered(lambda r: r.state != 'dropped')).sorted('id')

    def _sa_buy_lines_make(self):
        """The missing buy lines of a paid, confirmed order. Returns the new ones."""
        self.ensure_one()
        order = self.sudo()
        Line = self.env['sa.buy.line'].sudo()
        made = Line.browse()
        if order.state != 'sale' or not order._sa_buy_paid():
            return made
        requests = order._sa_buy_requests()
        have = {(line.sale_line_id.id, line.request_id.id): line for line in Line.search([('order_id', '=', order.id)])}
        left = {}
        for request in requests:
            line = request._sa_buy_sale_line(order)
            if not line:
                _logger.info("Vendor orders: enquiry %s has no line on %s", request.id, order.name)
                continue
            stocked = line.product_id.is_storable
            if stocked:
                left.setdefault(line.id, line._sa_buy_shortage())
            old = have.get((line.id, request.id))
            if old:
                if stocked:
                    left[line.id] -= old.qty
                continue
            want = request.qty or 1.0
            # a product whose stock is not counted is bought when vendors were asked for it
            qty = min(want, left[line.id]) if stocked else (want if request.best_quote_id else 0.0)
            if float_compare(qty, 0.0, precision_rounding=line.product_uom_id.rounding) <= 0:
                continue
            if stocked:
                left[line.id] -= qty
            made |= Line.create({
                'request_id': request.id, 'sale_line_id': line.id, 'product_id': line.product_id.id,
                'qty': qty, 'uom_id': line.product_uom_id.id,
                'sell_unit': line.price_subtotal / line.product_uom_qty if line.product_uom_qty else 0.0,
                'sell_currency_id': order.currency_id.id,
                'paid_on': request.sa_paid_on or fields.Datetime.now(), 'company_id': order.company_id.id})
        requests.write({'sa_buy_checked_on': fields.Datetime.now()})
        if made:
            _logger.info("Vendor orders: %s - %s item(s) to buy", order.name, len(made))
        return made

    def write(self, vals):
        res = super().write(vals)
        if vals.get('state') == 'cancel':
            self.env['sa.buy.line'].sudo().search(
                [('order_id', 'in', self.ids), ('state', 'in', NOT_ORDERED)]).write({'state': 'cancelled'})
        return res


class SaleOrderLineBuy(models.Model):
    _inherit = 'sale.order.line'

    def _sa_buy_shortage(self):
        """How much of this line is neither reserved nor delivered, in its own unit."""
        self.ensure_one()
        line = self.sudo()
        unit = line.product_id.uom_id
        moves = line.move_ids.filtered(lambda m: m.state != 'cancel' and m.picking_code == 'outgoing')
        own = moves.filtered(lambda m: m.product_id == line.product_id)
        if own:
            need = sum(m.product_uom._compute_quantity(m.product_uom_qty, unit, rounding_method='HALF-UP') for m in own)
            here = sum(m.product_uom._compute_quantity(m.quantity, unit, rounding_method='HALF-UP') for m in own)
            short = need - here
        elif moves:             # a kit: its parts are on the moves
            return 0.0 if all(m.state in ('assigned', 'done') for m in moves) else line.product_uom_qty
        else:
            need = line.product_uom_id._compute_quantity(line.product_uom_qty, unit, rounding_method='HALF-UP')
            short = need - max(line.product_id.with_company(line.company_id).free_qty, 0.0)
        return unit._compute_quantity(max(short, 0.0), line.product_uom_id, rounding_method='HALF-UP')
