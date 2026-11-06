# -*- coding: utf-8 -*-
"""Our side of the shared cards, delivery part (7 Oct 2026).

* The rider collects what the ORDER says is unpaid, less anything paid
  elsewhere (`sale.order._sa_paid_elsewhere`, a hook: 0 by default).
* The job's note for the rider: this order's note first, then the address's
  landmark, then the street's second line (as before).
* After Delivered: when `sale.order._sa_review_link()` gives a page, the
  customer is asked once to rate the products. Default: no link, nothing sent.
"""
import logging

from odoo import _, models

_logger = logging.getLogger(__name__)


class SaleOrderCollect(models.Model):
    _inherit = 'sale.order'

    def _sa_amount_to_collect(self):
        amount = super()._sa_amount_to_collect()
        try:
            elsewhere = float(self._sa_paid_elsewhere() or 0.0)
        except Exception as err:  # noqa: BLE001 - never lose the rider's amount over a hook
            _logger.info("Delivery: paid-elsewhere hook failed: %s", err)
            elsewhere = 0.0
        return max(0.0, (amount or 0.0) - elsewhere)


class StockPickingCommonHooks(models.Model):
    _inherit = 'stock.picking'

    def _compute_sa_pay_text(self):
        """Paid also when money taken outside Odoo (the shop wallet) leaves
        nothing to collect - not "Unpaid - collect 0.00"."""
        super()._compute_sa_pay_text()
        for job in self:
            order = job.sale_id
            if not order or job.sa_is_paid or not order.amount_total:
                continue
            try:
                elsewhere = float(order._sa_paid_elsewhere() or 0.0)
                if elsewhere > 0.004 and order.currency_id.is_zero(order._sa_amount_to_collect()):
                    job.sa_is_paid = True
                    job.sa_pay_text = _("Paid")
            except Exception as err:  # noqa: BLE001
                _logger.info("Delivery: paid-elsewhere check for %s failed: %s", job.name, err)

    def _sa_prepare_trip(self):
        """This order's note goes to the rider before the address landmark."""
        for job in self:
            try:
                note = job.sale_id.sa_delivery_note if job.sale_id and 'sa_delivery_note' in job.sale_id._fields else ''
                if note and not job.sa_delivery_note:
                    job.write({'sa_delivery_note': note[:120]})
            except Exception as err:  # noqa: BLE001
                _logger.info("Delivery: order note for %s not copied: %s", job.name, err)
        return super()._sa_prepare_trip()

    def sa_set_state(self, state):
        res = super().sa_set_state(state)
        if state == 'delivered':
            for job in self:
                try:
                    job._sa_after_delivered()
                except Exception as err:  # noqa: BLE001 - the delivery stands
                    _logger.warning("Delivery: after-delivered step for %s failed: %s", job.name, err)
        return res

    def _sa_after_delivered(self):
        """Ask for a product review, once, when a link exists."""
        self.ensure_one()
        order = self.sale_id.sudo()
        if not order or 'sa_delivery_note' not in order._fields:
            return False
        link = order._sa_review_link() or ''
        if not link:
            return False
        if not self.env['sa.outbox.guard'].sudo().claim('review|%s' % order.id, 60 * 60 * 24 * 14):
            return False
        return self._sa_tell_customer(_(
            "⭐ How was your order *#%(ref)s*? Rate the products here:\n%(url)s",
            ref=self.sa_ref_code or order.name, url=link), unique=True)
