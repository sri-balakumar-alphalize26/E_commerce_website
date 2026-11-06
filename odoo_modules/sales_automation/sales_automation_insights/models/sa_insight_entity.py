# -*- coding: utf-8 -*-
"""One row per customer and per supplier, with a star rating earned from
what they actually did.

Nothing here asks anybody anything. Every number comes from records the
other modules already keep - enquiries, quotes, messages, delivery jobs - and
the rating is recomputed from scratch every night, so it can be argued with,
re-weighted, and rebuilt without anybody's opinion having been stored.

Identity is the hard part. A customer reaches us as a partner id, a phone
number, and sometimes only a WhatsApp @lid, and the enquiry records whichever
it saw. Folding is deterministic only: a shared phone tail, a shared lid, or
an order that names the partner. Never by name - the data is too thin to risk
fusing two people, and a wrong fold rates two humans as one.
"""
import logging
import statistics
from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

CUSTOMER_MIN_SAMPLE = 3     # enquiries
VENDOR_MIN_SAMPLE = 3       # asks

# (code, label, weight). Weights are renormalised over the components that
# have a sample, so a customer who never paid COD is not punished for it.
CUSTOMER_COMPONENTS = [
    ('reply', 'Reply speed', 0.21),
    ('conversion', 'Enquiries to orders', 0.21),
    ('completion', 'Orders delivered', 0.17),
    ('cancel', 'Cancellations & timeouts', 0.13),
    ('bargain', 'Bargaining', 0.04),
    ('payment', 'Payment', 0.09),
    ('conduct', 'Conduct', 0.15),
]
VENDOR_COMPONENTS = [
    ('reply_rate', 'Reply rate', 0.17),
    ('reply_speed', 'Reply speed', 0.13),
    ('win', 'Cheapest', 0.17),
    ('no', 'Said no', 0.04),
    ('promise', 'Promise kept', 0.17),
    ('price', 'Price vs cheapest', 0.17),
    ('conduct', 'Conduct', 0.15),
]
# The verdict a shopkeeper reads at a glance. Thresholds on the star value;
# a row without enough data is "new", never a fake grade.
TIERS = [
    ('best', 'Best', 4.5),
    ('better', 'Better', 3.5),
    ('normal', 'Normal', 2.5),
    ('poor', 'Poor', 0.0),
]
TIER_SELECTION = [(code, label) for code, label, _floor in TIERS] + [('new', 'New')]


def _tier_for(stars, enough):
    if not enough:
        return 'new'
    for code, _label, floor in TIERS:
        if stars >= floor:
            return code
    return 'poor'


# Conduct: every remark in the window costs a third; three zero it. Everyone
# has a sample here (no remarks = 1.0), which is why the other weights above
# were scaled to make room rather than renormalised.
CONDUCT_REMARKS_TO_ZERO = 3.0

# Only these drops are the customer's doing. `unavailable`, `not_product`,
# `no_vendor_reply` and the rest are ours, and must never count against them.
CUSTOMER_FAULT_DROPS = ('not_confirmed', 'declined', 'customer_timeout', 'stale')
CLOSED_STATES = ('order_created', 'dropped', 'answered', 'handed_off')
JOB_DONE = 'delivered'
JOB_BAD = ('cancelled', 'returned', 'failed')
JOB_TRANSIT = ('accepted', 'picked', 'dispatched', 'out_for_delivery')


def _tail(value):
    digits = ''.join(ch for ch in str(value or '') if ch.isdigit())
    return digits[-9:] if len(digits) >= 9 else digits


def _clamp(x):
    return max(0.0, min(1.0, float(x)))


def _linear(value, best, worst):
    """1.0 at `best` or better, 0.0 at `worst` or worse, linear between."""
    if value is None:
        return None
    if best < worst:
        if value <= best:
            return 1.0
        if value >= worst:
            return 0.0
        return 1.0 - (value - best) / float(worst - best)
    if value >= best:
        return 1.0
    if value <= worst:
        return 0.0
    return (value - worst) / float(best - worst)


class SaInsightEntity(models.Model):
    _name = 'sa.insight.entity'
    _description = 'Customer / Supplier Insight'
    _order = 'stars desc, enough_data desc, enquiry_count desc, id'
    _rec_name = 'name'

    kind = fields.Selection([('customer', 'Customer'), ('vendor', 'Supplier')],
                            required=True, index=True)
    key = fields.Char(
        'Identity Key', required=True, index=True,
        help="p:<partner id> when a partner is known, else t:<last nine "
             "digits>, else l:<WhatsApp lid>. Deterministic, so a rebuild "
             "finds the same row again.")
    partner_id = fields.Many2one('res.partner', ondelete='set null', index=True)
    name = fields.Char('Name')
    phone = fields.Char('Phone')
    phone_tail = fields.Char('Phone Tail', index=True)
    lid = fields.Char('WhatsApp LID', index=True)
    alias_ids = fields.One2many('sa.insight.alias', 'entity_id', 'Other Spellings')
    merged_into_id = fields.Many2one(
        'sa.insight.entity', 'Merged Into', ondelete='set null',
        help="Set this when two rows are one human. On the next recompute "
             "this row's history is counted on the target and this row is "
             "hidden. Nothing is deleted.")
    active = fields.Boolean(default=True)
    company_id = fields.Many2one('res.company', default=lambda s: s.env.company)

    # ---- what the rating is made of ----
    stars = fields.Float('Stars', digits=(2, 1), default=0.0)
    tier = fields.Selection(TIER_SELECTION, 'Tier', default='new', index=True)
    score_total = fields.Float('Score (0-1)', digits=(4, 3), default=0.0)
    components = fields.Json('Components')
    sample_size = fields.Integer('Sample')
    enough_data = fields.Boolean('Enough Data', index=True)
    scored_on = fields.Datetime('Scored On', readonly=True)

    # ---- counters for the board ----
    enquiry_count = fields.Integer('Enquiries')
    order_count = fields.Integer('Orders')
    delivered_count = fields.Integer('Delivered')
    cancelled_count = fields.Integer('Cancelled')
    open_threads = fields.Integer('Open Enquiries')
    revenue_total = fields.Float('Revenue / Spend')
    first_seen_on = fields.Datetime('First Seen')
    last_seen_on = fields.Datetime('Last Seen')

    # The exact records this row was scored from, so the profile page shows
    # precisely what the stars were made of - not a second guess at identity.
    request_ids = fields.Many2many(
        'sa.group.request', 'sa_insight_entity_request_rel',
        'entity_id', 'request_id', string='Enquiries (records)')
    quote_ids = fields.Many2many(
        'sa.vendor.quote', 'sa_insight_entity_quote_rel',
        'entity_id', 'quote_id', string='Quotes (records)')
    picking_ids = fields.Many2many(
        'stock.picking', 'sa_insight_entity_picking_rel',
        'entity_id', 'picking_id', string='Delivery Jobs (records)')
    remark_ids = fields.One2many('sa.conduct.remark', 'entity_id', 'Remarks')
    remarks_count = fields.Integer('Remark Count')

    # Odoo 19 style: `_sql_constraints` is logged as unsupported and silently
    # not created, which is worse than an error.
    _key_uniq = models.Constraint(
        'unique(kind, key)', 'One row per identity per kind.')

    # ==================================================================
    # Actions
    # ==================================================================
    def action_recompute(self):
        self._rebuild()
        return True

    @api.model
    def _cron_recompute(self):
        self._rebuild()
        return True

    # ==================================================================
    # The rebuild
    # ==================================================================
    @api.model
    def _rebuild(self, days=180):
        """Collect, fold, score, upsert. Idempotent: run it twice and get
        the same rows with the same numbers."""
        now = fields.Datetime.now()
        since = fields.Datetime.subtract(now, days=days)

        customers = self._collect_customers(since)
        vendors = self._collect_vendors(since)

        merged = self._merge_map()
        written = 0
        for kind, bucket in (('customer', customers), ('vendor', vendors)):
            # Fold rows the owner has merged by hand into their target.
            folded = {}
            for key, data in bucket.items():
                target = merged.get((kind, key), key)
                if target not in folded:
                    folded[target] = data
                elif target != key:
                    folded[target] = self._fold_data(kind, folded[target], data)
            for key, data in folded.items():
                self._upsert(kind, key, data, now)
                written += 1
        _logger.info("Insights: rebuilt %d customer(s) and %d supplier(s)",
                     len(customers), len(vendors))
        return written

    def _merge_map(self):
        out = {}
        for row in self.sudo().with_context(active_test=False).search(
                [('merged_into_id', '!=', False)]):
            out[(row.kind, row.key)] = row.merged_into_id.key
        return out

    @staticmethod
    def _fold_data(kind, a, b):
        """Two buckets for one human, after a manual merge."""
        for f in ('request_ids', 'quote_ids', 'picking_ids', 'order_ids', 'remark_ids'):
            a[f] = sorted(set(a.get(f, [])) | set(b.get(f, [])))
        for f in ('names', 'tails', 'lids'):
            a[f] = list(dict.fromkeys(a.get(f, []) + b.get(f, [])))
        a['partner_id'] = a.get('partner_id') or b.get('partner_id')
        return a

    # ------------------------------------------------------------------
    # Customers
    # ------------------------------------------------------------------
    @api.model
    def _collect_customers(self, since):
        Req = self.env['sa.group.request'].sudo()
        rows = Req.search_read(
            [('create_date', '>=', since)],
            ['requester_partner_id', 'requester_phone', 'requester_lid',
             'requester_is_lid', 'requester_name', 'order_id', 'create_date'],
            order='id asc')
        order_partner = {}
        order_ids = [r['order_id'][0] for r in rows if r['order_id']]
        if order_ids:
            for o in self.env['sale.order'].sudo().search_read(
                    [('id', 'in', order_ids)], ['partner_id']):
                order_partner[o['id']] = o['partner_id'] and o['partner_id'][0]

        # Pass 1: rows with a partner claim their tails and lids.
        tail_owner, lid_owner = {}, {}
        for r in rows:
            partner = (r['requester_partner_id'] and r['requester_partner_id'][0]) \
                or (r['order_id'] and order_partner.get(r['order_id'][0]))
            if not partner:
                continue
            key = 'p:%s' % partner
            t = _tail(r['requester_phone']) if not r['requester_is_lid'] else ''
            if t:
                tail_owner.setdefault(t, key)
            if r['requester_lid']:
                lid_owner.setdefault(r['requester_lid'], key)
        # Pass 1b: a row carrying both phone and lid teaches the lid - to the
        # partner row that owns the phone when there is one, else to the plain
        # phone row. Without the second case a LID-only enquiry from the same
        # person stayed a separate human forever.
        for r in rows:
            t = _tail(r['requester_phone']) if not r['requester_is_lid'] else ''
            if t and r['requester_lid']:
                lid_owner.setdefault(r['requester_lid'],
                                     tail_owner.get(t) or 't:%s' % t)

        # Pass 2: assign every row a key, folding into partner rows.
        bucket = {}
        for r in rows:
            partner = (r['requester_partner_id'] and r['requester_partner_id'][0]) \
                or (r['order_id'] and order_partner.get(r['order_id'][0]))
            t = _tail(r['requester_phone']) if not r['requester_is_lid'] else ''
            lid = r['requester_lid'] or ''
            if partner:
                key = 'p:%s' % partner
            elif t and t in tail_owner:
                key = tail_owner[t]
            elif lid and lid in lid_owner:
                key = lid_owner[lid]
            elif t:
                key = 't:%s' % t
            elif lid:
                key = 'l:%s' % lid
            else:
                continue
            d = bucket.setdefault(key, {
                'partner_id': False, 'names': [], 'tails': [], 'lids': [],
                'phone': '', 'request_ids': [], 'order_ids': [],
                'quote_ids': [], 'picking_ids': [], 'remark_ids': []})
            d['partner_id'] = d['partner_id'] or partner or False
            if r['requester_name'] and r['requester_name'] not in d['names']:
                d['names'].append(r['requester_name'])
            if t and t not in d['tails']:
                d['tails'].append(t)
            if lid and lid not in d['lids']:
                d['lids'].append(lid)
            if r['requester_phone'] and not d['phone'] and not r['requester_is_lid']:
                d['phone'] = r['requester_phone']
            d['request_ids'].append(r['id'])
            if r['order_id']:
                d['order_ids'].append(r['order_id'][0])

        # Pass 3: remarks, by the same rules. A person with a remark and no
        # enquiry still gets a row, so a flagged newcomer is visible.
        for m in self._remarks_since('customer', since):
            partner = m['partner_id'] and m['partner_id'][0]
            t = m['phone_tail'] or ''
            lid = m['lid'] or ''
            if partner:
                key = 'p:%s' % partner
            elif t and t in tail_owner:
                key = tail_owner[t]
            elif lid and lid in lid_owner:
                key = lid_owner[lid]
            elif t:
                key = 't:%s' % t
            elif lid:
                key = 'l:%s' % lid
            else:
                continue
            d = bucket.setdefault(key, {
                'partner_id': partner or False, 'names': [], 'tails': [], 'lids': [],
                'phone': m['phone'] or '', 'request_ids': [], 'order_ids': [],
                'quote_ids': [], 'picking_ids': [], 'remark_ids': []})
            if t and t not in d['tails']:
                d['tails'].append(t)
            if lid and lid not in d['lids']:
                d['lids'].append(lid)
            d['remark_ids'].append(m['id'])
        return bucket

    @api.model
    def _remarks_since(self, kind, since):
        return self.env['sa.conduct.remark'].sudo().search_read(
            [('kind', '=', kind), ('remarked_on', '>=', since)],
            ['partner_id', 'phone', 'phone_tail', 'lid'], order='id asc')

    # ------------------------------------------------------------------
    # Vendors
    # ------------------------------------------------------------------
    @api.model
    def _collect_vendors(self, since):
        Req = self.env['sa.group.request'].sudo()
        Quote = self.env['sa.vendor.quote'].sudo()
        Pick = self.env['stock.picking'].sudo()
        Partner = self.env['res.partner'].sudo()

        reqs = Req.search_read(
            [('create_date', '>=', since)],
            ['sourcing_vendor_ids', 'sa_vendor_yes_ids', 'sa_vendor_no_ids',
             'create_date'], order='id asc')
        quotes = Quote.search_read(
            [('create_date', '>=', since)],
            ['partner_id', 'vendor_phone', 'vendor_name', 'request_id',
             'create_date'], order='id asc')
        picks = Pick.search_read(
            [('sa_supply_partner_id', '!=', False),
             ('create_date', '>=', since)],
            ['sa_supply_partner_id', 'sa_supply_vendor_ids'])

        partner_ids = set()
        for r in reqs:
            partner_ids |= set(r['sourcing_vendor_ids']) | set(r['sa_vendor_yes_ids']) \
                | set(r['sa_vendor_no_ids'])
        for q in quotes:
            if q['partner_id']:
                partner_ids.add(q['partner_id'][0])
        for p in picks:
            partner_ids.add(p['sa_supply_partner_id'][0])
            partner_ids |= set(p['sa_supply_vendor_ids'])
        # Odoo 19 has no `mobile` on res.partner - it was folded into `phone`.
        partners = {p['id']: p for p in Partner.search_read(
            [('id', 'in', list(partner_ids))], ['name', 'phone'])} \
            if partner_ids else {}
        tail_of_partner = {}
        for pid, p in partners.items():
            t = _tail(p['phone'])
            if t:
                tail_of_partner.setdefault(t, pid)

        def bucket_for(bucket, key, partner_id=False, name='', phone=''):
            d = bucket.setdefault(key, {
                'partner_id': partner_id or False, 'names': [], 'tails': [],
                'lids': [], 'phone': phone or '', 'request_ids': [],
                'order_ids': [], 'quote_ids': [], 'picking_ids': [],
                'remark_ids': []})
            if name and name not in d['names']:
                d['names'].append(name)
            if phone and not d['phone']:
                d['phone'] = phone
            t = _tail(phone)
            if t and t not in d['tails']:
                d['tails'].append(t)
            return d

        bucket = {}
        asked_by_request = {}
        for r in reqs:
            everyone = set(r['sourcing_vendor_ids']) | set(r['sa_vendor_yes_ids']) \
                | set(r['sa_vendor_no_ids'])
            asked_by_request[r['id']] = everyone
            for pid in everyone:
                p = partners.get(pid, {})
                d = bucket_for(bucket, 'p:%s' % pid, pid, p.get('name', ''),
                               p.get('phone') or '')
                d['request_ids'].append(r['id'])

        for q in quotes:
            req_id = q['request_id'] and q['request_id'][0]
            asked = asked_by_request.get(req_id, set())
            # The vendor actually messaged on that enquiry wins over whatever
            # `_find_partner`'s unordered `limit=1` happened to bind.
            pid = None
            qt = _tail(q['vendor_phone'])
            if q['partner_id'] and q['partner_id'][0] in asked:
                pid = q['partner_id'][0]
            elif qt and tail_of_partner.get(qt) in asked:
                pid = tail_of_partner[qt]
            elif q['partner_id']:
                pid = q['partner_id'][0]
            elif qt and qt in tail_of_partner:
                pid = tail_of_partner[qt]
            if pid:
                p = partners.get(pid, {})
                d = bucket_for(bucket, 'p:%s' % pid, pid, p.get('name', ''),
                               p.get('phone') or q['vendor_phone'])
            elif qt:
                d = bucket_for(bucket, 't:%s' % qt, False,
                               q['vendor_name'] or '', q['vendor_phone'])
            else:
                continue
            d['quote_ids'].append(q['id'])
            if req_id and req_id not in d['request_ids']:
                d['request_ids'].append(req_id)

        for p in picks:
            pid = p['sa_supply_partner_id'][0]
            pp = partners.get(pid, {})
            d = bucket_for(bucket, 'p:%s' % pid, pid, pp.get('name', ''),
                           pp.get('phone') or '')
            d['picking_ids'].append(p['id'])

        for m in self._remarks_since('vendor', since):
            pid = m['partner_id'] and m['partner_id'][0]
            t = m['phone_tail'] or ''
            if not pid and t:
                pid = tail_of_partner.get(t)
            if pid:
                pp = partners.get(pid, {})
                d = bucket_for(bucket, 'p:%s' % pid, pid, pp.get('name', ''),
                               pp.get('phone') or m['phone'] or '')
            elif t:
                d = bucket_for(bucket, 't:%s' % t, False, '', m['phone'] or '')
            else:
                continue
            d['remark_ids'].append(m['id'])
        return bucket

    # ------------------------------------------------------------------
    # Upsert + score
    # ------------------------------------------------------------------
    @api.model
    def _upsert(self, kind, key, data, now):
        Entity = self.sudo().with_context(active_test=False)
        row = Entity.search([('kind', '=', kind), ('key', '=', key)], limit=1)
        partner = self.env['res.partner'].sudo().browse(data.get('partner_id') or [])
        name = (partner.name if partner else '') or (data['names'][-1] if data['names'] else '') \
            or data.get('phone') or key
        vals = {
            'kind': kind, 'key': key,
            'partner_id': partner.id if partner else False,
            'name': name,
            'phone': data.get('phone') or (partner.phone if partner else '') or '',
            'phone_tail': data['tails'][0] if data['tails'] else '',
            'lid': data['lids'][0] if data['lids'] else '',
            'request_ids': [(6, 0, sorted(set(data['request_ids'])))],
            'quote_ids': [(6, 0, sorted(set(data['quote_ids'])))],
            'picking_ids': [(6, 0, sorted(set(data['picking_ids'])))],
            'remark_ids': [(6, 0, sorted(set(data.get('remark_ids', []))))],
            'remarks_count': len(set(data.get('remark_ids', []))),
        }
        if row:
            row.write(vals)
        else:
            row = Entity.create(vals)
        # Aliases: every spelling beyond the first.
        want = [('tail', t) for t in data['tails'][1:]] + [('lid', l) for l in data['lids'][1:]]
        have = {(a.tail and 'tail' or 'lid', a.tail or a.lid) for a in row.alias_ids}
        Alias = self.env['sa.insight.alias'].sudo()
        for f, v in want:
            if (f, v) not in have:
                Alias.create({'entity_id': row.id, f: v, 'source': 'rebuild'})
        if kind == 'customer':
            row._score_customer(data, now)
        else:
            row._score_vendor(data, now)
        return row

    # ------------------------------------------------------------------
    def _finish_score(self, components, sample, minimum, now, extra):
        """Turn components into stars, honestly: no sample, no stars."""
        sampled = [c for c in components if c['score'] is not None]
        total = 0.0
        if sampled:
            wsum = sum(c['weight'] for c in sampled)
            total = sum(c['weight'] * c['score'] for c in sampled) / wsum if wsum else 0.0
        enough = sample >= minimum and bool(sampled)
        vals = {
            'components': [dict(c, score=(round(c['score'], 3)
                                          if c['score'] is not None else None))
                           for c in components],
            'sample_size': sample,
            'enough_data': enough,
            'score_total': round(total, 3) if enough else 0.0,
            'stars': round(1 + 4 * total, 1) if enough else 0.0,
            'scored_on': now,
        }
        vals['tier'] = _tier_for(vals['stars'], enough)
        vals.update(extra)
        self.write(vals)

    def _score_customer(self, data, now):
        self.ensure_one()
        Req = self.env['sa.group.request'].sudo()
        Pick = self.env['stock.picking'].sudo()
        reqs = Req.browse(data['request_ids'])
        orders = self.env['sale.order'].sudo().browse(sorted(set(data['order_ids'])))
        jobs = Pick.search([('sale_id', 'in', orders.ids),
                            ('sa_delivery_state', 'not in', ('none', False))])
        self.write({'picking_ids': [(6, 0, jobs.ids)]})

        closed = reqs.filtered(lambda r: r.state in CLOSED_STATES)
        converted = reqs.filtered(lambda r: r.state == 'order_created' or r.order_id)
        faults = reqs.filtered(lambda r: r.state == 'dropped'
                               and r.drop_reason in CUSTOMER_FAULT_DROPS)
        delivered = jobs.filtered(lambda j: j.sa_delivery_state == JOB_DONE)
        bad_jobs = jobs.filtered(lambda j: j.sa_delivery_state in JOB_BAD)

        # Reply speed: our outgoing -> their next incoming, per enquiry.
        pairs = self._reply_minutes(reqs, data)
        reply_min = statistics.median(pairs) if len(pairs) >= 2 else None
        if reply_min is None:
            reply_min = self._conversation_avg_minutes(data)

        cod_total = sum(j.sa_cod_amount or 0.0 for j in delivered)
        collected = 0.0
        for j in delivered:
            if j.sa_cod_amount:
                try:
                    due = j.sa_amount_due() or 0.0
                except Exception:  # noqa: BLE001 - one bad invoice is not a rating
                    due = 0.0
                collected += max(0.0, (j.sa_cod_amount or 0.0) - due)

        def ratio(a, b):
            return (_clamp(a / float(b)) if b else None)

        bargain_avg = (sum(reqs.mapped('bargain_count')) / float(len(reqs))) if reqs else None
        comps = [
            self._comp('reply', 'Reply speed', 0.21,
                       _linear(reply_min, 5, 120),
                       reply_min, ('%d min' % reply_min) if reply_min is not None else 'no replies yet'),
            self._comp('conversion', 'Enquiries to orders', 0.21,
                       ratio(len(converted), len(closed)),
                       len(converted), '%d of %d' % (len(converted), len(closed))),
            self._comp('completion', 'Orders delivered', 0.17,
                       ratio(len(delivered), len(jobs)),
                       len(delivered), '%d of %d' % (len(delivered), len(jobs))),
            self._comp('cancel', 'Cancellations & timeouts', 0.13,
                       (1.0 - _clamp((len(faults) + len(bad_jobs)) / float(len(reqs) + len(jobs))))
                       if (reqs or jobs) else None,
                       len(faults) + len(bad_jobs),
                       '%d of %d' % (len(faults) + len(bad_jobs), len(reqs) + len(jobs))),
            self._comp('bargain', 'Bargaining', 0.04,
                       _linear(bargain_avg, 0, 3) if bargain_avg is not None else None,
                       bargain_avg, ('%.1f rounds avg' % bargain_avg) if bargain_avg is not None else '-'),
            self._comp('payment', 'Payment', 0.09,
                       ratio(collected, cod_total) if cod_total else None,
                       collected, ('%.0f of %.0f collected' % (collected, cod_total)) if cod_total else 'no COD yet'),
            self._conduct_comp(data),
        ]
        open_threads = len(reqs.filtered(lambda r: r.state not in CLOSED_STATES))
        revenue = sum(o.amount_total for o in orders if o.state in ('sale', 'done'))
        dates = reqs.mapped('create_date')
        self._finish_score(comps, len(reqs), CUSTOMER_MIN_SAMPLE, now, {
            'enquiry_count': len(reqs),
            'order_count': len(orders),
            'delivered_count': len(delivered),
            'cancelled_count': len(faults) + len(bad_jobs),
            'open_threads': open_threads,
            'revenue_total': revenue,
            'first_seen_on': min(dates) if dates else False,
            'last_seen_on': max(dates) if dates else False,
        })

    def _score_vendor(self, data, now):
        self.ensure_one()
        Req = self.env['sa.group.request'].sudo()
        Quote = self.env['sa.vendor.quote'].sudo()
        Pick = self.env['stock.picking'].sudo()
        reqs = Req.browse(data['request_ids'])
        quotes = Quote.browse(data['quote_ids'])
        jobs = Pick.browse(data['picking_ids'])
        partner = self.partner_id

        asks = len(reqs)
        answered = len(set(quotes.mapped('request_id').ids))
        said_no = len(reqs.filtered(lambda r: partner and partner in r.sa_vendor_no_ids))
        best = len(quotes.filtered('is_best'))

        settings = self.env['sa.ai.settings'].sudo().get_settings()
        window = max(1, settings.sourcing_window_minutes or 10)
        mins = [q.response_minutes for q in quotes if q.response_minutes is not None]
        avg_min = (sum(mins) / float(len(mins))) if mins else None

        # Price vs the cheapest on the same enquiry.
        cheapest = {}
        for q in Quote.search([('request_id', 'in', reqs.ids)]):
            if q.price and (q.request_id.id not in cheapest or q.price < cheapest[q.request_id.id]):
                cheapest[q.request_id.id] = q.price
        ratios = [cheapest[q.request_id.id] / q.price for q in quotes
                  if q.price and cheapest.get(q.request_id.id)]
        price_score = (sum(ratios) / float(len(ratios))) if ratios else None

        dated = jobs.filtered(lambda j: j.sa_supply_arrived_on and j.sa_promised_on)
        on_time = dated.filtered(lambda j: j.sa_supply_arrived_on <= j.sa_promised_on)

        def ratio(a, b):
            return (_clamp(a / float(b)) if b else None)

        comps = [
            self._comp('reply_rate', 'Reply rate', 0.17, ratio(answered, asks),
                       answered, '%d of %d asks' % (answered, asks)),
            self._comp('reply_speed', 'Reply speed', 0.13,
                       _linear(avg_min, window * 0.25, window) if avg_min is not None else None,
                       avg_min, ('%.0f min avg' % avg_min) if avg_min is not None else 'no replies yet'),
            self._comp('win', 'Cheapest', 0.17, ratio(best, len(quotes)),
                       best, '%d of %d quotes' % (best, len(quotes))),
            self._comp('no', 'Said no', 0.04,
                       (1.0 - _clamp(said_no / float(asks))) if asks else None,
                       said_no, '%d of %d asks' % (said_no, asks)),
            self._comp('promise', 'Promise kept', 0.17, ratio(len(on_time), len(dated)),
                       len(on_time), ('%d of %d' % (len(on_time), len(dated))) if dated else 'nothing bought in yet'),
            self._comp('price', 'Price vs cheapest', 0.17, price_score,
                       price_score, ('%.0f%% of cheapest' % (100 / price_score)) if price_score else '-'),
            self._conduct_comp(data),
        ]
        spend = sum(j.sa_supply_cost or 0.0 for j in jobs)
        dates = reqs.mapped('create_date') + quotes.mapped('create_date')
        self._finish_score(comps, asks, VENDOR_MIN_SAMPLE, now, {
            'enquiry_count': asks,
            'order_count': len(quotes),
            'delivered_count': len(on_time),
            'cancelled_count': said_no,
            'open_threads': len(reqs.filtered(lambda r: r.state == 'sourcing')),
            'revenue_total': spend,
            'first_seen_on': min(dates) if dates else False,
            'last_seen_on': max(dates) if dates else False,
        })

    def _conduct_comp(self, data):
        n = len(set(data.get('remark_ids') or []))
        label = ('%d remark%s' % (n, '' if n == 1 else 's')) if n else 'no remarks'
        return self._comp('conduct', 'Conduct', 0.15,
                          1.0 - min(1.0, n / CONDUCT_REMARKS_TO_ZERO), n, label)

    # ------------------------------------------------------------------
    # One row, now - for a fresh remark, not tonight.
    # ------------------------------------------------------------------
    @api.model
    def _attach_remark(self, remark, days=180):
        """Fold one new remark into its row and re-score that row only.
        The collector already keys remarks by the same rules as enquiries,
        so the bucket that contains this remark is the row it belongs to."""
        now = fields.Datetime.now()
        since = fields.Datetime.subtract(now, days=days)
        kind = remark.kind
        bucket = (self._collect_vendors(since) if kind == 'vendor'
                  else self._collect_customers(since))
        merged = self._merge_map()
        for key, data in bucket.items():
            if remark.id in data.get('remark_ids', []):
                target = merged.get((kind, key), key)
                if target != key and target in bucket:
                    data = self._fold_data(kind, dict(bucket[target]), data)
                row = self._upsert(kind, target, data, now)
                _logger.info("Conduct: remark %s attached to %s row %s (%s)",
                             remark.id, kind, row.id, row.name)
                return row
        return self.browse()

    def _rescore_self(self, days=180):
        """Re-score this row from scratch (after a remark was deleted)."""
        now = fields.Datetime.now()
        since = fields.Datetime.subtract(now, days=days)
        for row in self:
            bucket = (self._collect_vendors(since) if row.kind == 'vendor'
                      else self._collect_customers(since))
            data = bucket.get(row.key)
            if data:
                self._upsert(row.kind, row.key, data, now)
            else:
                row.write({'remark_ids': [(5, 0, 0)], 'remarks_count': 0})
        return True

    @staticmethod
    def _comp(code, label, weight, score, raw, raw_label):
        return {'code': code, 'label': label, 'weight': weight,
                'score': (None if score is None else _clamp(score)),
                'raw': raw, 'raw_label': raw_label}

    # ------------------------------------------------------------------
    def _reply_minutes(self, reqs, data):
        """Minutes from our message to the customer's next one, per enquiry."""
        Msg = self.env['whatsapp.message'].sudo()
        if not reqs:
            return []
        rows = Msg.search_read(
            [('sa_request_id', 'in', reqs.ids)],
            ['sa_request_id', 'direction', 'create_date', 'participant_phone',
             'participant_lid', 'phone'], order='create_date asc, id asc')
        tails = set(data.get('tails') or [])
        lids = set(data.get('lids') or [])
        by_req = defaultdict(list)
        for m in rows:
            by_req[m['sa_request_id'][0]].append(m)
        out = []
        for msgs in by_req.values():
            waiting_since = None
            for m in msgs:
                if m['direction'] == 'outgoing':
                    waiting_since = waiting_since or m['create_date']
                    continue
                theirs = (_tail(m['participant_phone']) in tails
                          or (m['participant_lid'] or '') in lids
                          or (not m['participant_phone'] and _tail(m['phone']) in tails))
                if theirs and waiting_since:
                    out.append((m['create_date'] - waiting_since).total_seconds() / 60.0)
                    waiting_since = None
        return out

    def _conversation_avg_minutes(self, data):
        """The tracker's own per-thread average, when it keeps one."""
        Conv = self.env['wa.conversation'].sudo()
        if 'avg_response_minutes' not in Conv._fields or not data.get('tails'):
            return None
        for t in data['tails']:
            conv = Conv.search([('phone', 'like', t)], order='id desc', limit=1)
            if conv and conv.avg_response_minutes:
                return float(conv.avg_response_minutes)
        return None

    # ------------------------------------------------------------------
    @api.constrains('merged_into_id')
    def _check_merge(self):
        for row in self:
            if row.merged_into_id:
                if row.merged_into_id == row:
                    raise UserError(_("A row cannot be merged into itself."))
                if row.merged_into_id.kind != row.kind:
                    raise UserError(_("Merge a customer into a customer and a "
                                      "supplier into a supplier."))
