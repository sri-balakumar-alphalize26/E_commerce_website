"""Delivery that sets itself up.

Setting a branch up for delivery used to mean five screens: the warehouse in
Inventory, its address, its pin and Quick reach in the console, its routes to
the other hubs in Hub rules, and (with WhatsApp orders) a delivery shop of its
own. Everything a machine can work out is now worked out:

* **the pin** - from the branch's address, the same lookup as "Find from the
  address";
* **Quick** - on, with the usual reaches (5 km, "Quick if possible" 15 km), once
  the pin is known;
* **routes to the other hubs** - while the hub rules are on, a missing pair
  gets a row from the straight-line distance (Next day / In 2-3 days / Cargo);
* the WhatsApp side adds its delivery shop (mart369_whatsapp_bridge).

The one rule: **it only fills what is empty or missing, never what a person
set.** Pins and Quick are only ever touched on a branch made after this module
(`mart369_auto`, on for every new warehouse); the moment somebody saves its
Quick settings by hand, it is theirs. Routes are only added, never changed,
and an archived route counts as somebody's "no".

A background job does it (hourly, and at once when a warehouse is made, its
address changes, or someone presses "Set up automatically"). What only a
person can do - give the address, add a rider - is what the checklist shows.
"""

import logging

import requests

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

from .branch import (DEFAULT_MAYBE_KM, DEFAULT_QUICK_KM, EDITOR_GROUP, has_pin,
                     haversine_km, quick_time_text)

_logger = logging.getLogger(__name__)

ADDRESS_FIELDS = {'street', 'street2', 'city', 'zip', 'state_id', 'country_id'}

# A route worked out from the distance between two hubs: up to this many km,
# this many days, these words, and the Cargo badge or not.
ROUTE_BANDS = (
    (150.0, 1, 'Next day', False),
    (400.0, 2, 'In 2-3 days', False),
    (None, 3, 'In 3-4 days', True),
)

# A check's state: done, being done by the shop, needs a person, or not used
# on purpose.
OK, WAIT, TODO, OFF = 'ok', 'wait', 'todo', 'off'


def route_for_km(km):
    """(days, arrives, cargo) for two hubs `km` apart in a straight line."""
    for most, days, arrives, cargo in ROUTE_BANDS:
        if most is None or km <= most:
            return days, arrives, cargo
    return ROUTE_BANDS[-1][1:]


def address_text(partner):
    """The address as one line, or '' when there is none to look up."""
    if not partner:
        return ''
    parts = [partner.street, partner.street2, partner.city, partner.zip,
             partner.state_id.name, partner.country_id.name]
    if not (partner.street or partner.city or partner.zip):
        return ''
    return ', '.join(p.strip() for p in parts if p and p.strip())


def check(key, state, text, fix=''):
    return {'key': key, 'state': state, 'text': text, 'fix': fix}


class Mart369BranchAutoSetup(models.Model):
    _inherit = 'stock.warehouse'

    mart369_auto = fields.Boolean(
        string='Delivery sets itself up', default=False, copy=False,
        help="On for a branch made after automatic setup arrived: its pin is "
             "found from its address and Quick switched on by itself. Saving "
             "its Quick settings by hand turns this off, and from then on "
             "nothing is changed for it.")
    mart369_auto_tried = fields.Char(
        copy=False, help="The address last looked up on the map, so the same "
                         "address is not asked about every hour.")
    mart369_auto_note = fields.Char(
        string='Map lookup', copy=False,
        help="What the last automatic map lookup said.")

    # The checklist, for the list in Odoo (369 Mart > Store > Delivery setup).
    mart369_setup_ok = fields.Boolean(
        string='Ready', compute='_compute_mart369_setup')
    mart369_setup_state = fields.Selection(
        [(OK, 'Ready'), (WAIT, 'Setting up'), (TODO, 'Needs you'), (OFF, 'Not delivering')],
        string='Delivery', compute='_compute_mart369_setup')
    mart369_setup_done = fields.Char(
        string='Set up', compute='_compute_mart369_setup')
    mart369_setup_todo = fields.Char(
        string='To do', compute='_compute_mart369_setup')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals.setdefault('mart369_auto', True)
        branches = super().create(vals_list)
        self._mart369_auto_soon()
        return branches

    def write(self, vals):
        moved = 'partner_id' in vals
        result = super().write(vals)
        if moved and any(b.mart369_auto for b in self):
            self._mart369_auto_soon()
        return result

    def _compute_mart369_setup(self):
        for branch in self:
            checks = branch.sudo()._mart369_setup_checks()
            branch.mart369_setup_ok = not any(c['state'] in (TODO, WAIT) for c in checks)
            branch.mart369_setup_state = branch._mart369_setup_state(checks)
            branch.mart369_setup_done = ' · '.join(
                c['text'] for c in checks if c['state'] in (OK, OFF))
            branch.mart369_setup_todo = ' · '.join(
                c['text'] for c in checks if c['state'] in (TODO, WAIT))

    # ------------------------------------------------------------- running

    @api.model
    def _mart369_auto_soon(self):
        """Run the setup job as soon as the server can, not on the hour."""
        cron = self.env.ref('mart369_cart.ir_cron_delivery_autosetup',
                            raise_if_not_found=False)
        if cron and cron.sudo().active:
            cron.sudo()._trigger()

    @api.model
    def _cron_mart369_auto_setup(self):
        self.sudo()._mart369_auto_setup()

    @api.model
    def _mart369_auto_setup(self):
        """Fill in what delivery can work out by itself. Returns what was
        done, one plain-words line each. Running it twice changes nothing."""
        done = []
        for branch in self.sudo().search([('mart369_auto', '=', True)]):
            if not has_pin(branch.mart369_lat, branch.mart369_lng):
                done += branch._mart369_auto_pin()
            done += branch._mart369_auto_quick()
        done += self.env['mart369.hub.rule'].sudo()._mart369_fill_routes()
        for line in done:
            _logger.info("Delivery setup: %s", line)
        return done

    def _mart369_address_partner(self):
        self.ensure_one()
        return (self.partner_id or self.company_id.partner_id).sudo()

    def _mart369_auto_pin(self):
        """Look this branch's address up on the map, once per address."""
        self.ensure_one()
        partner = self._mart369_address_partner()
        text = address_text(partner)
        if not text or text == self.mart369_auto_tried:
            return []
        try:
            spot = self.env['mart369.postcode'].sudo()._mart369_locate(partner)
        except UserError as exc:
            if isinstance(exc.__cause__, requests.RequestException):
                # The map could not be reached: ask again next time.
                self.mart369_auto_note = str(exc)
                return []
            self.write({'mart369_auto_tried': text, 'mart369_auto_note': str(exc)})
            return []
        except Exception as exc:  # noqa: BLE001 - a lookup must never stop the job
            _logger.warning("Delivery setup: map lookup for %s failed: %s", self.name, exc)
            return []
        vals = {'mart369_auto_tried': text, 'mart369_auto_note': spot.get('message') or ''}
        if spot.get('found') and spot.get('lat') is not None:
            vals.update(mart369_lat=spot['lat'], mart369_lng=spot['lng'])
        self.write(vals)
        if 'mart369_lat' in vals:
            return [self.env._('%(branch)s: found on the map from its address.',
                               branch=self.name)]
        return []

    def _mart369_auto_quick(self):
        """Quick on with the usual reaches, once the pin is known."""
        self.ensure_one()
        if self.mart369_quick or not has_pin(self.mart369_lat, self.mart369_lng):
            return []
        reach = self.mart369_quick_km or DEFAULT_QUICK_KM
        self.write({
            'mart369_quick': True,
            'mart369_quick_km': reach,
            'mart369_maybe_km': max(self.mart369_maybe_km, DEFAULT_MAYBE_KM, reach),
        })
        return [self.env._('%(branch)s: Quick switched on, up to %(km)s km.',
                           branch=self.name, km='%g' % reach)]

    # ----------------------------------------------------------- the checks

    def _mart369_setup_checks(self):
        """What is done for this branch and what is left:
        [{'key', 'state', 'text', 'fix'}]. `state` is ok, wait (the shop is
        doing it), todo (a person must) or off (not used, on purpose); `fix`
        names the screen that changes it. Other modules add their own."""
        self.ensure_one()
        _ = self.env._
        checks = []
        partner = self._mart369_address_partner()
        text = address_text(partner)
        pinned = has_pin(self.mart369_lat, self.mart369_lng)

        if text:
            checks.append(check('address', OK, _('Address: %s', partner.city or text), 'address'))
        elif not pinned:
            checks.append(check('address', TODO if self.mart369_auto else OFF,
                                _('Add the branch address in Odoo'), 'address'))

        if pinned:
            checks.append(check('pin', OK, _('On the map'), 'branch'))
        elif self.mart369_auto and text and text != self.mart369_auto_tried:
            checks.append(check('pin', WAIT, _('Finding it on the map…'), 'branch'))
        elif self.mart369_auto:
            checks.append(check('pin', TODO, self.mart369_auto_note or _('Pick it on the map'),
                                'branch'))
        else:
            checks.append(check('pin', OFF, _('No map pin: not delivering from here'),
                                'branch'))

        if self._mart369_ready():
            checks.append(check('quick', OK, _('Quick up to %(km)s km (about %(time)s)',
                                               km='%g' % self.mart369_quick_km,
                                               time=quick_time_text(self.mart369_quick_km)),
                                'branch'))
        elif self.mart369_quick:
            checks.append(check('quick', TODO, _('Quick is on but reaches nobody: set the reach'),
                                'branch'))
        elif self.mart369_auto and not pinned:
            checks.append(check('quick', WAIT, _('Quick turns on once the pin is found'),
                                'branch'))
        else:
            checks.append(check('quick', OFF, _('Quick off: Express only'), 'branch'))

        Rule = self.env['mart369.hub.rule'].sudo().with_context(active_test=False)
        if pinned and self.env['mart369.hub.rule']._mart369_table():
            others = self.sudo().search([('id', '!=', self.id)]).filtered(
                lambda b: has_pin(b.mart369_lat, b.mart369_lng))
            rows = Rule.search(['|', ('from_hub_id', '=', self.id), ('to_hub_id', '=', self.id)])
            pairs = {(r.from_hub_id.id, r.to_hub_id.id) for r in rows}
            missing = sum(1 for o in others for pair in ((self.id, o.id), (o.id, self.id))
                          if pair not in pairs)
            guessed = len(rows.filtered('auto'))
            if missing:
                checks.append(check('routes', WAIT, _('%s routes to other hubs being added', missing),
                                    'routes'))
            elif others:
                line = _('Routes to %s other hubs', len(others))
                if guessed:
                    line += _(' (%s worked out from distance: check them)', guessed)
                checks.append(check('routes', OK, line, 'routes'))
        return checks

    @api.model
    def _mart369_setup_state(self, checks):
        """One word for a branch: todo, wait, off (no pin, not set up on
        purpose - not a delivery branch) or ok."""
        states = {c['state'] for c in checks}
        if TODO in states:
            return TODO
        if WAIT in states:
            return WAIT
        if any(c['key'] == 'pin' and c['state'] == OFF for c in checks):
            return OFF
        return OK

    @api.model
    def _mart369_setup_shop_checks(self):
        """The same for what the whole shop shares: fees, slots, hub routes."""
        _ = self.env._
        checks = []
        rules = self.env['mart369.delivery.rule']._mart369_rules()
        for mode, name in (('quick', _('Quick')), ('all', _('Express'))):
            rule = rules.get(mode)
            if rule:
                line = (_('%(name)s fee %(fee)s, free above %(free)s', name=name,
                          fee='%g' % rule.fee, free='%g' % rule.free_above)
                        if rule.free_above else
                        _('%(name)s fee %(fee)s', name=name, fee='%g' % rule.fee))
                checks.append(check('fee_' + mode, OK, line, 'fees'))
            else:
                checks.append(check('fee_' + mode, TODO,
                                    _('%s has no delivery fee rule switched on', name), 'fees'))
        Slot = self.env['mart369.delivery.slot'].sudo()
        if not Slot._mart369_slots_on(self.env.company):
            checks.append(check('slots', OFF, _('Delivery slots off: soonest delivery'), 'slots'))
        else:
            count = Slot.search_count([])
            checks.append(check('slots', OK, _('%s delivery slots', count), 'slots') if count else
                          check('slots', TODO, _('Slots are on but there are none: add one or '
                                                 'switch slots off'), 'slots'))
        table = self.env['mart369.hub.rule']._mart369_table()
        checks.append(check('hubs', OK, _('Hub routes on (%s routes)', len(table)), 'routes')
                      if table else
                      check('hubs', OFF, _('Hub routes off: one area'), 'routes'))
        return checks

    # ---------------------------------------------------- for both screens

    @api.model
    def _mart369_may_set_up(self):
        user = self.env.user
        if not (user.has_group(EDITOR_GROUP) or user.has_group('base.group_system')):
            raise AccessError(self.env._('You do not have access to this.'))

    @api.model
    def mart369_setup_status(self):
        """The checklist for the console and the list in Odoo:
        {'shop': [checks], 'branches': [{id, name, company, auto, ready,
        checks}], 'todo': n}."""
        self._mart369_may_set_up()
        rows = []
        for branch in self.sudo().search([], order='company_id, id'):
            checks = branch._mart369_setup_checks()
            states = {c['state'] for c in checks}
            rows.append({
                'id': branch.id,
                'name': branch.name or '',
                'company': branch.company_id.name or '',
                'auto': branch.mart369_auto,
                'ready': not states & {TODO, WAIT},
                # ready, working (the shop is doing it), todo (a person must),
                # off (no pin, not set up on purpose: not a delivery branch).
                'state': branch._mart369_setup_state(checks),
                'checks': checks,
            })
        shop = self._mart369_setup_shop_checks()
        todo = sum(1 for c in shop if c['state'] == TODO) + sum(
            1 for row in rows for c in row['checks'] if c['state'] == TODO)
        working = sum(1 for row in rows if row['state'] == WAIT)
        return {'shop': shop, 'branches': rows, 'todo': todo, 'working': working}

    @api.model
    def mart369_setup_run(self):
        """"Set up automatically now": the job, at once, then the checklist."""
        self._mart369_may_set_up()
        done = self.sudo()._mart369_auto_setup()
        return dict(self.mart369_setup_status(), done=done)

    def action_mart369_auto_setup(self):
        """The button in Odoo: run it, say what it did and what is left, then
        take the person to what is left - the one branch, or the list of
        them - instead of a "see To do" that leads nowhere (13 Nov 2026)."""
        _ = self.env._
        status = self.env['stock.warehouse'].mart369_setup_run()
        done = status.get('done') or []
        left = ['%s: %s' % (row['name'], c['text'])
                for row in status['branches'] for c in row['checks'] if c['state'] == TODO]
        left += [c['text'] for c in status['shop'] if c['state'] == TODO]
        parts = [' '.join(done) if done else _(
            'Nothing new to fill in: everything the shop can work out is done.')]
        if left:
            parts.append(_('Still needs you: %s', ' · '.join(left)))
        needing = [row['id'] for row in status['branches'] if row['state'] == TODO]
        if len(needing) == 1:
            after = self.browse(needing)._mart369_setup_form()
        elif needing:
            after = dict(self.env['ir.actions.act_window']._for_xml_id(
                'mart369_cart.action_mart369_delivery_setup'),
                name=_('Needs you'), domain=[('id', 'in', needing)])
        else:
            after = {'type': 'ir.actions.client', 'tag': 'soft_reload'}
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Delivery set up'),
                'message': ' '.join(parts),
                'type': 'warning' if left else ('success' if done else 'info'),
                'sticky': bool(done or left),
                'next': after,
            },
        }

    def _mart369_setup_form(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.name,
            'res_model': 'stock.warehouse',
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(self.env.ref('mart369_cart.mart369_delivery_setup_view_form').id, 'form')],
            'target': 'current',
        }

    # Where each kind of to-do is put right. Riders and shops belong to the
    # WhatsApp delivery module, so they are looked up, not required.
    FIX_ACTIONS = {
        'branch': 'mart369_cart.action_mart369_delivery_desk',
        'fees': 'mart369_cart.action_mart369_delivery_desk',
        'slots': 'mart369_cart.action_mart369_delivery_desk',
        'routes': 'mart369_cart.action_mart369_hub_rules',
        'riders': 'sales_automation_delivery.action_sa_delivery_partner',
        'shop': 'sales_automation_delivery.action_sa_delivery_shop',
    }

    def action_mart369_fix(self):
        """"Fix it": the screen that puts this branch's first to-do right."""
        self.ensure_one()
        todo = next((c for c in self.sudo()._mart369_setup_checks() if c['state'] == TODO), None)
        if not todo:
            return self._mart369_setup_form()
        if todo['fix'] == 'address':
            partner = self._mart369_address_partner()
            return {'type': 'ir.actions.act_window', 'res_model': 'res.partner',
                    'res_id': partner.id, 'view_mode': 'form',
                    'views': [(False, 'form')], 'target': 'current',
                    'name': self.env._('Address of %s', self.name)}
        xmlid = self.FIX_ACTIONS.get(todo['fix'])
        if not xmlid or not self.env.ref(xmlid, raise_if_not_found=False):
            return self._mart369_setup_form()
        return self.env['ir.actions.actions']._for_xml_id(xmlid)


class Mart369PartnerAutoSetup(models.Model):
    _inherit = 'res.partner'

    def write(self, vals):
        result = super().write(vals)
        if ADDRESS_FIELDS & set(vals):
            Branch = self.env['stock.warehouse'].sudo()
            if Branch.search_count([('mart369_auto', '=', True), '|',
                                    ('partner_id', 'in', self.ids),
                                    ('company_id.partner_id', 'in', self.ids)], limit=1):
                Branch._mart369_auto_soon()
        return result
