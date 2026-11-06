"""The thread back from a sale order to the group message that started it."""

import logging

from odoo import SUPERUSER_ID, fields, models

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    sa_group_request_id = fields.Many2one(
        'sa.group.request', string='Group Enquiry',
        readonly=True, copy=False, index=True,
        help="The WhatsApp group message this order grew out of.",
    )
    sa_group_id = fields.Many2one(
        related='sa_group_request_id.group_id', store=True,
        string='WhatsApp Group',
    )

    def action_confirm(self):
        """Confirm as the system user when an automated step is doing it.

        369ai_erp allows only sales managers and system users to confirm. The
        WhatsApp flow confirms from the public payment page and from the
        webhook, both as the public user under sudo - and sudo does not change
        who env.user is, so the check refused every real customer's paid
        order while passing in tests driven from an admin browser.

        Escalated only when *both* hold: the call is already privileged (su)
        and the current user could not confirm by themselves. A person in the
        UI is never sudo, so the block still applies to them.
        """
        user = self.env.user
        automated = self.env.su and not (
            user.has_group('sales_team.group_sale_manager')
            or user.has_group('base.group_system'))
        if automated and user.id != SUPERUSER_ID:
            return self._sa_confirm_with_serial_rule(
                lambda: super(SaleOrder, self.with_user(SUPERUSER_ID)).action_confirm())
        return self._sa_confirm_with_serial_rule(lambda: super(SaleOrder, self).action_confirm())

    # ------------------------------------------------------------------
    # product_tracker bridge: serial-tracked lines with nothing in stock
    # ------------------------------------------------------------------
    _SA_ENFORCE_KEY = 'product_tracker.enforce_serial_on_sale'

    def _sa_is_whatsapp_order(self):
        self.ensure_one()
        if self.sa_group_request_id:
            return True
        if (self.origin or '').startswith('WhatsApp'):
            return True
        return bool(self.env['sa.group.request'].sudo().search_count(
            [('order_id', '=', self.id)]))

    def _sa_serials_short(self):
        """Serial-tracked lines that still lack serials after the tracker's
        own auto-pick. Empty when product_tracker is not installed."""
        self.ensure_one()
        if 'tracker_lot_ids' not in self.env['sale.order.line']._fields:
            return []
        short = []
        for line in self.order_line:
            product = line.product_id
            if line.display_type or not product or product.tracking != 'serial':
                continue
            qty = int(line.product_uom_qty or 0)
            if qty > 0 and len(line.tracker_lot_ids) < qty:
                short.append((product.display_name, len(line.tracker_lot_ids), qty))
        return short

    def _sa_confirm_with_serial_rule(self, confirm):
        """Run `confirm()` for WhatsApp orders whose serials cannot exist yet.

        A group order for goods that are not in stock is confirmed at the
        customer's signature so the purchase can start; the serial numbers
        only come into being when the goods are received. product_tracker's
        "enforce serial on sale" would refuse that order forever. For those
        orders only, and only when the tracker's auto-pick found nothing to
        link, the switch is turned off for this one call - inside the
        transaction, restored in `finally`, so no other request ever sees
        it - and the serials are pinned on the delivery instead.
        """
        Param = self.env['ir.config_parameter'].sudo()
        if Param.get_param(self._SA_ENFORCE_KEY, 'True') != 'True':
            return confirm()
        relax = self.env['sale.order']
        for order in self:
            if not order._sa_is_whatsapp_order():
                continue
            if hasattr(order, '_tracker_auto_pick_missing_on_confirm'):
                try:
                    order._tracker_auto_pick_missing_on_confirm()
                except Exception as err:  # noqa: BLE001 - the rule decides below
                    _logger.warning("Sales Automation: serial auto-pick on %s "
                                    "failed: %s", order.name, err)
            short = order._sa_serials_short()
            if short:
                relax |= order
                _logger.info("Sales Automation: %s confirmed without serials "
                             "(%s) - they are assigned on the delivery",
                             order.name, '; '.join(
                                 '%s %d/%d' % x for x in short))
        if not relax:
            return confirm()
        Param.set_param(self._SA_ENFORCE_KEY, 'False')
        try:
            return confirm()
        finally:
            Param.set_param(self._SA_ENFORCE_KEY, 'True')
