# -*- coding: utf-8 -*-
"""Who carries the parcel - our own rider, or an outside courier."""

import logging
from datetime import timedelta

import pytz

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


def _tz_get(self):
    return [(tz, tz) for tz in sorted(pytz.all_timezones,
                                      key=lambda t: t if not t.startswith(
                                          'Etc/') else '_')]


class SaDeliveryPartner(models.Model):
    _name = 'sa.delivery.partner'
    _description = 'Delivery Rider or Courier'
    _order = 'kind, sequence, id'
    _rec_name = 'name'

    name = fields.Char('Name', required=True)
    sequence = fields.Integer(
        default=10, help="Who is offered a job first within their kind.")
    active = fields.Boolean(default=True)

    kind = fields.Selection([
        ('own', 'Own Rider'),
        ('third_party', 'Delivery Partner'),
    ], string='Kind', default='own', required=True,
        help="Own riders are always offered a job before outside couriers.")

    partner_id = fields.Many2one(
        'res.partner', string='Contact',
        help="Optional. Links the rider to a contact so their deliveries can "
             "be seen alongside the rest of their record.")
    phone = fields.Char(
        'WhatsApp Number', required=True,
        help="The number the job is sent to, and the only number whose "
             "replies are accepted for it. Digits and country code, e.g. "
             "96891234567.")

    shop_ids = fields.Many2many(
        'sa.delivery.shop', 'sa_delivery_partner_shop_rel',
        'partner_id', 'shop_id', string='Shops Served',
        help="Leave empty to serve every shop.")

    # ---- On duty ----
    on_duty = fields.Boolean(
        'On Duty', default=False, tracking=True,
        help="Only riders on duty are offered new work. A rider who has gone "
             "home keeps the jobs already in their hands - taking those away "
             "would strand a parcel halfway.")
    duty_since = fields.Datetime('On Duty Since', readonly=True)
    # Where the rider was when they last checked in with no job in hand. Kept
    # so waiting work can be offered to whoever is nearest, which is the whole
    # reason the app sends a position while idle.
    last_lat = fields.Float('Last Latitude', digits=(10, 7), readonly=True)
    last_lng = fields.Float('Last Longitude', digits=(10, 7), readonly=True)
    last_fix_on = fields.Datetime('Last Position At', readonly=True)
    last_battery = fields.Float(
        'Battery', readonly=True,
        help="0 to 1, as the phone reported it. A rider at 5% is a poor "
             "choice for a long run even if they are the closest.")

    tz = fields.Selection(
        _tz_get, string='Timezone',
        default=lambda self: self.env.company.partner_id.tz or 'Asia/Muscat',
        help="What the app shows this rider. 369ai stores every time in UTC; "
             "this is only how it is displayed.")

    user_id = fields.Many2one(
        'res.users', string='369ai User',
        help="Optional. The app does not need one - riders log in with their "
             "number and a code - but linking a user lets record rules back "
             "up the API's own scoping, and puts a name on the audit trail.")

    notes = fields.Text('Notes')

    delivery_count = fields.Integer('Deliveries', compute='_compute_counts')
    open_count = fields.Integer('In Hand', compute='_compute_counts')

    # ---- Fleet (Call a Rider, 3 Oct 2026) ----
    job_ids = fields.One2many('stock.picking', 'sa_delivery_partner_id', string='Jobs')
    is_busy = fields.Boolean('Busy', compute='_compute_fleet', store=True,
                             help="Has a job in hand (accepted up to delivered).")
    fleet_state = fields.Selection([
        ('off', 'Off duty'), ('idle', 'On duty - free'), ('busy', 'On duty - busy'),
    ], 'Fleet', compute='_compute_fleet', store=True)
    idle_since = fields.Datetime('Idle Since', readonly=True)
    address_short = fields.Char('Where (area)', readonly=True,
                                help="Looked up from the last GPS position.")
    address_full = fields.Char('Where (full address)', readonly=True)
    geocoded_on = fields.Datetime('Address Looked Up', readonly=True)

    @api.depends('on_duty', 'job_ids.sa_delivery_state')
    def _compute_fleet(self):
        busy_states = ('accepted', 'picked', 'dispatched', 'out_for_delivery', 'returning')
        for r in self:
            busy = any(j.sa_delivery_state in busy_states for j in r.job_ids)
            r.is_busy = busy
            r.fleet_state = 'busy' if (r.on_duty and busy) else ('idle' if r.on_duty else 'off')

    def _sa_geocode(self, max_age_minutes=0):
        """Turn the last position into words. Never raises."""
        now = fields.Datetime.now()
        Geo = self.env['sa.geocode.cache'].sudo()
        for r in self:
            if not r.last_lat or not r.last_lng:
                continue
            if max_age_minutes and r.geocoded_on and (now - r.geocoded_on) < timedelta(minutes=max_age_minutes):
                continue
            try:
                short, full = Geo.sa_reverse(r.last_lat, r.last_lng)
            except Exception:  # noqa: BLE001
                continue
            if short or full:
                r.sudo().write({'address_short': short, 'address_full': full, 'geocoded_on': now})
        return True

    def _compute_counts(self):
        Picking = self.env['stock.picking']
        for rider in self:
            rider.delivery_count = Picking.search_count(
                [('sa_delivery_partner_id', '=', rider.id)])
            rider.open_count = Picking.search_count([
                ('sa_delivery_partner_id', '=', rider.id),
                ('sa_delivery_state', 'in', ('offered', 'accepted', 'picked')),
            ])

    @api.model
    def _sa_digits(self, phone):
        return ''.join(c for c in (phone or '') if c.isdigit())

    @api.model
    def _sa_by_phone(self, phone):
        """The rider a WhatsApp number belongs to.

        Matched on the last nine digits, the same rule the vendor and customer
        code paths use: a number reaches us with and without its country code
        depending on how the group was joined.
        """
        digits = self._sa_digits(phone)
        if len(digits) < 8:
            return self.browse()
        for rider in self.sudo().search([]):
            mine = self._sa_digits(rider.phone)
            if mine and mine[-9:] == digits[-9:]:
                return rider
        return self.browse()

    @api.model
    def _sa_pick_for(self, shop, exclude=None):
        """Who to offer this shop's next job to.

        **On duty only.** A rider who has clocked off gets nothing: the job
        waits in To Dispatch until somebody clocks on, which is better than
        pushing it at a phone that is face-down on a kitchen table. Within the
        riders who are on duty, own riders come before outside couriers, then
        sequence decides.

        A rider with no shops listed serves every shop - the common case for a
        business with one branch, and it means the module works before anything
        is configured.
        """
        riders = self.sudo().search([('on_duty', '=', True)])
        if 'sa_sos_open' in self._fields:
            riders = riders.filtered(lambda r: not r.sa_sos_open)     # an open SOS: no job (6 Oct 2026)
        settings = self.env['sa.delivery.settings'].sudo().get_settings()
        if 'third_party_enabled' in settings._fields and not settings.third_party_enabled:
            riders = riders.filtered(lambda r: r.kind != 'third_party')
        if exclude:
            riders = riders - exclude.sudo()
        if shop:
            riders = riders.filtered(
                lambda r: not r.shop_ids or shop in r.shop_ids)
        for kind in ('own', 'third_party'):
            of_kind = riders.filtered(lambda r, k=kind: r.kind == k)
            if of_kind:
                return of_kind[0]
        return self.browse()

    def _sa_waiting_jobs(self):
        """Jobs left unassigned because nobody was on duty."""
        self.ensure_one()
        domain = [('sa_delivery_state', '=', 'to_assign'),
                  ('state', 'not in', ('done', 'cancel'))]
        jobs = self.env['stock.picking'].sudo().search(domain,
                                                       order='id asc')
        if self.shop_ids:
            jobs = jobs.filtered(
                lambda p: not p.sa_shop_id or p.sa_shop_id in self.shop_ids)
        return jobs

    def sa_set_duty(self, on_duty, lat=None, lng=None):
        """Clock on or off.

        Clocking **on** sweeps up the work that was waiting for somebody:
        without this a job confirmed at 7am while everyone was off duty would
        sit in To Dispatch until a human noticed, which is the exact gap this
        was meant to close.

        Clocking **off** touches nothing already accepted - taking a parcel's
        job away mid-route would strand it.
        """
        self.ensure_one()
        vals = {'on_duty': bool(on_duty),
                'duty_since': fields.Datetime.now() if on_duty else False}
        if lat is not None and lng is not None:
            vals.update({'last_lat': lat, 'last_lng': lng, 'last_fix_on': fields.Datetime.now()})
        if on_duty:
            vals['idle_since'] = fields.Datetime.now()
        self.write(vals)
        if lat is not None and lng is not None:
            self._sa_geocode()
        _logger.info("Delivery: %s is %s duty", self.name,
                     'on' if on_duty else 'off')
        if not on_duty:
            return 0
        # Waiting jobs are swept up only when riders are called automatically;
        # otherwise the counter presses Call a Rider (3 Oct 2026).
        if not self.env['sa.delivery.settings'].sudo().get_settings().auto_call_rider_on_packed:
            return 0

        taken = 0
        for job in self._sa_waiting_jobs():
            job.sa_delivery_partner_id = self.id
            # `sa_action_offer` carries its own outbox-guard claim, so a job
            # cannot be offered twice even if two riders clock on together.
            job.sa_action_offer()
            if job.sa_delivery_state == 'offered':
                taken += 1
        if taken:
            _logger.info("Delivery: %s picked up %d waiting job(s) on "
                         "clocking in", self.name, taken)
        return taken

    def action_toggle_duty(self):
        for rider in self:
            rider.sa_set_duty(not rider.on_duty)
        return True

    def action_open_deliveries(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Deliveries - %s', self.name),
            'res_model': 'stock.picking',
            'view_mode': 'list,form',
            'domain': [('sa_delivery_partner_id', '=', self.id)],
            'context': {'search_default_group_delivery_state': 1},
        }
