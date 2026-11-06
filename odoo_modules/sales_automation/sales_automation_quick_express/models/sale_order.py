# -*- coding: utf-8 -*-
"""Quick or Express, decided on the order before it becomes a delivery job."""

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .qe_delivery_rule import MODE_CHOICES

_logger = logging.getLogger(__name__)

QUICK, EXPRESS = 'quick', 'express'

REASON_CHOICES = [
    ('product', 'A product is Express only'),
    ('far', 'Too far from every Quick shop'),
    ('stock', 'Not in stock at a shop in reach'),
    ('area', 'The area does not get Quick'),
]
# When several lines are Express for different reasons, the order shows the
# one a person can do least about.
_REASON_RANK = ['product', 'far', 'area', 'stock']


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    qe_mode = fields.Selection(MODE_CHOICES, 'Delivery', copy=False, readonly=True)
    qe_shop_id = fields.Many2one('sa.delivery.shop', 'Quick from', copy=False,
                                 readonly=True)
    qe_kind = fields.Selection([('fee', 'Delivery fee')], copy=False, readonly=True)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    qe_decided = fields.Boolean(copy=False, readonly=True)
    qe_mode = fields.Selection(MODE_CHOICES, 'Quick or Express', copy=False,
                               readonly=True, tracking=True)
    qe_reason = fields.Selection(REASON_CHOICES, 'Why Express', copy=False,
                                 readonly=True)
    qe_shop_id = fields.Many2one(
        'sa.delivery.shop', 'Quick from', copy=False, readonly=True,
        help="The nearest shop in reach of the customer that holds every line.")
    qe_slot_id = fields.Many2one(
        'sa.qe.delivery.slot', 'Delivery slot', copy=False,
        domain="[('mode', '=', qe_mode)]")
    qe_slot_day = fields.Date('Slot day', compute='_compute_qe_slot_day',
                              store=True, copy=False)
    qe_due_at = fields.Datetime('Due', copy=False, readonly=True)
    qe_fee = fields.Monetary('Delivery fee', copy=False, readonly=True)
    qe_blocked = fields.Boolean(
        'Below the Quick minimum', copy=False, readonly=True)

    @api.depends('qe_slot_id')
    def _compute_qe_slot_day(self):
        for order in self:
            slot = order.qe_slot_id
            order.qe_slot_day = slot._qe_day() if slot else False

    @api.constrains('qe_slot_id')
    def _check_qe_slot(self):
        for order in self:
            slot = order.qe_slot_id
            if slot and not slot._qe_is_open(exclude=order):
                raise ValidationError(_(
                    "The slot \"%s\" is closed or full. Pick another one.",
                    slot.name))

    # ------------------------------------------------------------------
    # The decision
    # ------------------------------------------------------------------
    def _qe_product_lines(self):
        """The lines that have to be carried."""
        self.ensure_one()
        return self.order_line.filtered(
            lambda l: not l.display_type and not l.qe_kind and l.product_id
            and l.product_id.type != 'service')

    def _qe_where(self):
        """What the customer's address allows.

        `shops` is a list when distance decides (possibly empty: nobody
        reaches), `area_quick` is set when the pincode area decides, and both
        stay None when nothing is known - which is Quick.
        """
        self.ensure_one()
        where = {'shops': None, 'area_quick': None, 'reason': False}
        address = self.partner_shipping_id or self.partner_id
        ready = self.env['sa.delivery.shop'].sudo().search(
            [('qe_quick', '=', True)]).filtered(lambda s: s._qe_ready())
        lat, lng = address.partner_latitude, address.partner_longitude
        if ready and (lat or lng):
            where['shops'] = ready._qe_in_reach(lat, lng)
            if not where['shops']:
                where['reason'] = 'far'
            return where
        area = self.env['sa.qe.service.area']._qe_match(address.zip)
        if area:
            where['area_quick'] = bool(area.quick)
            if not area.quick:
                where['reason'] = 'area'
        return where

    def _qe_mode_of(self, line, where):
        """(mode, shop, reason) for one line."""
        none = self.env['sa.delivery.shop']
        if line.product_id.product_tmpl_id.qe_delivery_text:
            return EXPRESS, none, 'product'
        if where['shops'] is not None:
            for shop, _km in where['shops']:
                if shop._qe_has_stock(line.product_id, line.product_uom_qty):
                    return QUICK, shop, False
            return EXPRESS, none, where['reason'] or 'stock'
        if where['area_quick'] is not None:
            if where['area_quick']:
                return QUICK, none, False
            return EXPRESS, none, 'area'
        return QUICK, none, False

    def _qe_decide(self):
        """Work out Quick or Express for each line, then for the order.

        One order is one delivery job, so the order is Quick only when every
        line is - and, when distance decides, only when one shop in reach
        holds all of it.
        """
        for order in self:
            lines = order._qe_product_lines()
            if not lines:
                order.write({'qe_decided': False, 'qe_mode': False,
                             'qe_reason': False, 'qe_shop_id': False})
                continue
            where = order._qe_where()
            reasons = set()
            for line in lines:
                mode, shop, reason = order._qe_mode_of(line, where)
                line.write({'qe_mode': mode, 'qe_shop_id': shop.id})
                if reason:
                    reasons.add(reason)

            mode, shop = (EXPRESS if reasons else QUICK), self.env['sa.delivery.shop']
            if mode == QUICK and where['shops'] is not None:
                needed = {}
                for line in lines:
                    needed[line.product_id] = (needed.get(line.product_id, 0.0)
                                               + line.product_uom_qty)
                for candidate, _km in where['shops']:
                    if all(candidate._qe_has_stock(p, q) for p, q in needed.items()):
                        shop = candidate
                        break
                if not shop:
                    mode = EXPRESS
                    reasons.add('stock')

            vals = {
                'qe_decided': True,
                'qe_mode': mode,
                'qe_shop_id': shop.id,
                'qe_reason': next((r for r in _REASON_RANK if r in reasons), False),
            }
            if order.qe_slot_id and order.qe_slot_id.mode != mode:
                vals['qe_slot_id'] = False
            if (shop and order.state in ('draft', 'sent')
                    and shop.warehouse_id != order.warehouse_id
                    and shop.warehouse_id.company_id == order.company_id):
                vals['warehouse_id'] = shop.warehouse_id.id
            order.write(vals)
            order._qe_refresh_amounts()
        return True

    def action_qe_decide(self):
        self._qe_decide()
        return True

    # ------------------------------------------------------------------
    # Fee and minimum
    # ------------------------------------------------------------------
    def _qe_goods_total(self):
        self.ensure_one()
        return sum(self.order_line.filtered(
            lambda l: not l.display_type and not l.qe_kind).mapped('price_total'))

    def _qe_refresh_amounts(self):
        """The fee this order owes and whether it is under the Quick minimum."""
        for order in self:
            rule = self.env['sa.qe.delivery.rule']._qe_for(order.qe_mode)
            goods = order._qe_goods_total()
            fee = 0.0
            if rule and goods < (rule.free_above or 0.0):
                fee += rule.fee or 0.0
            fee += max(0.0, order.qe_slot_id.fee or 0.0)
            order.write({
                'qe_fee': fee if order.qe_mode else 0.0,
                'qe_blocked': bool(order.qe_mode == QUICK and rule
                                   and goods < (rule.min_order or 0.0)),
            })

    def _qe_apply_fee(self):
        product = self.env.ref(
            'sales_automation_quick_express.product_qe_delivery').sudo()
        for order in self:
            if not order.qe_decided:
                order._qe_decide()
            order._qe_refresh_amounts()
            order.order_line.filtered(lambda l: l.qe_kind == 'fee').unlink()
            if not order.qe_fee:
                continue
            rule = self.env['sa.qe.delivery.rule']._qe_for(order.qe_mode)
            line = self.env['sale.order.line'].create({
                'order_id': order.id,
                'product_id': product.id,
                'name': rule.eta or product.name,
                'product_uom_qty': 1.0,
                'price_unit': order.qe_fee,
                'qe_kind': 'fee',
                'sequence': 9999,
            })
            # other modules recompute the price on create; the fee is the fee
            if line.price_unit != order.qe_fee:
                line.write({'price_unit': order.qe_fee})
        return True

    def action_qe_apply_fee(self):
        for order in self:
            if order.state == 'cancel' or order.locked:
                raise UserError(_("%s can no longer be changed.", order.name))
        self._qe_apply_fee()
        return True

    # ------------------------------------------------------------------
    # Hand-off to the delivery job
    # ------------------------------------------------------------------
    def _qe_due(self):
        """When the booked slot is due, or False to use the standard promise."""
        self.ensure_one()
        slot = self.qe_slot_id
        return slot._qe_due(self.qe_slot_day) if slot else False

    def action_confirm(self):
        settings = self.env['sa.delivery.settings'].sudo().get_settings()
        if settings.qe_enabled:
            todo = self.filtered(lambda o: o.state in ('draft', 'sent'))
            try:
                with self.env.cr.savepoint():
                    # an order decided already (e.g. placed on the website,
                    # where the customer paid for that mode) keeps it
                    todo.filtered(lambda o: not o.qe_decided)._qe_decide()
                    if settings.qe_auto_fee:
                        todo._qe_apply_fee()
            except Exception as err:  # noqa: BLE001 - never block a confirmation
                _logger.exception("Quick/Express: deciding %s failed: %s",
                                  todo.mapped('name'), err)
            if settings.qe_enforce_minimum:
                low = todo.filtered('qe_blocked')
                if low:
                    rule = self.env['sa.qe.delivery.rule']._qe_for(QUICK)
                    raise UserError(_(
                        "%(orders)s: a Quick order needs at least %(min)s.",
                        orders=', '.join(low.mapped('name')), min=rule.min_order))
        return super().action_confirm()

    def _sa_dispatch_deliveries(self):
        forced = self.filtered(
            lambda o: o.qe_decided and o.qe_mode == QUICK and o.qe_shop_id)
        if not forced:
            return super()._sa_dispatch_deliveries()
        rest = self - forced
        if rest:
            super(SaleOrder, rest)._sa_dispatch_deliveries()
        for order in forced:
            super(SaleOrder, order.with_context(
                qe_force_shop=order.qe_shop_id.id))._sa_dispatch_deliveries()
        return True
