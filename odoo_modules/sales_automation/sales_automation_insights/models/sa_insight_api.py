# -*- coding: utf-8 -*-
"""What the two dashboards read. Plain dicts, nothing written.

Kept apart from the scoring so the screens' contract is in one file. The
per-enquiry thread is NOT built here: `sa_enquiry_detail` does up to five
searches per call, so the profile hands out enquiry ids and the screen fetches
one thread at a time, on expand.
"""
from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import UserError

WAITING_STATES = ('awaiting_confirm', 'finding', 'quoted', 'negotiating',
                  'awaiting_qty', 'awaiting_order_confirm', 'sourcing',
                  'awaiting_vendor_pick')
JOB_ORDER = ['awaiting_shop', 'preparing', 'ready', 'to_assign', 'offered',
             'accepted', 'picked', 'dispatched', 'out_for_delivery', 'delivered']


def _iso(dt):
    return (fields.Datetime.to_string(dt).replace(' ', 'T') + 'Z') if dt else False


class SaInsightEntityApi(models.Model):
    _inherit = 'sa.insight.entity'

    # ==================================================================
    @api.model
    def sa_insights_board(self, kind, search='', limit=100):
        kind = 'vendor' if kind == 'vendor' else 'customer'
        domain = [('kind', '=', kind)]
        if search:
            domain += ['|', ('name', 'ilike', search), ('phone', 'ilike', search)]
        rows = self.sudo().search(domain, limit=limit)
        now = fields.Datetime.now()
        out = []
        for e in rows:
            out.append({
                'id': e.id, 'name': e.name or '', 'phone': e.phone or '',
                'partner_id': e.partner_id.id or False,
                'stars': e.stars, 'enough_data': e.enough_data,
                'sample_size': e.sample_size,
                'enquiry_count': e.enquiry_count, 'order_count': e.order_count,
                'delivered_count': e.delivered_count,
                'cancelled_count': e.cancelled_count,
                'revenue_total': e.revenue_total,
                'last_seen_on': _iso(e.last_seen_on),
                'remarks_count': e.remarks_count,
                'tier': e.tier or 'new',
                'scores': {c.get('code'): c.get('score') for c in (e.components or [])},
                'badge': e._badge(now),
            })
        scored = self.sudo().search([('kind', '=', kind)])
        counts = {'all': len(out), 'flagged': sum(1 for r in out if r['remarks_count'])}
        for code in ('best', 'better', 'normal', 'poor', 'new'):
            counts[code] = sum(1 for r in out if r['tier'] == code)
        return {
            'kpis': self._kpis(kind, scored),
            'rows': out,
            'tier_counts': counts,
            'scored_on': _iso(max([d for d in scored.mapped('scored_on') if d] or [False])),
            'currency': self.env.company.currency_id.symbol
                        or self.env.company.currency_id.name or '',
        }

    def _badge(self, now):
        self.ensure_one()
        if self.remarks_count:
            return 'FLAGGED'
        if self.kind == 'vendor':
            live = self.request_ids.filtered(lambda r: r.state == 'sourcing')
            if live and not self.quote_ids.filtered(lambda q: q.request_id in live):
                return 'AWAITED'
            return 'REPLIED' if self.quote_ids else 'NONE'
        open_ = self.request_ids.filtered(lambda r: r.state in WAITING_STATES)
        if not open_:
            return 'REPLIED'
        latest = open_.sorted('id')[-1]
        if latest.customer_deadline and latest.customer_deadline < now:
            return 'OVERDUE'
        return 'AWAITED'

    @api.model
    def _kpis(self, kind, entities):
        Pick = self.env['stock.picking'].sudo()
        if kind == 'vendor':
            spend = sum(entities.mapped('revenue_total'))
            waiting = Pick.search_count([('sa_supply_waiting', '=', True)])
            open_asks = sum(entities.mapped('open_threads'))
            return {
                'live_revenue': spend, 'live_revenue_label': 'SUPPLY SPEND',
                'avg_response_min': self._avg_vendor_minutes(entities),
                'orders_transit': waiting, 'orders_transit_label': 'WAITING FOR STOCK',
                'open_threads': open_asks, 'open_threads_label': 'OPEN ASKS',
                'entity_count': len(entities),
                'scored_count': len(entities.filtered('enough_data')),
            }
        revenue = sum(entities.mapped('revenue_total'))
        transit = Pick.search_count([('sa_delivery_state', 'in',
                                      ('accepted', 'picked', 'dispatched', 'out_for_delivery'))])
        return {
            'live_revenue': revenue, 'live_revenue_label': 'LIVE REVENUE',
            'avg_response_min': self._avg_customer_minutes(entities),
            'orders_transit': transit, 'orders_transit_label': 'ORDERS TRANSIT',
            'open_threads': sum(entities.mapped('open_threads')),
            'open_threads_label': 'OPEN THREADS',
            'entity_count': len(entities),
            'scored_count': len(entities.filtered('enough_data')),
        }

    @staticmethod
    def _avg_customer_minutes(entities):
        vals = []
        for e in entities:
            for c in (e.components or []):
                if c.get('code') == 'reply' and isinstance(c.get('raw'), (int, float)):
                    vals.append(float(c['raw']))
        return round(sum(vals) / len(vals), 1) if vals else 0.0

    @staticmethod
    def _avg_vendor_minutes(entities):
        vals = []
        for e in entities:
            for c in (e.components or []):
                if c.get('code') == 'reply_speed' and isinstance(c.get('raw'), (int, float)):
                    vals.append(float(c['raw']))
        return round(sum(vals) / len(vals), 1) if vals else 0.0

    # ==================================================================
    @api.model
    def sa_insights_profile(self, kind, entity_id):
        e = self.sudo().browse(int(entity_id))
        if not e.exists():
            raise UserError(_("That row is no longer there."))
        now = fields.Datetime.now()
        labels = dict(self.env['stock.picking']._fields['sa_delivery_state']
                      ._description_selection(self.env))
        state_labels = dict(self.env['sa.group.request']._fields['state']
                            ._description_selection(self.env))
        drop_labels = dict(self.env['sa.group.request']._fields['drop_reason']
                           ._description_selection(self.env))
        timeline = []

        # ---- header ----
        dupes = self.sudo().search([
            ('kind', '=', e.kind), ('id', '!=', e.id),
            ('name', '=ilike', (e.name or '').strip())]) if e.name else self.browse()
        peers = self.sudo().search([('kind', '=', e.kind)])
        header = {
            'id': e.id, 'kind': e.kind, 'name': e.name or '', 'phone': e.phone or '',
            'partner_id': e.partner_id.id or False, 'stars': e.stars,
            'enough_data': e.enough_data, 'sample_size': e.sample_size,
            'first_seen_on': _iso(e.first_seen_on), 'last_seen_on': _iso(e.last_seen_on),
            'lifetime_value': e.revenue_total,
            'lifetime_max': max(peers.mapped('revenue_total') or [0.0]) or 0.0,
            'lifetime_label': 'SUPPLY SPEND' if e.kind == 'vendor' else 'LIFETIME VALUE',
            'aliases': [(a.tail or a.lid) for a in e.alias_ids],
            'duplicates': [{'id': d.id, 'name': d.name, 'phone': d.phone or ''} for d in dupes],
            'badge': e._badge(now),
            'remarks_count': e.remarks_count,
            'tier': e.tier or 'new',
            'scored_on': _iso(e.scored_on),
            'currency': self.env.company.currency_id.symbol or '',
        }
        score = {'total': e.score_total, 'stars': e.stars,
                 'components': e.components or []}

        # ---- enquiries / asks ----
        enquiries = []
        for r in e.request_ids.sorted(lambda r: r.id, reverse=True):
            tag = 'REPLIED'
            if r.state in WAITING_STATES:
                tag = 'OVERDUE' if (r.customer_deadline and r.customer_deadline < now) else 'AWAITED'
            elif r.state == 'order_created':
                tag = 'ORDERED'
            elif r.state == 'dropped':
                tag = 'DROPPED'
            enquiries.append({
                'id': r.id, 'ref': r.ref_code or str(r.id),
                'product': r.product_id.name or r.ai_search_term or r.raw_text or '',
                'state': r.state, 'state_label': state_labels.get(r.state, r.state),
                'drop_reason': drop_labels.get(r.drop_reason, '') if r.drop_reason else '',
                'created_on': _iso(r.create_date),
                'quoted_price': r.quoted_price or 0.0,
                'agreed_price': r.agreed_price or 0.0,
                'bargain_count': r.bargain_count or 0,
                'order_id': r.order_id.id or False,
                'order_name': r.order_id.name or '',
                'tag': tag,
            })
            timeline.append({'at': r.create_date, 'kind': 'enquiry',
                             'text': 'Asked for %s (#%s)' % (
                                 r.product_id.name or r.ai_search_term or r.raw_text or '?',
                                 r.ref_code or r.id), 'ref_id': r.id})
            if r.order_id:
                timeline.append({'at': r.order_id.date_order or r.write_date, 'kind': 'order',
                                 'text': 'Order %s for %.2f' % (r.order_id.name, r.order_id.amount_total),
                                 'ref_id': r.order_id.id})
            if r.state == 'dropped' and r.drop_reason:
                timeline.append({'at': r.write_date, 'kind': 'enquiry',
                                 'text': 'Dropped: %s (#%s)' % (
                                     drop_labels.get(r.drop_reason, r.drop_reason), r.ref_code),
                                 'ref_id': r.id})

        asks = []
        if e.kind == 'vendor':
            quotes_by_req = defaultdict(lambda: self.env['sa.vendor.quote'])
            for q in e.quote_ids:
                quotes_by_req[q.request_id.id] |= q
            for r in e.request_ids.sorted(lambda r: r.id, reverse=True):
                mine = quotes_by_req.get(r.id, self.env['sa.vendor.quote'])
                q = mine.sorted('price')[:1]
                asks.append({
                    'request_id': r.id, 'ref': r.ref_code or str(r.id),
                    'product': r.product_id.name or r.ai_search_term or '',
                    'asked_on': _iso(r.create_date),
                    'replied': bool(q), 'price': q.price if q else 0.0,
                    'is_best': bool(q and q.is_best),
                    'said_no': bool(e.partner_id and e.partner_id in r.sa_vendor_no_ids),
                    'response_minutes': q.response_minutes if q else 0,
                    'state': r.state,
                })
            for q in e.quote_ids:
                timeline.append({'at': q.create_date, 'kind': 'quote',
                                 'text': 'Quoted %.2f on #%s%s' % (
                                     q.price, q.request_id.ref_code,
                                     ' - cheapest' if q.is_best else ''),
                                 'ref_id': q.request_id.id})
        else:
            for q in self.env['sa.vendor.quote'].sudo().search(
                    [('request_id', 'in', e.request_ids.ids)]):
                timeline.append({'at': q.create_date, 'kind': 'quote',
                                 'text': '%s quoted %.2f on #%s' % (
                                     q.vendor_name or q.vendor_phone, q.price,
                                     q.request_id.ref_code), 'ref_id': q.request_id.id})

        # ---- orders / supplies ----
        orders, supplies = [], []
        for j in e.picking_ids.sorted(lambda j: j.id, reverse=True):
            st = j.sa_delivery_state
            idx = JOB_ORDER.index(st) if st in JOB_ORDER else -1
            progress = int(100 * (idx + 1) / len(JOB_ORDER)) if idx >= 0 else 0
            if st == 'delivered':
                progress = 100
            bucket = ('done' if st == 'delivered'
                      else 'bad' if st in ('cancelled', 'returned', 'failed')
                      else 'transit' if st in ('accepted', 'picked', 'dispatched', 'out_for_delivery')
                      else 'wait')
            overdue = bool(j.sa_promised_on and j.sa_promised_on < now
                           and st not in ('delivered', 'cancelled', 'returned', 'failed'))
            row = {
                'picking_id': j.id, 'ref': j.sa_ref_code or j.name,
                'order_name': j.sale_id.name or j.origin or '',
                'order_id': j.sale_id.id or False,
                'product': j.product_id.name or (j.move_ids[:1].product_id.name if j.move_ids else ''),
                'amount_total': j.sale_id.amount_total if j.sale_id else 0.0,
                'delivery_state': st, 'delivery_label': labels.get(st, st),
                'bucket': bucket, 'progress': progress, 'overdue': overdue,
                'promised_on': _iso(j.sa_promised_on),
                'delivered_on': _iso(j.sa_delivered_on),
                'cancelled_on': _iso(j.sa_cancelled_on),
                'cod': j.sa_cod_amount or 0.0,
                'kind': j.sa_delivery_kind or '',
            }
            if e.kind == 'vendor':
                row.update({
                    'cost': j.sa_supply_cost or 0.0,
                    'asked_on': _iso(j.sa_supply_asked_on),
                    'arrived_on': _iso(j.sa_supply_arrived_on),
                    'on_time': bool(j.sa_supply_arrived_on and j.sa_promised_on
                                    and j.sa_supply_arrived_on <= j.sa_promised_on),
                })
                supplies.append(row)
                if j.sa_supply_asked_on:
                    timeline.append({'at': j.sa_supply_asked_on, 'kind': 'supply',
                                     'text': 'Asked to supply #%s' % (j.sa_ref_code or j.name),
                                     'ref_id': j.id})
                if j.sa_supply_arrived_on:
                    timeline.append({'at': j.sa_supply_arrived_on, 'kind': 'supply',
                                     'text': 'Goods arrived for #%s%s' % (
                                         j.sa_ref_code or j.name,
                                         ' - on time' if row['on_time'] else ' - late'),
                                     'ref_id': j.id})
            else:
                orders.append(row)
                for stamp, what in ((j.sa_offered_on, 'Rider called'),
                                    (j.sa_delivered_on, 'Delivered'),
                                    (j.sa_cancelled_on, 'Cancelled')):
                    if stamp:
                        timeline.append({'at': stamp, 'kind': 'delivery',
                                         'text': '%s #%s' % (what, j.sa_ref_code or j.name),
                                         'ref_id': j.id})

        # ---- remarks: removed messages ----
        remarks = []
        for m in e.remark_ids.sorted(lambda m: (m.remarked_on, m.id), reverse=True):
            remarks.append({
                'id': m.id, 'at': _iso(m.remarked_on), 'chat': m.chat_label or '',
                'words': m.matched_words or '', 'text': m.text or '',
                'deleted': m.deleted, 'warned': m.warned,
                'error': m.delete_error or '', 'source': m.source, 'type': m.hit_type,
                'decided_by': m.decided_by, 'confidence': m.confidence,
                'severity': m.severity,
            })
            timeline.append({'at': m.remarked_on, 'kind': 'remark',
                             'text': 'Removed for "%s" in %s' % (
                                 m.matched_words or '?', m.chat_label or 'chat'),
                             'ref_id': m.id})

        # ---- messages: heatmap + a few log lines ----
        Msg = self.env['whatsapp.message'].sudo()
        msgs = Msg.search_read(
            [('sa_request_id', 'in', e.request_ids.ids)],
            ['direction', 'create_date', 'message', 'sa_request_id'],
            order='create_date desc, id desc', limit=400)
        buckets = [[0] * 24 for _ in range(7)]
        stamps = [m['create_date'] for m in msgs] + [t['at'] for t in timeline if t['at']]
        for dt in stamps:
            local = fields.Datetime.context_timestamp(self, dt)
            buckets[local.weekday()][local.hour] += 1
        for m in msgs[:20]:
            timeline.append({'at': m['create_date'], 'kind': 'message',
                             'text': ('%s: %s' % ('Us' if m['direction'] == 'outgoing' else 'Them',
                                                  (m['message'] or '')[:70].replace('\n', ' '))),
                             'ref_id': m['sa_request_id'] and m['sa_request_id'][0] or False})

        timeline = [t for t in timeline if t['at']]
        timeline.sort(key=lambda t: t['at'], reverse=True)
        logs = [{'at': _iso(t['at']), 'level': t['kind'].upper(), 'text': t['text'],
                 'ref_id': t['ref_id']} for t in timeline[:30]]
        feed = [{'at': _iso(t['at']), 'kind': t['kind'], 'text': t['text'],
                 'ref_id': t['ref_id']} for t in timeline[:12]]

        return {
            'header': header, 'score': score,
            'orders': orders, 'supplies': supplies,
            'enquiries': enquiries, 'asks': asks,
            'remarks': remarks,
            'timeline': feed, 'logs': logs,
            'heatmap': {'buckets': buckets, 'max': max(max(r) for r in buckets),
                        'tz': self.env.user.tz or 'UTC'},
        }

    # ==================================================================
    @api.model
    def sa_insights_chat_log(self, entity_id, day=None):
        """Every WhatsApp message with this person on one day, in the
        user's timezone: what they wrote (group or private chat) and what
        the shop wrote to them (their enquiries' replies, @mentions, private
        messages). The record the shop shows a customer who disputes what
        was said."""
        import pytz
        from datetime import datetime, time, timedelta
        e = self.sudo().browse(int(entity_id))
        if not e.exists():
            raise UserError(_("Unknown row."))
        tz = pytz.timezone(self.env.user.tz or 'UTC')
        d = fields.Date.from_string(day) if day else datetime.now(tz).date()
        start_local = tz.localize(datetime.combine(d, time.min))
        start = start_local.astimezone(pytz.utc).replace(tzinfo=None)
        end = (start_local + timedelta(days=1)).astimezone(pytz.utc).replace(tzinfo=None)

        tails = set()
        for raw in [e.phone_tail, e.phone, e.partner_id.phone if e.partner_id else '',
                    e.partner_id.mobile if e.partner_id and 'mobile' in e.partner_id._fields else '']:
            digits = ''.join(c for c in str(raw or '') if c.isdigit())
            if len(digits) >= 9:
                tails.add(digits[-9:])
        tails |= {a.tail for a in e.alias_ids if a.tail}
        lids = {x for x in [e.lid] + [a.lid for a in e.alias_ids] if x}
        parts = []
        for t in tails:
            parts += [[('participant_phone', 'like', t)], [('phone', 'like', t)], [('message', 'like', '@%' + t)]]
        for l in lids:
            parts += [[('participant_lid', '=', l)]]
        if e.request_ids:
            parts += [[('sa_request_id', 'in', e.request_ids.ids)]]
        if not parts:
            return {'day': d.isoformat(), 'rows': [], 'count': 0}
        who = ['|'] * (len(parts) - 1)
        for p in parts:
            who += p
        Msg = self.env['whatsapp.message'].sudo()
        rows = Msg.search_read(
            [('create_date', '>=', start), ('create_date', '<', end)] + who,
            ['create_date', 'direction', 'message', 'phone', 'group_jid', 'participant_phone',
             'participant_lid', 'status', 'attachment_ids', 'sa_request_id', 'wa_message_id'],
            order='create_date asc, id asc', limit=800)
        groups = {g['group_jid']: g['name'] for g in self.env['sa.sales.group'].sudo().search_read(
            [('group_jid', 'in', list({r['group_jid'] for r in rows if r['group_jid']}))], ['group_jid', 'name'])}
        out = []
        for r in rows:
            gj = r['group_jid'] or (r['phone'] if (r['phone'] or '').endswith('@g.us') else '')
            out.append({
                'id': r['id'], 'at': _iso(r['create_date']),
                'direction': 'in' if r['direction'] == 'incoming' else 'out',
                'chat': groups.get(gj) or (_("Group") if gj else _("Private chat")),
                'text': r['message'] or '', 'status': r['status'] or '',
                'media': len(r['attachment_ids'] or []),
                'ref': r['sa_request_id'] and r['sa_request_id'][1] or '',
                'wa_id': r['wa_message_id'] or '',
            })
        return {'day': d.isoformat(), 'rows': out, 'count': len(out),
                'tz': self.env.user.tz or 'UTC'}

    # ==================================================================
    @api.model
    def sa_insights_enquiry(self, entity_id, request_id):
        """One enquiry's whole thread, only if it belongs to this row."""
        e = self.sudo().browse(int(entity_id))
        if not e.exists() or int(request_id) not in e.request_ids.ids:
            raise UserError(_("That enquiry does not belong to this row."))
        return self.env['sa.group.request'].sa_enquiry_detail(int(request_id))

    # ==================================================================
    @api.model
    def sa_insights_compare(self, kind, entity_ids):
        ids = [int(i) for i in (entity_ids or [])]
        if not 2 <= len(ids) <= 4:
            raise UserError(_("Tick two to four rows to compare."))
        rows = self.sudo().browse(ids).exists()
        columns = [{'id': e.id, 'name': e.name or '', 'stars': e.stars,
                    'enough_data': e.enough_data} for e in rows]
        comps = (VENDOR_COMPONENT_CODES if kind == 'vendor'
                 else CUSTOMER_COMPONENT_CODES)
        metrics = []

        def add(code, label, unit, values, higher_better=True):
            clean = [v if isinstance(v, (int, float)) else None for v in values]
            candidates = [(v, i) for i, v in enumerate(clean) if v is not None]
            best = None
            if candidates:
                best = (max if higher_better else min)(candidates)[1]
            metrics.append({'code': code, 'label': label, 'unit': unit,
                            'values': clean, 'best_index': best})

        add('stars', 'Stars', '', [e.stars if e.enough_data else None for e in rows])
        for code, label in comps:
            vals = []
            for e in rows:
                c = next((c for c in (e.components or []) if c.get('code') == code), None)
                vals.append(c['score'] if c and c.get('score') is not None else None)
            add(code, label, '0-1', vals)
        add('enquiry_count', 'Asks' if kind == 'vendor' else 'Enquiries', '',
            [e.enquiry_count for e in rows])
        add('order_count', 'Quotes' if kind == 'vendor' else 'Orders', '',
            [e.order_count for e in rows])
        add('delivered_count', 'On time' if kind == 'vendor' else 'Delivered', '',
            [e.delivered_count for e in rows])
        add('cancelled_count', 'Said no' if kind == 'vendor' else 'Cancelled', '',
            [e.cancelled_count for e in rows], higher_better=False)
        add('revenue_total', 'Spend' if kind == 'vendor' else 'Revenue', 'money',
            [e.revenue_total for e in rows])

        radar = {
            'labels': [label for _c, label in comps],
            'datasets': [{
                'id': e.id, 'name': e.name or '',
                'data': [next((c['score'] or 0.0 for c in (e.components or [])
                               if c.get('code') == code and c.get('score') is not None), 0.0)
                         for code, _l in comps],
            } for e in rows],
        }
        return {'columns': columns, 'metrics': metrics, 'radar': radar}


CUSTOMER_COMPONENT_CODES = [
    ('reply', 'Reply speed'), ('conversion', 'Enquiries to orders'),
    ('completion', 'Orders delivered'), ('cancel', 'Cancellations & timeouts'),
    ('bargain', 'Bargaining'), ('payment', 'Payment'), ('conduct', 'Conduct')]
VENDOR_COMPONENT_CODES = [
    ('reply_rate', 'Reply rate'), ('reply_speed', 'Reply speed'),
    ('win', 'Cheapest'), ('no', 'Said no'), ('promise', 'Promise kept'),
    ('price', 'Price vs cheapest'), ('conduct', 'Conduct')]
