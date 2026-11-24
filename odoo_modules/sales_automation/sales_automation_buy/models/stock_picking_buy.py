# -*- coding: utf-8 -*-
"""The purchase behind "order it in" (owner, 24 Nov 2026)."""
import logging

import psycopg2

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class StockPickingBuy(models.Model):
    _inherit = 'stock.picking'

    sa_supply_po_id = fields.Many2one('purchase.order', 'Vendor Purchase', readonly=True, copy=False, index='btree_not_null')
    sa_supply_po_note = fields.Char('Purchase Note', readonly=True, copy=False)

    # ------------------------------------------------------------ making it
    def _sa_buy_live(self):
        """The purchase that counts, or an empty one."""
        self.ensure_one()
        po = self.sudo().sa_supply_po_id
        return po if po and po.state != 'cancel' else po.browse()

    def _sa_buy_received(self, po):
        return sum(po.order_line.mapped('qty_received'))

    def _sa_buy_lock(self):
        self.ensure_one()
        self.flush_recordset()
        self.env.cr.execute('SELECT id FROM stock_picking WHERE id = %s FOR UPDATE', [self.id])
        self.invalidate_recordset(['sa_supply_po_id'])

    def _sa_buy_vals(self):
        self.ensure_one()
        moves = self.move_ids.filtered(lambda m: m.state not in ('done', 'cancel'))
        products = {}
        for move in moves:
            products[move.product_id] = products.get(move.product_id, 0.0) + move.product_qty
        single = len(products) == 1
        day = self.sa_supply_day and fields.Datetime.to_datetime(self.sa_supply_day).replace(hour=12)
        planned = self.sa_supply_due_on or day or self.sa_promised_on or fields.Datetime.now()
        lines = [(0, 0, {
            'product_id': product.id, 'name': product.display_name, 'product_qty': qty, 'product_uom_id': product.uom_id.id,
            'price_unit': (self.sa_supply_cost / qty) if single and qty else 0.0, 'date_planned': planned,
            # what comes belongs to this order, not to whoever waited longest;
            # cancelling the purchase never cancels the customer's delivery
            'move_dest_ids': [(6, 0, moves.filtered(lambda m, p=product: m.product_id == p).ids)], 'propagate_cancel': False,
        }) for product, qty in products.items()]
        warehouse = self.picking_type_id.warehouse_id
        return {
            'partner_id': self.sa_supply_partner_id.id, 'company_id': self.company_id.id,
            'currency_id': (self.sa_currency_id or self.company_id.currency_id).id, 'picking_type_id': warehouse.in_type_id.id,
            'origin': ', '.join(x for x in (self.sale_id.name, self.sa_ref_code and '#' + self.sa_ref_code) if x),
            'date_planned': planned, 'order_line': lines}, single

    def _sa_buy_make(self, before=False):
        """The purchase order for the vendor of this job, once."""
        self.ensure_one()
        job = self.sudo()
        job._sa_buy_lock()
        partner = job.sa_supply_partner_id
        if not job.sa_supply_waiting and not before:
            return False
        po = job._sa_buy_live()
        if po:
            same = po.partner_id.commercial_partner_id == partner.commercial_partner_id and abs(po.amount_untaxed - job.sa_supply_cost) < 0.01
            if same or job._sa_buy_received(po):
                return po
            job._sa_buy_cancel(_("another vendor or price was chosen"))
        if not partner:
            job.sa_supply_po_note = _("No purchase order: no vendor was chosen.")
            return False
        try:
            with self.env.cr.savepoint():
                vals, single = job._sa_buy_vals()
                if not vals['order_line']:
                    raise UserError(_("there is nothing to order."))
                if not vals['picking_type_id']:
                    raise UserError(_("the branch has no place for receipts."))
                quiet = job.env['purchase.order'].with_company(job.company_id).with_context(
                    mail_create_nosubscribe=True, mail_create_nolog=True, mail_notrack=True, mail_auto_subscribe_no_notify=True)
                po = quiet.create(vals)
                if single:
                    # the price that was agreed, whatever the vendor price list says
                    for line in po.order_line:
                        line.price_unit = job.sa_supply_cost / line.product_qty
                    po.button_confirm()
                job.write({'sa_supply_po_id': po.id, 'sa_supply_po_note': False if single else _(
                    "Draft purchase: several products. Fill in the prices and confirm it.")})
        except psycopg2.OperationalError:
            raise
        except Exception as err:  # noqa: BLE001 - the order and the message stay
            _logger.warning("Buy: no purchase order for %s: %s", job.sa_ref_code, err)
            job.sa_supply_po_note = _("No purchase order: %s", str(err)[:150])
            return False
        _logger.info("Buy: %s for %s from %s", po.name, job.sa_ref_code, partner.name)
        return po

    def _sa_buy_cancel(self, why):
        """Not received yet: cancelled. Else it stays, and the note says so."""
        self.ensure_one()
        job = self.sudo()
        po = job._sa_buy_live()
        if not po:
            return True
        if job._sa_buy_received(po):
            job.sa_supply_po_note = _("%(po)s stays (goods were received): %(why)s", po=po.name, why=why)
            return False
        try:
            with self.env.cr.savepoint():
                if getattr(po, 'locked', False):
                    po.button_unlock()
                po.with_context(mail_notrack=True).button_cancel()
        except psycopg2.OperationalError:
            raise
        except Exception as err:  # noqa: BLE001
            _logger.warning("Buy: %s not cancelled: %s", po.name, err)
            job.sa_supply_po_note = _("%(po)s could not be cancelled: %(why)s", po=po.name, why=str(err)[:120])
            return False
        job.sa_supply_po_note = _("%(po)s was cancelled: %(why)s", po=po.name, why=why)
        return True

    def _sa_supply_prepare(self):
        res = super()._sa_supply_prepare()
        self._sa_buy_make(before=True)
        return res

    def _sa_supply_number(self):
        po = self._sa_buy_live()
        return po.name if po and po.state in ('purchase', 'done') else super()._sa_supply_number()

    @api.model
    def sa_store_supply_set(self, job_id, **kwargs):
        super().sa_store_supply_set(job_id, **kwargs)
        job = self.sudo().browse(int(job_id))
        job._sa_buy_make()
        return self.sa_store_queue(job.sa_shop_id.id)

    @api.model
    def sa_store_act(self, job_id, action, reason='', company_id=None, **kwargs):
        if action in ('supply_po', 'supply_arrived'):
            job = self.sudo().browse(int(job_id))
            if not job.exists():
                raise UserError(_("That order is no longer there."))
            if action == 'supply_arrived':
                return self.sa_store_supply_arrived(job.id, qty=kwargs.get('qty'))
            job._sa_buy_make()
            return self.sa_store_queue(job.sa_shop_id.id)
        return super().sa_store_act(job_id, action, reason=reason, company_id=company_id, **kwargs)

    def action_cancel(self):
        res = super().action_cancel()
        for job in self:
            if job.sudo().sa_supply_po_id and job.state == 'cancel':
                job._sa_buy_cancel(_("the order was cancelled"))
        return res

    # ------------------------------------------------------------ goods arrived
    def _sa_buy_receipts(self, po):
        return po.picking_ids.filtered(lambda p: p.state not in ('done', 'cancel') and p.picking_type_code == 'incoming')

    @api.model
    def sa_store_supply_arrived(self, job_id, qty=None):
        job = self.sudo().browse(int(job_id))
        if not job.exists():
            raise UserError(_("That order is no longer there."))
        job._sa_buy_lock()
        if not job.sa_supply_waiting:
            return self.sa_store_queue(job.sa_shop_id.id)       # somebody got there first
        po = job._sa_buy_live()
        if po and po.state in ('draft', 'sent', 'to approve'):
            raise UserError(_("%s is not confirmed yet. Confirm it in Purchase first.", po.name))
        if not po and job.sa_supply_partner_id:
            # first the purchase, else the goods would never come into stock
            raise UserError(_("Make the purchase order first."))
        receipts = job._sa_buy_receipts(po) if po else self.browse()
        if not receipts:
            if not po:
                job.sa_supply_po_note = _("Goods arrived without a purchase order: no stock was added.")
            return super().sa_store_supply_arrived(job.id)
        moves = receipts.move_ids.filtered(lambda m: m.state not in ('done', 'cancel'))
        if any(p.tracking != 'none' for p in moves.product_id):
            raise UserError(_("This product has serial or lot numbers. Receive %s in Odoo first, then press Goods arrived.", receipts[:1].name))
        still = sum(moves.mapped('product_uom_qty'))
        came = still if qty in (None, False, '') else float(qty)
        if came <= 0 or came > still + 0.0001:
            raise UserError(_("Type how many came: 1 to %g.", still))
        if came < still and len(moves.product_id) > 1:
            raise UserError(_("Several products: receive a part of them in Odoo."))
        left = came
        for move in moves:
            take = min(left, move.product_uom_qty)
            move.quantity = take
            move.picked = bool(take)
            left -= take
        done = receipts.with_context(skip_backorder=True, skip_sms=True, skip_immediate=True, cancel_backorder=False,
                                     mail_notrack=True).button_validate()
        if not all(r.state == 'done' for r in receipts):
            raise UserError(_("The receipt %s could not be completed. Open it in Odoo.", receipts[:1].name) if done is not True
                            else _("The receipt %s is not done.", receipts[:1].name))
        job._sa_buy_bill(po)
        if job._sa_buy_receipts(po):
            job.sa_supply_po_note = _("%(a)g of %(b)g came.", a=job._sa_buy_received(po), b=sum(po.order_line.mapped('product_qty')))
            job._sa_store_notify()
            return self.sa_store_queue(job.sa_shop_id.id)
        job.sa_supply_po_note = False
        return super().sa_store_supply_arrived(job.id)

    def _sa_buy_bill(self, po):
        """A draft bill for what was received, never posted. Never in the way."""
        self.ensure_one()
        try:
            with self.env.cr.savepoint():
                po.invalidate_recordset()
                if po.invoice_status == 'to invoice':
                    po.with_company(po.company_id).with_context(mail_notrack=True, mail_create_nosubscribe=True).action_create_invoice()
        except psycopg2.OperationalError:
            raise
        except Exception as err:  # noqa: BLE001
            _logger.warning("Buy: no bill for %s: %s", po.name, err)
            self.sa_supply_po_note = _("No draft bill: %s", str(err)[:120])

    # ------------------------------------------------------------ the screen
    def _sa_board_extra(self):
        out = super()._sa_board_extra()
        job = self.sudo()
        po = job._sa_buy_live()
        out.update(po=False, arrive_stop=_("Make the purchase order first.") if job.sa_supply_waiting and not po and job.sa_supply_partner_id else '', po_note=job.sa_supply_po_note or '', po_can_make=bool(job.sa_supply_waiting and not po and job.sa_supply_partner_id))
        if po:
            receipts = job._sa_buy_receipts(po)
            moves = receipts.move_ids.filtered(lambda m: m.state not in ('done', 'cancel'))
            tracked = any(p.tracking != 'none' for p in moves.product_id)
            bills = po.invoice_ids.filtered(lambda m: m.state != 'cancel')
            can = self.env.user.has_group('purchase.group_purchase_user')
            if po.state in ('draft', 'sent', 'to approve'):
                out['arrive_stop'] = _("Confirm %s in Purchase first.", po.name)
            out['po'] = {
                'id': po.id, 'name': po.name, 'state': po.state, 'can_open': can,
                'state_name': dict(po._fields['state']._description_selection(self.env)).get(po.state, ''),
                'ordered': sum(po.order_line.mapped('product_qty')), 'received': job._sa_buy_received(po),
                'open': sum(moves.mapped('product_uom_qty')), 'single': len(moves.product_id) == 1,
                'receipt_url': '/odoo/stock.picking/%s' % receipts[:1].id if tracked and receipts else '',
                'bill': _("draft bill") if any(b.state == 'draft' for b in bills) else _("bill posted") if bills else ''}
        return out
