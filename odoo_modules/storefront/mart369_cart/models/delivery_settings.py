"""Delivery settings: every delivery option on one page, saved with one Save.

Asked for on 13 Nov 2026: delivery was spread over Fees, Slots, Service areas,
Branches, Hub rules, Shops, Riders and Delivery Settings, each branch had two
or three map pins in different records, and the hub rules list was what
"made us collapse". This is the one page both screens show - the console's
Delivery > Settings and Odoo's 369 Mart > Store > Delivery settings - read and
saved here, so the two cannot disagree.

* **How we deliver** - one area, or many branches (the hub rules on, shown as
  a From x To grid instead of a list). Switching to one area archives the
  routes, so switching back loses nothing.
* **Branches** - pin, Quick, its reaches. Saved through `mart369_admin_save`,
  the same door as the Branches tab, so a person's choice stops the
  automatic setup from touching it; the WhatsApp side keeps its delivery
  shop in step (mart369_whatsapp_bridge).
* **Between branches** - one cell per pair: Same day ... Not delivered, Cargo.
* **Fees**, **slots on/off**, and the **WhatsApp delivery** section the bridge
  adds.
* **How delivery decides** - the same settings, said in sentences.

Save is all or nothing: every value is checked first and the page gets
`{section, row, field, message}` for each one that is wrong; only when none is
wrong is anything written, inside one savepoint.
"""

from odoo import api, models
from odoo.exceptions import UserError, ValidationError

from .branch import has_pin, quick_time_text

# The words a Between-branches cell can say, and the days each one ranks as
# (fewest days wins when several branches have the item).
ROUTE_CHOICES = (
    ('Same day', 0), ('Next day', 1), ('In 2-3 days', 2),
    ('In 3-4 days', 3), ('In 5-7 days', 5),
)
NOT_DELIVERED = 'Not delivered'
MODES = (('quick', 'Quick'), ('all', 'Express'))
SLOT_KINDS = (('now', 'Now'), ('window', 'Time window'), ('days', 'In a number of days'))


class Mart369DeliverySettingsPage(models.AbstractModel):
    _name = 'mart369.delivery.settings.page'
    _description = '369 Mart delivery settings page'

    # ---------------------------------------------------------------- read

    @api.model
    def mart369_settings_get(self):
        """The whole page as plain data."""
        Branch = self.env['stock.warehouse']
        Branch._mart369_may_set_up()
        Rule = self.env['mart369.hub.rule'].sudo().with_context(active_test=False)
        rows = Rule.search([])
        branches = Branch.sudo().search([], order='company_id, id')
        hubs = branches.filtered(lambda b: has_pin(b.mart369_lat, b.mart369_lng))
        page = {
            'currency': self.env['mart369.serializable']._mart369_currency(),
            'mode': 'many' if rows.filtered('active') else 'one',
            'branches': [self._page_branch(b) for b in branches],
            'routes': {
                'hubs': [{'id': b.id, 'name': b.name or ''} for b in hubs],
                'cells': [{
                    'from': r.from_hub_id.id, 'to': r.to_hub_id.id,
                    'arrives': (r.arrives or '') if r.active else NOT_DELIVERED,
                    'cargo': bool(r.cargo), 'auto': bool(r.auto),
                } for r in rows if r.from_hub_id in hubs and r.to_hub_id in hubs],
                'choices': [w for w, _d in ROUTE_CHOICES] + [NOT_DELIVERED],
            },
            'fees': self._page_fees(),
            'slots': self._page_slots(),
            'whatsapp': self._page_whatsapp(),
            'areas': self.env['mart369.service.area'].sudo().search_count([]),
            'status': Branch.mart369_setup_status(),
        }
        page['explain'] = self._page_explain(page)
        return page

    def _page_branch(self, branch):
        pinned = has_pin(branch.mart369_lat, branch.mart369_lng)
        return {
            'id': branch.id,
            'name': branch.name or '',
            'company': branch.company_id.name or '',
            'pin': '%.6f, %.6f' % (branch.mart369_lat, branch.mart369_lng) if pinned else '',
            'quick': bool(branch.mart369_quick),
            'quickKm': round(branch.mart369_quick_km or 0.0, 2),
            'maybeKm': round(branch.mart369_maybe_km or 0.0, 2),
            'quickUpTo': quick_time_text(branch.mart369_quick_km) if branch.mart369_quick_km else '',
            'auto': bool(branch.mart369_auto),
            # Advanced: a branch's own fees, for a basket split between
            # branches of different companies (cart.py `_mart369_hub_rules`).
            'ownFees': bool(branch.mart369_own_fees),
            'quickFee': branch.mart369_quick_fee or 0.0,
            'expressFee': branch.mart369_express_fee or 0.0,
            'freeAbove': branch.mart369_free_above or 0.0,
            # The WhatsApp side fills these in (mart369_whatsapp_bridge).
            'shop': '', 'riders': None,
        }

    @api.model
    def _page_fees(self):
        # The records themselves, not `_mart369_rules()`: with Quick / Express
        # installed that answers with the senior's rules in a stand-in object
        # (the bridge reads his rules for this page itself).
        Rule = self.env['mart369.delivery.rule'].sudo().with_context(active_test=False)
        out = {}
        for mode, _name in MODES:
            rule = Rule.search([('mode', '=', mode)], order='active desc, id', limit=1)
            out[mode] = {
                'label': rule.label or '', 'eta': rule.eta or '',
                'fee': rule.fee or 0.0, 'freeAbove': rule.free_above or 0.0,
                'minOrder': rule.min_order or 0.0, 'active': bool(rule.active),
            } if rule else None
        return out

    # ---------------------------------------------------------------- slots
    # The slot list itself is edited here too (17 Nov 2026: "slots in one
    # place"). Always the list customers are offered: the website's own, or -
    # with the WhatsApp Quick / Express module - that module's, which the
    # bridge (mart369_whatsapp_bridge) puts in its place. Nothing here
    # deletes a slot: it is switched off.

    @api.model
    def _page_slot_records(self):
        """Every slot of the list in use, switched-off ones too."""
        return self.env['mart369.delivery.slot'].sudo().with_context(active_test=False).search(
            [], order='mode, sequence, id')

    @api.model
    def _page_slot_row(self, slot):
        """One slot as the page edits it."""
        return {
            'id': slot.id, 'mode': slot.mode, 'kind': slot.kind,
            'heading': slot.top or '', 'detail': slot.sub or '',
            'dayOffset': slot.day_offset or 0,
            'fromHour': round(slot.from_hour or 0.0, 2), 'toHour': round(slot.to_hour or 0.0, 2),
            'orderBefore': round(slot.order_before or 0.0, 2),
            'fee': round(slot.fee or 0.0, 2), 'capacity': slot.capacity or 0,
            'active': bool(slot.active),
        }

    @api.model
    def _page_slot_shown(self, slot):
        """How a slot is named in the summary line."""
        return slot.label or ' '.join(x for x in (slot.top, slot.sub) if x) or slot.key or ''

    @api.model
    def _page_slot_write(self, slot, vals):
        """Write one checked row (`slot` empty: a new one). `vals` uses the
        page's names: mode, kind, heading, detail, dayOffset, fromHour,
        toHour, orderBefore, fee, capacity, active."""
        out = {'mode': vals['mode'], 'kind': vals['kind'], 'top': vals['heading'],
               'sub': vals['detail'] or False, 'day_offset': vals['dayOffset'],
               'from_hour': vals['fromHour'], 'to_hour': vals['toHour'],
               'order_before': vals['orderBefore'], 'fee': vals['fee'],
               'capacity': vals['capacity'], 'active': vals['active']}
        Slot = self.env['mart369.delivery.slot'].sudo()
        if slot:
            if vals['mode'] != slot.mode:
                # a key is unique per storefront: moved to the other one, it
                # gets a key that is free there
                out['key'] = Slot._mart369_auto_key(vals['mode'], vals['kind'], vals['dayOffset'],
                                                    vals['fromHour'])
            slot.write(out)
        else:
            # the key is worked out from the day and the time (create())
            Slot.create(out)

    @api.model
    def _page_slots(self):
        Slot = self.env['mart369.delivery.slot'].sudo()
        records = self._page_slot_records()
        live = records.filtered('active')
        return {
            'on': bool(Slot._mart369_slots_on(self.env.company)),
            'count': len(live),
            'names': [self._page_slot_shown(s) for s in live[:6]],
            'rows': [self._page_slot_row(s) for s in records],
            # the website's slot has a detail line ("6 - 8 PM"); some lists do not
            'detail': True,
            'modes': [{'key': k, 'label': v} for k, v in MODES],
            'kinds': [{'key': k, 'label': v} for k, v in SLOT_KINDS],
        }

    @api.model
    def _page_whatsapp(self):
        """The WhatsApp delivery section, or None (mart369_whatsapp_bridge)."""
        return None

    @api.model
    def _page_explain(self, page):
        """How delivery decides, with these settings, in sentences."""
        _ = self.env._
        quick = [b for b in page['branches'] if b['quick'] and b['quickKm'] and b['pin']]
        lines = [_("The customer's map pin is measured to every branch that has the item in stock.")]
        if quick:
            reach = max(b['quickKm'] for b in quick)
            maybe = max(b['maybeKm'] for b in quick)
            lines.append(_('Within %(km)s km of a branch with Quick on, it comes Quick, in about '
                           '%(time)s at the edge (10 mins to pack, 5 mins a km).',
                           km='%g' % reach, time=quick_time_text(reach)))
            if maybe > reach:
                lines.append(_('Up to %s km, the customer is promised Express and it may still '
                               'come Quick when a rider is free.', '%g' % maybe))
        else:
            lines.append(_('No branch has Quick on with a map pin and a reach, so nothing comes '
                           'Quick by distance.'))
        if page['mode'] == 'many':
            sample = next((c for c in page['routes']['cells'] if c['arrives'] != NOT_DELIVERED), None)
            names = {h['id']: h['name'] for h in page['routes']['hubs']}
            line = _('Farther, the nearest branch that has it ships it, and Between branches says '
                     'when it arrives')
            if sample:
                line += _(' (e.g. %(a)s to %(b)s: %(w)s)', a=names.get(sample['from'], ''),
                          b=names.get(sample['to'], ''), w=sample['arrives'])
            lines.append(line + '.')
        else:
            lines.append(_('Farther, it ships Express from wherever it is in stock.'))
        fees = page['fees']
        parts = []
        for mode, name in MODES:
            fee = fees.get(mode)
            if not fee:
                continue
            if not fee['active']:
                parts.append(_('%s: no fee rule switched on', name))
            elif fee['freeAbove']:
                parts.append(_('%(n)s %(f)s, free above %(x)s', n=name, f='%g' % fee['fee'],
                               x='%g' % fee['freeAbove']))
            else:
                parts.append(_('%(n)s %(f)s', n=name, f='%g' % fee['fee']))
        if parts:
            lines.append(_('Fees: %s.', '; '.join(parts)))
        lines.append(_('Customers pick a delivery slot if they want to (%s slots).', page['slots']['count'])
                     if page['slots']['on'] else
                     _('Delivery slots are off: everyone gets the soonest delivery.'))
        wa = page.get('whatsapp')
        if wa:
            lines.append(_('WhatsApp orders in stock are promised within %(h)s hours, the next day '
                           'after %(c)s:00; others within %(d)s days.',
                           h=wa['quickHours'], c=wa['cutoffHour'], d=wa['expressDays']))
        return lines

    # ---------------------------------------------------------------- save

    @api.model
    def mart369_settings_save(self, payload):
        """Check every value, then write them all, or nothing.

        Returns {'ok': True, 'page': <the page again>} or
        {'ok': False, 'errors': [{section, row, field, message}]}."""
        self.env['stock.warehouse']._mart369_may_set_up()
        payload = payload if isinstance(payload, dict) else {}
        errors = []
        plan = self._page_check(payload, errors)
        if errors:
            return {'ok': False, 'errors': errors}
        try:
            with self.env.cr.savepoint():
                self._page_write(plan)
        except (UserError, ValidationError) as exc:
            return {'ok': False, 'errors': [{'section': '', 'row': '', 'field': '',
                                             'message': str(exc.args[0] if exc.args else exc)}]}
        return {'ok': True, 'page': self.mart369_settings_get()}

    def _number(self, raw, errors, where, what, low=0.0, high=None, whole=False):
        try:
            value = float(raw if raw not in (None, '') else 0)
        except (TypeError, ValueError):
            errors.append(dict(where, message=self.env._('%s is a number.', what)))
            return None
        if value < low or (high is not None and value > high):
            errors.append(dict(where, message=(
                self.env._('%(w)s must be between %(a)s and %(b)s.', w=what, a='%g' % low, b='%g' % high)
                if high is not None else self.env._('%s cannot be negative.', what))))
            return None
        return int(value) if whole else value

    @api.model
    def _page_check(self, payload, errors):
        """Every value, typed and checked, as a plan for `_page_write`."""
        _ = self.env._
        plan = {}
        if payload.get('mode') in ('one', 'many'):
            plan['mode'] = payload['mode']

        Branch = self.env['stock.warehouse'].sudo()
        plan['branches'] = []
        for row in payload.get('branches') or []:
            branch = Branch.browse(int(row.get('id') or 0)).exists()
            if not branch:
                continue
            where = {'section': 'branches', 'row': branch.id}
            vals = {}
            if 'quick' in row and bool(row['quick']) != branch.mart369_quick:
                vals['quick'] = bool(row['quick'])
            if 'ownFees' in row and bool(row['ownFees']) != branch.mart369_own_fees:
                vals['ownFees'] = bool(row['ownFees'])
            for key, field, what in (('quickFee', 'mart369_quick_fee', _('Quick fee')),
                                     ('expressFee', 'mart369_express_fee', _('Express fee')),
                                     ('freeAbove', 'mart369_free_above', _('Free above'))):
                if key in row:
                    value = self._number(row[key], errors, dict(where, field=key), what)
                    if value is not None and abs(value - (branch[field] or 0.0)) > 1e-6:
                        vals[key] = value
            reach = maybe = None
            for key, field, what in (('quickKm', 'mart369_quick_km', _('Quick up to')),
                                     ('maybeKm', 'mart369_maybe_km', _('Quick if possible up to'))):
                if key not in row:
                    continue
                value = self._number(row[key], errors, dict(where, field=key), what, high=500)
                if value is None:
                    continue
                if key == 'quickKm':
                    reach = value
                else:
                    maybe = value
                if abs(value - (branch[field] or 0.0)) > 1e-6:
                    vals[key] = value
            reach = branch.mart369_quick_km if reach is None else reach
            maybe = branch.mart369_maybe_km if maybe is None else maybe
            if maybe and maybe < reach:
                errors.append(dict(where, field='maybeKm',
                                   message=_('"Quick if possible" must be at least the Quick reach.')))
            if 'pin' in row:
                raw = str(row.get('pin') or '').strip()
                now = '%.6f, %.6f' % (branch.mart369_lat, branch.mart369_lng) \
                    if has_pin(branch.mart369_lat, branch.mart369_lng) else ''
                if raw != now:
                    parts = [p.strip() for p in raw.split(',')] if raw else ['', '']
                    try:
                        lat, lng = (float(parts[0] or 0), float(parts[1] or 0))
                        if len(parts) != 2 or not (-90 <= lat <= 90 and -180 <= lng <= 180):
                            raise ValueError
                        vals['pin'] = raw
                    except (ValueError, IndexError):
                        errors.append(dict(where, field='pin', message=_(
                            'Paste the location as two numbers with a comma between, '
                            'e.g. 25.2697, 55.3095.')))
            if vals:
                plan['branches'].append((branch, vals))

        Rule = self.env['mart369.hub.rule'].sudo().with_context(active_test=False)
        days_of = dict(ROUTE_CHOICES)
        plan['cells'] = []
        for cell in payload.get('cells') or []:
            a = Branch.browse(int(cell.get('from') or 0)).exists()
            b = Branch.browse(int(cell.get('to') or 0)).exists()
            if not a or not b or a == b:
                continue
            arrives = str(cell.get('arrives') or '').strip()
            if not arrives:
                errors.append({'section': 'routes', 'row': '%s-%s' % (a.id, b.id), 'field': 'arrives',
                               'message': _('Say when it arrives, or pick Not delivered.')})
                continue
            row = Rule.search([('from_hub_id', '=', a.id), ('to_hub_id', '=', b.id)], limit=1)
            plan['cells'].append((a, b, row, arrives, bool(cell.get('cargo')), days_of.get(arrives)))

        fees = payload.get('fees') or {}
        plan['fees'] = {}
        for mode, name in MODES:
            fee = fees.get(mode)
            if not isinstance(fee, dict):
                continue
            where = {'section': 'fees', 'row': mode}
            vals = {}
            for key, field, what in (('fee', 'fee', _('%s fee', name)),
                                     ('freeAbove', 'free_above', _('Free above')),
                                     ('minOrder', 'min_order', _('Minimum order'))):
                if key in fee:
                    value = self._number(fee[key], errors, dict(where, field=key), what)
                    if value is not None:
                        vals[field] = value
            for key in ('label', 'eta'):
                if key in fee:
                    text = str(fee.get(key) or '').strip()
                    if not text:
                        errors.append(dict(where, field=key, message=_(
                            'Write the words the customer reads.') if key == 'eta' else _(
                            'A storefront needs a name.')))
                    else:
                        vals[key] = text
            if 'active' in fee:
                vals['active'] = bool(fee['active'])
            if vals:
                plan['fees'][mode] = vals

        if 'slotsOn' in payload:
            plan['slots_on'] = bool(payload['slotsOn'])
        if isinstance(payload.get('slots'), list):
            plan['slots'] = self._page_slots_check(payload['slots'], errors)
        if isinstance(payload.get('whatsapp'), dict):
            plan['whatsapp'] = self._page_whatsapp_check(payload['whatsapp'], errors)
        return plan

    @api.model
    def _page_slots_check(self, rows, errors):
        """The slot rows, checked: [(record or empty, vals)] for the changed
        and the new ones. The same rules as the slot records themselves."""
        _ = self.env._
        records = self._page_slot_records()
        by_id = {r.id: r for r in records}
        modes, kinds = dict(MODES), dict(SLOT_KINDS)
        out = []
        for n, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            try:
                rid = int(row.get('id') or 0)
            except (TypeError, ValueError):
                rid = 0
            record = by_id.get(rid) if rid else None
            if rid and not record:
                continue                      # gone meanwhile: nothing to write
            where = {'section': 'slots', 'row': rid or str(row.get('key') or 'new-%d' % n)}
            vals = {}
            mode, kind = row.get('mode'), row.get('kind')
            if mode not in modes:
                errors.append(dict(where, field='mode', message=_('Pick Quick or Express.')))
            if kind not in kinds:
                errors.append(dict(where, field='kind', message=_('Pick Now, a time window or a number of days.')))
            vals.update(mode=mode, kind=kind)
            heading = str(row.get('heading') or '').strip()
            if not heading:
                errors.append(dict(where, field='heading', message=_('Write the words the customer sees, e.g. Today.')))
            vals['heading'] = heading
            vals['detail'] = str(row.get('detail') or '').strip()
            for key, what, high, whole in (('dayOffset', _('Days ahead'), 60, True),
                                           ('fromHour', _('From'), 24, False),
                                           ('toHour', _('To'), 24, False),
                                           ('orderBefore', _('Order before'), 24, False),
                                           ('fee', _('Extra fee'), None, False),
                                           ('capacity', _('Orders per slot'), None, True)):
                value = self._number(row.get(key), errors, dict(where, field=key), what, high=high, whole=whole)
                vals[key] = value
            if kind == 'window' and vals['fromHour'] is not None and vals['toHour'] is not None \
                    and vals['fromHour'] >= vals['toHour']:
                errors.append(dict(where, field='toHour', message=_('"To" must be later than "From".')))
            vals['active'] = bool(row.get('active', True))
            if any(v is None for v in vals.values()):
                continue                      # an error is already noted
            if record:
                now = self._page_slot_row(record)
                if all(self._page_same(now.get(k), v) for k, v in vals.items()):
                    continue                  # unchanged
            out.append((record, vals))
        return out

    @staticmethod
    def _page_same(old, new):
        if isinstance(old, (int, float)) and isinstance(new, (int, float)) and not isinstance(old, bool):
            return abs(float(old) - float(new)) < 1e-6
        return old == new

    @api.model
    def _page_whatsapp_check(self, data, errors):
        return {}

    @api.model
    def _page_write(self, plan):
        Branch = self.env['stock.warehouse']
        for branch, vals in plan.get('branches', []):
            Branch.mart369_admin_save(branch.id, vals)
            self._page_branch_saved(branch, vals)

        Rule = self.env['mart369.hub.rule'].sudo().with_context(active_test=False)
        if plan.get('mode') == 'one':
            Rule.search([('active', '=', True)]).write({'active': False})
        elif plan.get('mode') == 'many' and not Rule.search_count([('active', '=', True)]):
            # Back on: what was there before comes back, and the pairs that
            # never had a row are worked out from the distance.
            Rule.search([('active', '=', False), ('auto', '=', False)]).write({'active': True})
            Rule.search([('active', '=', False), ('auto', '=', True)]).write({'active': True})
            Rule._mart369_fill_routes(force=True)

        if plan.get('mode', 'many') == 'many':
            for a, b, row, arrives, cargo, days in plan.get('cells', []):
                if arrives == NOT_DELIVERED:
                    if row and row.active:
                        row.write({'active': False, 'auto': False})
                    continue
                vals = {}
                if not row:
                    Rule.create({'from_hub_id': a.id, 'to_hub_id': b.id, 'arrives': arrives,
                                 'days': days if days is not None else 1, 'cargo': cargo})
                    continue
                if not row.active:
                    vals['active'] = True
                if (row.arrives or '') != arrives:
                    vals['arrives'] = arrives
                    if days is not None:
                        vals['days'] = days
                if bool(row.cargo) != cargo:
                    vals['cargo'] = cargo
                if vals:
                    row.write(vals)

        for mode, vals in plan.get('fees', {}).items():
            self._page_fee_write(mode, vals)

        if 'slots_on' in plan:
            self.env.company.sudo().write({'mart369_slots_on': plan['slots_on']})
        for record, vals in plan.get('slots', []):
            self._page_slot_write(record, vals)
        if plan.get('whatsapp'):
            self._page_whatsapp_write(plan['whatsapp'])

    @api.model
    def _page_branch_saved(self, branch, vals):
        """After a branch is saved; the WhatsApp side keeps its shop in step."""

    @api.model
    def _page_fee_write(self, mode, vals):
        Rule = self.env['mart369.delivery.rule'].sudo().with_context(active_test=False)
        rule = Rule.search([('mode', '=', mode)], limit=1)
        if rule:
            rule.write(vals)

    @api.model
    def _page_whatsapp_write(self, vals):
        """The WhatsApp section (mart369_whatsapp_bridge)."""
