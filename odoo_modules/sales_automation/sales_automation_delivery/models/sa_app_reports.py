# -*- coding: utf-8 -*-
"""Rider app "next round" items 6 and 8 (6 Oct 2026): crash reports from the
riders' phones, and SOS alerts.

Crash reports: the app keeps every crash on the phone and posts them when
online (`POST /api/delivery/app/crash`, up to 20 a call); one record per
report under the rider, a list in Delivery > Fleet > App Crashes.

SOS: the rider holds the red button 3 s; the app posts position, job and
emergency contacts (`POST /api/delivery/sos`, retried every 20 s until a
200, so a repeat of the same rider + time is one alert). The alert is stored
under the rider, the delivery managers get an Odoo notification at once,
the office number gets a WhatsApp with name, phone, job and a map link, and
the shop card shows it in red until somebody presses Handled."""
import json
import logging
from datetime import datetime

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


def _parse_dt(value):
    """'2026-10-06T07:12:44Z' / '...+04:00' / naive -> naive UTC, or now."""
    if not value:
        return fields.Datetime.now()
    try:
        s = str(value).strip().replace('Z', '+00:00')
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is not None:
            dt = (dt - dt.utcoffset()).replace(tzinfo=None)
        return dt.replace(microsecond=0)
    except (ValueError, TypeError):
        return fields.Datetime.now()


class SaDeliverySettingsSos(models.Model):
    _inherit = 'sa.delivery.settings'

    sos_phone = fields.Char(
        'SOS alerts: office WhatsApp number',
        help="Gets a WhatsApp the moment a rider presses SOS (name, phone, job, map link). "
             "Empty: the phone of the job's shop, else the company phone.")


class SaDeliveryPartnerSos(models.Model):
    _inherit = 'sa.delivery.partner'

    # A rider with an SOS nobody has handled is not offered work (6 Oct
    # 2026): Not available in the Call a Rider dialog, skipped by every
    # automatic pick, red on the Live Map. Back to Available at Handled.
    sa_sos_open = fields.Boolean('SOS Open', compute='_compute_sa_sos_open')

    @api.model
    def _sa_sos_open_ids(self):
        if 'sa.sos.alert' not in self.env:
            return []
        rows = self.env['sa.sos.alert'].sudo().read_group([('state', '=', 'new')], ['rider_id'], ['rider_id'])
        return [r['rider_id'][0] for r in rows if r.get('rider_id')]

    def _compute_sa_sos_open(self):
        open_ids = set(self._sa_sos_open_ids())
        for r in self:
            r.sa_sos_open = r.id in open_ids


class SaAppCrash(models.Model):
    _name = 'sa.app.crash'
    _description = 'Rider App Crash Report'
    _order = 'at desc, id desc'

    rider_id = fields.Many2one('sa.delivery.partner', 'Rider', required=True, index=True, ondelete='cascade')
    at = fields.Datetime('Crashed At', required=True, index=True)
    received_on = fields.Datetime('Received', default=fields.Datetime.now, readonly=True)
    message = fields.Char('Message', required=True)
    stack = fields.Text('Stack')
    source = fields.Selection([('screen', 'Screen'), ('global', 'Global'), ('other', 'Other')],
                              'Source', default='other')
    fatal = fields.Boolean('Fatal')
    route = fields.Char('Screen / Route')
    app_version = fields.Char('App Version', index=True)
    os = fields.Char('OS')
    device = fields.Char('Device')

    def _compute_display_name(self):
        for r in self:
            r.display_name = '%s - %s' % (r.rider_id.name or '?', (r.message or '')[:60])

    @api.model
    def sa_store_reports(self, rider, reports):
        """Save the app's batch (max 20); a report already saved (same rider,
        time and message) is counted but not duplicated. Returns the number saved."""
        saved = 0
        for rep in (reports or [])[:20]:
            if not isinstance(rep, dict):
                continue
            message = (str(rep.get('message') or '') or 'Unknown error')[:500]
            at = _parse_dt(rep.get('at'))
            if self.sudo().search_count([('rider_id', '=', rider.id), ('at', '=', at), ('message', '=', message)]):
                continue
            source = rep.get('source') if rep.get('source') in ('screen', 'global') else 'other'
            self.sudo().create({
                'rider_id': rider.id, 'at': at, 'message': message,
                'stack': (str(rep.get('stack') or ''))[:4000], 'source': source,
                'fatal': bool(rep.get('fatal')), 'route': (str(rep.get('route') or ''))[:200],
                'app_version': (str(rep.get('app_version') or ''))[:40],
                'os': (str(rep.get('os') or ''))[:80], 'device': (str(rep.get('device') or ''))[:120],
            })
            saved += 1
        if saved:
            _logger.info("Rider app: %s crash report(s) from %s", saved, rider.name)
        return saved


class SaSosAlert(models.Model):
    _name = 'sa.sos.alert'
    _description = 'Rider SOS Alert'
    _order = 'at desc, id desc'

    rider_id = fields.Many2one('sa.delivery.partner', 'Rider', required=True, index=True, ondelete='cascade')
    at = fields.Datetime('Pressed At', required=True, index=True)
    received_on = fields.Datetime('Received', default=fields.Datetime.now, readonly=True)
    picking_id = fields.Many2one('stock.picking', 'Job in Hand', index=True, ondelete='set null')
    latitude = fields.Float('Latitude', digits=(10, 7))
    longitude = fields.Float('Longitude', digits=(10, 7))
    accuracy = fields.Float('Accuracy (m)')
    contacts = fields.Text('Emergency Contacts', help="One per line: name - phone")
    state = fields.Selection([('new', 'New'), ('handled', 'Handled')], default='new', required=True, index=True)
    handled_on = fields.Datetime('Handled At', readonly=True)
    handled_by = fields.Many2one('res.users', 'Handled By', readonly=True)
    notified_on = fields.Datetime('Office Notified', readonly=True)
    whatsapp_sent = fields.Boolean('WhatsApp Sent', readonly=True)
    whatsapp_to = fields.Char('WhatsApp To', readonly=True)
    map_url = fields.Char('Map', compute='_compute_map_url')

    @api.depends('latitude', 'longitude')
    def _compute_map_url(self):
        for r in self:
            r.map_url = ('https://maps.google.com/?q=%.6f,%.6f' % (r.latitude, r.longitude)
                         if r.latitude and r.longitude else '')

    def _compute_display_name(self):
        for r in self:
            r.display_name = _('SOS %(rider)s %(when)s', rider=r.rider_id.name or '?',
                               when=fields.Datetime.context_timestamp(r, r.at).strftime('%d %b %H:%M') if r.at else '')

    # ------------------------------------------------------------------
    @api.model
    def sa_raise(self, rider, data):
        """The app's SOS post. Same rider + same `at` = the same alert
        (the app retries until it gets a 200). Returns the alert."""
        at = _parse_dt(data.get('at'))
        existing = self.sudo().search([('rider_id', '=', rider.id), ('at', '=', at)], limit=1)
        if existing:
            return existing
        job = self.env['stock.picking'].sudo()
        try:
            jid = int(data.get('delivery_order_id') or 0)
        except (TypeError, ValueError):
            jid = 0
        if jid:
            job = job.browse(jid).exists()
            if job and job.sa_delivery_partner_id.id != rider.id:
                job = self.env['stock.picking'].sudo()        # not this rider's job: keep the alert, drop the link
        if not job:
            job = self.env['stock.picking'].sudo().search(
                [('sa_delivery_partner_id', '=', rider.id),
                 ('sa_delivery_state', 'in', ('accepted', 'picked', 'dispatched', 'out_for_delivery'))],
                order='id desc', limit=1)

        def num(v):
            try:
                return float(v or 0)
            except (TypeError, ValueError):
                return 0.0
        contacts = data.get('contacts') or []
        lines = []
        for c in contacts if isinstance(contacts, list) else []:
            if isinstance(c, dict):
                lines.append('%s - %s' % (c.get('name') or '?', c.get('phone') or ''))
        lat, lng = num(data.get('latitude')), num(data.get('longitude'))
        if not (lat and lng) and job and job.sa_rider_lat:
            lat, lng = job.sa_rider_lat, job.sa_rider_lng
        if not (lat and lng) and rider.last_lat:
            lat, lng = rider.last_lat, rider.last_lng
        alert = self.sudo().create({
            'rider_id': rider.id, 'at': at, 'picking_id': job.id if job else False,
            'latitude': lat, 'longitude': lng, 'accuracy': num(data.get('accuracy')),
            'contacts': '\n'.join(lines),
        })
        _logger.warning("SOS from rider %s (%s) at %s, job %s", rider.name, rider.phone, at, job.sa_ref_code if job else '-')
        alert._sa_alert_office()
        return alert

    def _sa_office_phone(self):
        self.ensure_one()
        settings = self.env['sa.delivery.settings'].sudo().get_settings()
        phone = (settings.sos_phone or '').strip()
        if not phone and self.picking_id and self.picking_id.sa_shop_id:
            phone = (self.picking_id.sa_shop_id.phone or '').strip()
        if not phone:
            phone = (self.env.company.phone or '').strip()
        return phone

    def _sa_alert_office(self):
        """At once: an Odoo notification to every delivery manager, a WhatsApp
        to the office number, the shop screens refreshed. Never raises."""
        for alert in self.sudo():
            rider = alert.rider_id
            job = alert.picking_id
            when = fields.Datetime.context_timestamp(alert, alert.at).strftime('%H:%M')
            text = _("SOS from %(rider)s (%(phone)s) at %(when)s%(job)s. %(map)s",
                     rider=rider.name, phone=rider.phone or '-', when=when,
                     job=(_(" - job #%s", job.sa_ref_code) if job else ''),
                     map=(alert.map_url or _("No position.")))
            # 1. the managers' browsers
            try:
                # the delivery managers; a database with none in that group
                # (the admin often is not) falls back to the delivery users,
                # then to the administrators - somebody must see it
                users = self.env['res.users']
                for xmlid in ('sales_automation_delivery.group_sa_delivery_manager',
                              'sales_automation_delivery.group_sa_delivery_user', 'base.group_system'):
                    group = self.env.ref(xmlid, raise_if_not_found=False)
                    users = group.user_ids.filtered(lambda u: u.active and not u.share) if group else users
                    if users:
                        break
                bus = self.env['bus.bus'].sudo()
                for user in users:
                    bus._sendone(user.partner_id, 'simple_notification', {
                        'type': 'danger', 'sticky': True, 'title': _("SOS - %s", rider.name), 'message': text})
            except Exception as err:  # noqa: BLE001
                _logger.warning("SOS: notification failed: %s", err)
            # 2. the office WhatsApp
            phone = alert._sa_office_phone()
            sent = False
            if phone:
                try:
                    session = (job._sa_session() if job else
                               self.env['whatsapp.session'].sudo().search([('active', '=', True)], limit=1))
                    body = _("\U0001F198 *SOS* from rider *%(rider)s* (%(phone)s) at %(when)s%(job)s\n%(map)s%(contacts)s",
                             rider=rider.name, phone=rider.phone or '-', when=when,
                             job=(_("\nJob #%s - %s", job.sa_ref_code, job.partner_id.name or '') if job else ''),
                             map=(alert.map_url or _("No position")),
                             contacts=(_("\nContacts: %s", alert.contacts.replace('\n', '; ')) if alert.contacts else ''))
                    sent = bool(session) and session.send_message(phone, body) is not False
                except Exception as err:  # noqa: BLE001
                    _logger.warning("SOS: WhatsApp to %s failed: %s", phone, err)
            alert.write({'notified_on': fields.Datetime.now(), 'whatsapp_sent': sent, 'whatsapp_to': phone})
            # 3. the job's chatter and the shop screens
            try:
                if job:
                    job.message_post(body=text)
                    if hasattr(job, '_sa_store_notify'):
                        job._sa_store_notify()
                elif hasattr(self.env['stock.picking'], '_sa_store_notify'):
                    self.env['stock.picking'].sudo()._sa_store_notify()
            except Exception as err:  # noqa: BLE001
                _logger.warning("SOS: screen refresh failed: %s", err)
        return True

    def action_handled(self):
        self.sudo().filtered(lambda a: a.state == 'new').write({
            'state': 'handled', 'handled_on': fields.Datetime.now(), 'handled_by': self.env.user.id})
        for job in self.mapped('picking_id'):
            if hasattr(job, '_sa_store_notify'):
                job.sudo()._sa_store_notify()
        return True

    @api.model
    def sa_open_for_job(self, job):
        """The open alert the shop card shows: this job's, else the rider's
        with no job."""
        if not job.sa_delivery_partner_id:
            return self.browse()
        return self.sudo().search(['|', ('picking_id', '=', job.id),
                                   '&', ('picking_id', '=', False), ('rider_id', '=', job.sa_delivery_partner_id.id),
                                   ('state', '=', 'new')], order='at desc', limit=1)
