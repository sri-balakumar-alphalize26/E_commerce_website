# -*- coding: utf-8 -*-
"""The counter and a group order that is not yet paid.

Accept: the goods are here, so the customer is asked to pay - in the group,
with the order, its lines and the amount - instead of being told it is
being packed. Ready (packed, call the rider): refused until it is paid."""
import logging

from odoo import _, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class StockPickingOosGate(models.Model):
    _inherit = 'stock.picking'

    def _sa_unpaid_group_enquiry(self):
        """The group enquiry when this job's order is group-born and unpaid."""
        self.ensure_one()
        order = self.sale_id
        req = order._sa_group_enquiry() if order else False
        if not req or not req.group_id or not req.group_id.group_jid:
            return False
        if req._sa_order_is_paid(order):
            return False
        return req

    def sa_shop_accept(self):
        unpaid = self.filtered(lambda p: p.sa_delivery_state == 'awaiting_shop'
                               and p._sa_unpaid_group_enquiry())
        for picking in unpaid:
            req = picking._sa_unpaid_group_enquiry()
            picking.write({'sa_delivery_state': 'preparing',
                           'sa_shop_seen_on': fields.Datetime.now(),
                           'sa_shop_user_id': self.env.user.id})
            _logger.info("Store: %s accepted by %s - unpaid group order, asking the customer to pay",
                         picking.sa_ref_code, self.env.user.name)
            try:
                req.sudo()._sa_accept_pay_link(picking)
            except Exception as err:  # noqa: BLE001 - the accept stands
                _logger.warning("Store: pay link for %s failed: %s", picking.sa_ref_code, err)
        return super(StockPickingOosGate, self - unpaid).sa_shop_accept() if (self - unpaid) else True

    def sa_shop_ready(self):
        """Packed while the customer has not paid (6 Oct 2026): no popup.
        The job goes to Ready and waits; the rider is called by itself
        the moment the payment lands (see `sa_packed_paid_now`)."""
        unpaid = self.filtered(
            lambda p: p.sa_delivery_state in ('awaiting_shop', 'preparing')
            and (lambda r: bool(r and r.sa_pay_link_sent_on))(p._sa_unpaid_group_enquiry()))
        for picking in unpaid:
            picking.write({
                'sa_delivery_state': 'ready',
                'sa_shop_ready_on': fields.Datetime.now(),
                'sa_packed_unpaid_on': fields.Datetime.now(),
                'sa_shop_user_id': picking.sa_shop_user_id.id or self.env.user.id,
            })
            picking._sa_tell_customer(_(
                "📦 Order *#%(ref)s* is packed and ready. It leaves the moment "
                "your payment arrives - the pay link is above.", ref=picking.sa_ref_code or '-'))
            picking.message_post(body=_("Packed before payment by %s - the rider is called when the customer pays.",
                                        self.env.user.name))
            _logger.info("Store: %s packed before payment - waiting for the customer to pay",
                         picking.sa_ref_code)
        rest = self - unpaid
        res = super(StockPickingOosGate, rest).sa_shop_ready() if rest else True
        if unpaid:
            self._sa_store_notify()
        return res

    def _sa_waiting_payment(self):
        """Packed, nobody called, the customer chose to pay online (a pay
        link went out) and has not paid: Call a Rider waits (6 Oct 2026).
        Cash on delivery (no pay link) is never held."""
        self.ensure_one()
        if self.sa_delivery_state not in ('ready', 'to_assign') or self.sa_delivery_partner_id:
            return False
        req = self._sa_unpaid_group_enquiry()
        return bool(req and getattr(req, 'sa_pay_link_sent_on', False))

    def sa_action_call_rider(self, rider_id=None, rider_ids=None):
        if (self._sa_waiting_payment() and not self.env.context.get('sa_force_call')
                and not self.env.context.get('sa_cascade')):
            raise UserError(_("Order #%(ref)s is not paid yet - the rider is called by itself the moment the "
                              "payment arrives. A delivery manager can call anyway.", ref=self.sa_ref_code or '-'))
        return super().sa_action_call_rider(rider_id=rider_id, rider_ids=rider_ids)

    def sa_packed_paid_now(self):
        """The payment arrived on a job packed before it: tell the customer
        and call the rider exactly as Packed would have."""
        settings = self.env['sa.delivery.settings'].sudo().get_settings()
        for picking in self:
            picking.write({'sa_packed_unpaid_on': False})
            link = picking.sa_track_link_once()
            picking._sa_tell_customer(_(
                "✅ Payment received for order *#%(ref)s*. A rider is being called "
                "to collect it from %(shop)s.%(tail)s",
                ref=picking.sa_ref_code or '-', shop=picking.sa_shop_id.name or _("our shop"),
                tail=(_("\n\nTrack it here:\n%(url)s", url=link) if link else '')))
            picking.message_post(body=_("Payment received - the rider is being called."))
            try:
                if picking.sa_delivery_partner_id:
                    picking.sa_action_call_rider(rider_id=picking.sa_delivery_partner_id.id)
                elif settings.auto_call_rider_on_packed or (settings.call_rider_mode or 'ask') != 'manual':
                    picking.sa_action_call_rider()
                else:
                    _logger.info("Store: %s paid - manual mode, waiting for Call a Rider", picking.sa_ref_code)
            except UserError as err:
                picking.write({'sa_last_error': str(err.args[0] if err.args else err)[:250]})
                _logger.info("Store: %s paid, rider not called: %s", picking.sa_ref_code, err)
        self._sa_store_notify()
        return True


class SaleOrderPackedWait(models.Model):
    _inherit = 'sale.order'

    def _sa_refresh_cod(self):
        """A payment landed: a job packed before it gets its rider now."""
        res = super()._sa_refresh_cod()
        try:
            jobs = self.mapped('picking_ids').filtered(
                lambda p: p.sa_packed_unpaid_on and p.sa_delivery_state in ('ready', 'to_assign')
                and not p._sa_unpaid_group_enquiry())
            if jobs:
                jobs.sudo().sa_packed_paid_now()
        except Exception as err:  # noqa: BLE001 - bookkeeping, never block a payment
            _logger.warning("Store: calling the rider after the payment failed: %s", err)
        return res
