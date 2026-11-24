# -*- coding: utf-8 -*-
"""What the Orders and Enquiries screens show beside the open work (23 Nov 2026)."""
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

PAGE = 50
CLOSED = ('dropped',)
ORDERED = ('order_created', 'handed_off', 'answered')


def iso(value):
    return value.isoformat() + 'Z' if value else ''


class StockPickingBoard(models.Model):
    _inherit = 'stock.picking'

    def _sa_board_extra(self):
        self.ensure_one()
        order = self.sale_id
        request = order._sa_group_enquiry() if order else False
        return {
            'at': iso(order.date_order or self.create_date),
            'total': order.amount_total or 0.0,
            'in_stock': (self.state == 'assigned') if self.sa_delivery_state == 'awaiting_shop' else True,
            'pay_link': bool(request and request.sa_pay_link_sent_on),
            'can_send_pay_link': bool(order and order.sa_can_send_pay_link),
        }

    @api.model
    def sa_store_queue(self, shop_id=None):
        data = super().sa_store_queue(shop_id=shop_id)
        jobs = {job.id: job for job in self.sudo().browse([row['id'] for row in data['rows']])}
        for row in data['rows']:
            row.update(jobs[row['id']]._sa_board_extra())
        data['done'] = self._sa_done_today(shop_id)
        return data

    @api.model
    def _sa_done_today(self, shop_id=None):
        domain = [('sa_delivery_state', '=', 'delivered'), ('sa_delivered_on', '>=', fields.Datetime.now() - timedelta(hours=24))]
        if shop_id:
            domain.append(('sa_shop_id', '=', int(shop_id)))
        rows = []
        for job in self.sudo().search(domain, order='sa_delivered_on desc', limit=PAGE):
            order = job.sale_id
            currency = job.sa_currency_id or job.company_id.currency_id
            rows.append({
                'id': job.id, 'ref': job.sa_ref_code or '', 'state': 'delivered', 'order_id': order.id, 'order_name': order.name or '',
                'customer': job.partner_id.name or '', 'phone': job.partner_id.phone or '',
                'address': ', '.join(filter(None, [job.partner_id.street, job.partner_id.city])),
                'rider': job.sa_delivery_partner_id.name or '', 'paid': not job.sa_amount_due(), 'currency': currency.symbol or currency.name or '',
                'lines': [{'name': m.product_id.name, 'qty': m.product_uom_qty} for m in job.move_ids],
                'at': iso(order.date_order or job.create_date), 'done_at': iso(job.sa_delivered_on), 'total': order.amount_total or 0.0})
        return rows

    @api.model
    def sa_store_act(self, job_id, action, reason='', company_id=None, **kwargs):
        if action == 'send_pay_link':
            job = self.sudo().browse(int(job_id))
            if not job.exists():
                raise UserError(_("That order is no longer there."))
            request = job.sale_id._sa_group_enquiry() if job.sale_id else False
            if not request:
                raise UserError(_("This order did not come from a WhatsApp group."))
            request.sudo()._sa_send_pay_link_now()
            return self.sa_store_queue(job.sa_shop_id.id)
        return super().sa_store_act(job_id, action, reason=reason, company_id=company_id, **kwargs)


class SaGroupRequestBoard(models.Model):
    _inherit = 'sa.group.request'

    @api.model
    def _sa_board_counts(self, days=30):
        since = fields.Datetime.now() - timedelta(days=max(1, int(days or 30)))
        counts = {state: n for state, n in self.sudo()._read_group([('create_date', '>=', since)], ['state'], ['__count'])}
        return {'ordered': sum(counts.get(s, 0) for s in ORDERED), 'closed': sum(counts.get(s, 0) for s in CLOSED)}

    @api.model
    def sa_enquiry_queue(self):
        data = super().sa_enquiry_queue()
        at = {r.id: r for r in self.sudo().browse([row['id'] for key in ('rows', 'tracking', 'stalled') for row in data.get(key) or []])}
        for key in ('rows', 'tracking', 'stalled'):
            for row in data.get(key) or []:
                request = at[row['id']]
                row['at'] = iso(request.create_date)
                row['group'] = row.get('group') or request.group_id.name or ''
                row['qty'] = row.get('qty') or int(request.qty or 0)
                row['sell'] = request.quoted_price or 0.0
                row['better'] = bool(request.sa_better_quote_id)
                row['currency'] = row.get('currency') or request.currency_id.name or ''
        data['counts'] = self._sa_board_counts()
        return data

    @api.model
    def sa_enquiry_board(self, tab, search='', days=30, offset=0):
        """A page of the finished ones: 'ordered' or 'closed'."""
        since = fields.Datetime.now() - timedelta(days=max(1, min(365, int(days or 30))))
        domain = [('create_date', '>=', since), ('state', 'in', ORDERED if tab == 'ordered' else CLOSED)]
        word = (search or '').strip().lstrip('#')[:60]
        if word:
            domain += ['|', '|', '|', '|', ('ref_code', '=ilike', word), ('raw_text', 'ilike', word), ('requester_name', 'ilike', word),
                       ('product_id.name', 'ilike', word), ('order_id.name', 'ilike', word)]
        found = self.sudo().search(domain, order='create_date desc, id desc', limit=PAGE + 1, offset=max(0, int(offset or 0)))
        reasons = dict(self._fields['drop_reason']._description_selection(self.env))
        rows = [{
            'id': r.id, 'ref': r.ref_code or str(r.id), 'at': iso(r.create_date), 'product': r.product_id.name or r.ai_search_term or r.raw_text or '',
            'qty': int(r.qty or 0), 'customer': r.requester_name or r.requester_phone or '', 'group': r.group_id.name or '',
            'sell': r.agreed_price or r.quoted_price or 0.0, 'currency': r.currency_id.name or '', 'order_name': r.order_id.name or '',
            'best_price': r.best_quote_id.price or 0.0, 'best_vendor': r.best_quote_id.partner_id.name or r.best_quote_id.vendor_name or '',
            'reason': reasons.get(r.drop_reason, ''), 'state': r.state} for r in found[:PAGE]]
        return {'rows': rows, 'more': len(found) > PAGE, 'counts': self._sa_board_counts(days)}

    @api.model
    def sa_enquiry_detail(self, request_id):
        detail = super().sa_enquiry_detail(request_id)
        request = self.sudo().browse(int(request_id))
        quotes = {}
        for quote in request.quote_ids.sorted('id'):
            quotes[quote.partner_id.id or 0, quote.vendor_name or ''] = quote
        by_partner = {}
        for quote in request.quote_ids.sorted('id'):
            by_partner[quote.partner_id.id or 0] = quote
        for vendor in detail['vendors']:
            quote = by_partner.get(vendor['id']) if vendor['replied'] else False
            vendor.update(rank=quote.sa_rank if quote else 0, late=bool(quote and quote.sa_late),
                          said_yes=vendor['id'] in request.sa_vendor_yes_ids.ids, said_no=vendor['id'] in request.sa_vendor_no_ids.ids)
            if quote:
                vendor.update(price=quote.price, is_best=quote.is_best)
        detail['vendors'].sort(key=lambda v: (not v['is_best'], not v['replied'], v['late'], v['price'] or 0, v['name']))
        best = request.best_quote_id
        better = request.sa_better_quote_id
        detail.update(
            best_cost=best.price if best else 0.0,
            margin=request._sa_margin(),
            evaluated_on=iso(request.sa_evaluated_on),
            better={'quote_id': better.id, 'vendor': better.partner_id.name or better.vendor_name or '', 'price': better.price,
                    'less': best.price - better.price} if better else False)
        return detail

    @api.model
    def sa_enquiry_use_late(self, request_id, quote_id):
        request = self.sudo().browse(int(request_id))
        quote = self.env['sa.vendor.quote'].sudo().browse(int(quote_id))
        if not request.exists() or not quote.exists() or quote.request_id != request:
            raise UserError(_("That price is no longer there."))
        request._sa_use_better(quote)
        request._sa_enquiry_notify()
        return True
