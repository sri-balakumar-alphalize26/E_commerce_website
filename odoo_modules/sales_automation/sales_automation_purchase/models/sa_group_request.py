# -*- coding: utf-8 -*-
import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class SaGroupRequestBuy(models.Model):
    _inherit = 'sa.group.request'

    sa_buy_line_ids = fields.One2many('sa.buy.line', 'request_id', 'Items to Buy')
    sa_buy_checked_on = fields.Datetime('Looked at for Vendor Orders', copy=False, readonly=True)

    def _sa_group_confirmed(self, order):
        res = super()._sa_group_confirmed(order)
        if self.sa_paid_told_on and not self.sa_buy_checked_on:
            self._sa_buy_check(order)
        return res

    def _sa_buy_check(self, order):
        """Never in the way of the payment: what fails here is tried again by the sweep."""
        try:
            with self.env.cr.savepoint():
                order.sudo()._sa_buy_lines_make()
            return True
        except Exception:  # noqa: BLE001
            _logger.exception("Vendor orders: %s could not be looked at", order.name)
            return False

    def _sa_buy_sale_line(self, order):
        """The order line this enquiry is on: its variant at its price, then
        its variant, then its product, then the only line there is."""
        self.ensure_one()
        lines = order.order_line.filtered(lambda l: not l.display_type and l.product_id)
        variant = self._sa_cart_variant()
        price = self._sa_cart_price()
        own = lines.filtered(lambda l: variant and l.product_id == variant)
        exact = own.filtered(lambda l: abs((l.price_unit or 0.0) - float(price)) <= 0.005)
        same = lines.filtered(lambda l: self.product_id and l.product_id.product_tmpl_id == self.product_id)
        return (exact or own or same or (lines if len(lines) == 1 else lines[:0]))[:1]
