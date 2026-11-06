# -*- coding: utf-8 -*-
"""What happens AFTER the rider taps "Report a problem" (rider-app report,
5 Oct 2026). Until now every reason only told the office. Now each reason has
its next step:

  customer_absent       customer is messaged, a wait timer runs, then return
  customer_refused      return allowed at once (paid order: office refunds)
  payment_refused       return allowed at once
  damaged               photo kept, return allowed, shop told to replace
  address_wrong         customer asked for a location; saved on THIS job only
  customer_elsewhere    the same, for a one-day place
  address_unreachable   customer is sent the rider's spot; spot kept on the job
  vehicle_problem       before pickup: the job goes to the next rider;
                        after pickup: another rider collects the parcel from
                        this rider with a handover code
"""
import hmac
import logging
import secrets
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from markupsafe import Markup

from odoo.tools import html_escape

_logger = logging.getLogger(__name__)

REASONS = ('customer_absent', 'customer_refused', 'address_wrong', 'address_unreachable',
           'payment_refused', 'damaged', 'vehicle_problem', 'customer_elsewhere', 'other')
_ON_THE_ROAD = ('picked', 'dispatched', 'out_for_delivery')
_RELAY_ACTIVE = ('searching', 'offered', 'accepted', 'none')


class SaDeliverySettingsProblems(models.Model):
    _inherit = 'sa.delivery.settings'

    absent_wait_minutes = fields.Integer(
        'Wait for the customer (minutes)', default=10,
        help="After the rider reports 'customer not there' (or asks for a "
             "location), the customer is messaged and the rider waits this "
             "long before Return to shop is allowed.")
    relay_enabled = fields.Boolean(
        'Vehicle problem: hand the parcel to another rider', default=True,
        help="On: when a rider with a parcel reports a vehicle problem, the "
             "nearest free rider is offered the job, rides to the first "
             "rider and takes the parcel over with a handover code. Off: the "
             "office is only told.")


class SaRiderProblem(models.Model):
    """One report from a rider on one delivery. A second report on the same
    job adds a row - it never replaces the first."""
    _name = 'sa.rider.problem'
    _description = "Rider's problem report"
    _order = 'id desc'

    picking_id = fields.Many2one('stock.picking', 'Delivery', required=True, ondelete='cascade', index=True)
    rider_id = fields.Many2one('sa.delivery.partner', 'Rider', ondelete='set null')
    reported_on = fields.Datetime('Reported On', default=fields.Datetime.now, required=True)
    reason = fields.Char('Reason Code')
    reason_label = fields.Char('Reason')
    note = fields.Char("Rider's Note")
    office_line = fields.Char('Line Shown at the Counter')
    photo_ids = fields.Many2many('ir.attachment', 'sa_rider_problem_photo_rel', 'problem_id', 'attachment_id',
                                 string='Photos')
    photo_count = fields.Integer('Photos', compute='_compute_photo_count')
    handled_on = fields.Datetime('Handled On', readonly=True)
    handled_by = fields.Many2one('res.users', 'Handled By', readonly=True)

    @api.depends('photo_ids')
    def _compute_photo_count(self):
        for row in self:
            row.photo_count = len(row.photo_ids)


class StockPickingRiderProblems(models.Model):
    _inherit = 'stock.picking'

    sa_report_ids = fields.One2many('sa.rider.problem', 'picking_id', "Rider's Reports", copy=False)
    sa_issue_note = fields.Char("Rider's Note", copy=False, readonly=True,
                                help="What the rider wrote with the last report, in their own words.")

    def sa_rider_report(self, rider, kind, text):
        """Every report is also kept as its own row, with the rider's note
        (context `sa_note`) and photos (context `sa_photo_ids`)."""
        res = super().sa_rider_report(rider, kind, text)
        note = (self.env.context.get('sa_note') or '').strip()[:500]
        photos = self.env.context.get('sa_photo_ids') or []
        for job in self.sudo():
            job.write({'sa_issue_note': note or False})
            self.env['sa.rider.problem'].sudo().create({
                'picking_id': job.id, 'rider_id': rider.id if rider else False,
                'reason': (kind or 'issue')[:40], 'reason_label': job._sa_reason_text(kind or 'issue'),
                'note': note or False, 'office_line': (text or '')[:250],
                'photo_ids': [(6, 0, photos)],
            })
            if note:
                job.message_post(body=_("Rider's note: %s", note))
        return res

    def sa_action_issue_seen(self):
        rows = self.sudo().mapped('sa_report_ids').filtered(lambda r: not r.handled_on)
        rows.write({'handled_on': fields.Datetime.now(), 'handled_by': self.env.user.id})
        self.sudo().write({'sa_issue_note': False})
        return super().sa_action_issue_seen()

    def sa_reports_block(self, prefix):
        """Every report on this job, oldest first, for the apps."""
        self.ensure_one()
        return [{
            'id': r.id, 'at': self._sa_iso(r.reported_on), 'rider': r.rider_id.name or '',
            'reason': r.reason or '', 'reason_label': r.reason_label or '', 'note': r.note or '',
            'handled_at': self._sa_iso(r.handled_on),
            'photos': [{'id': a.id, 'name': a.name or '', 'url': '%s/%d' % (prefix, a.id)} for a in r.photo_ids.sorted('id')],
        } for r in self.sudo().sa_report_ids.sorted('id')]

    sa_problem_kind = fields.Char('Last Problem Reported', copy=False, readonly=True)
    sa_problem_on = fields.Datetime('Problem Reported On', copy=False, readonly=True)
    sa_wait_until = fields.Datetime('Rider Waits Until', copy=False, readonly=True)
    sa_wait_for = fields.Selection([('customer', 'The customer to come'),
                                    ('location', "The customer's location")],
                                   'Waiting For', copy=False, readonly=True)
    sa_return_reason = fields.Char('Return Reason', copy=False, readonly=True)
    # A drop point for THIS job only - the customer's saved address is not touched
    sa_drop_pending = fields.Boolean('Location Asked from the Customer', copy=False, readonly=True)
    sa_drop_lat = fields.Float('Drop Point Latitude', digits=(10, 7), copy=False, readonly=True)
    sa_drop_lng = fields.Float('Drop Point Longitude', digits=(10, 7), copy=False, readonly=True)
    sa_drop_label = fields.Char('Drop Point', copy=False, readonly=True)
    sa_drop_on = fields.Datetime('Drop Point Set On', copy=False, readonly=True)
    sa_problem_photo_ids = fields.Many2many(
        'ir.attachment', 'sa_picking_problem_photo_rel', 'picking_id', 'attachment_id',
        string='Problem Photos', copy=False)
    # Vehicle problem with the parcel on board: rider to rider
    sa_relay_state = fields.Selection([
        ('searching', 'Looking for another rider'), ('offered', 'Offered to another rider'),
        ('accepted', 'Another rider is coming'), ('none', 'No rider free'),
    ], 'Handover', copy=False, readonly=True)
    sa_relay_to_id = fields.Many2one('sa.delivery.partner', 'Handover To', copy=False, readonly=True)
    sa_relay_from_id = fields.Many2one('sa.delivery.partner', 'Taken Over From', copy=False, readonly=True)
    sa_relay_tried_ids = fields.Many2many(
        'sa.delivery.partner', 'sa_picking_relay_tried_rel', 'picking_id', 'rider_id', copy=False)
    sa_relay_expires_on = fields.Datetime(copy=False, readonly=True)
    sa_relay_code = fields.Char('Handover Code', copy=False, readonly=True, groups='base.group_system')
    sa_relay_attempts = fields.Integer(copy=False, readonly=True)
    sa_relay_on = fields.Datetime('Handover Started On', copy=False, readonly=True)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @api.model
    def _sa_reason_text(self, code):
        return {
            'customer_absent': _("Customer not there"),
            'customer_refused': _("Customer refused the parcel"),
            'address_wrong': _("Address is wrong"),
            'address_unreachable': _("Cannot reach the address"),
            'payment_refused': _("Customer would not pay"),
            'damaged': _("Parcel is damaged"),
            'vehicle_problem': _("Problem with the rider's vehicle"),
            'customer_elsewhere': _("Customer is at another place"),
            'other': _("Something else"),
            'item_missing': _("Item missing"),
            'issue': _("Problem"),
        }.get(code, code or '')

    def _sa_iso(self, dt):
        return (dt.replace(microsecond=0).isoformat() + 'Z') if dt else ''

    def _sa_wait_minutes(self):
        return max(0, self.env['sa.delivery.settings'].sudo().get_settings().absent_wait_minutes or 0)

    def _sa_waiting(self):
        self.ensure_one()
        return bool(self.sa_wait_until and fields.Datetime.now() < self.sa_wait_until)

    def _sa_relay_active(self):
        self.ensure_one()
        return self.sa_relay_state in _RELAY_ACTIVE

    def _sa_notify_counter(self):
        if hasattr(self, '_sa_store_notify'):
            try:
                self._sa_store_notify()
            except Exception:  # noqa: BLE001
                pass

    def _sa_push_rider(self, rider, data, title, body):
        try:
            return self.env['sa.delivery.settings'].sudo().get_settings()._sa_push(rider, data, title, body)
        except Exception as err:  # noqa: BLE001
            _logger.warning("Rider problems: push to %s failed: %s", rider.name, err)
            return 0

    # ------------------------------------------------------------------
    # The drop point of this job
    # ------------------------------------------------------------------
    def _sa_customer_position(self):
        self.ensure_one()
        if self.sa_drop_lat and self.sa_drop_lng:
            return self.sa_drop_lat, self.sa_drop_lng
        return super()._sa_customer_position()

    def sa_location_source(self):
        self.ensure_one()
        if self.sa_drop_lat and self.sa_drop_lng:
            return 'customer_pin'
        return super().sa_location_source()

    def sa_drop_block(self):
        self.ensure_one()
        if not (self.sa_drop_lat and self.sa_drop_lng):
            return None
        return {'latitude': self.sa_drop_lat, 'longitude': self.sa_drop_lng,
                'label': self.sa_drop_label or '', 'at': self._sa_iso(self.sa_drop_on)}

    def _sa_set_drop_point(self, lat, lng, label):
        self.ensure_one()
        self.sudo().write({'sa_drop_lat': lat, 'sa_drop_lng': lng, 'sa_drop_label': label,
                           'sa_drop_on': fields.Datetime.now(), 'sa_drop_pending': False,
                           'sa_near_since': False})
        try:
            slat, slng = self.sa_shop_position()
            if slat and slng:
                self.sudo().write({'sa_trip_m': int(self.env['sa.delivery.ping'].sudo()._sa_metres(slat, slng, lat, lng))})
        except Exception:  # noqa: BLE001
            pass

    def sa_set_customer_pin(self, lat, lng, source='whatsapp'):
        """A location the customer sends while the rider has asked for one
        is this job's drop point only - never the customer's saved address."""
        one_off = self.filtered('sa_drop_pending')
        for job in one_off:
            job._sa_set_drop_point(lat, lng, _("Location the customer sent for this order"))
            job.sudo().write({'sa_wait_until': False, 'sa_wait_for': False})
            job.message_post(body=_("The customer sent a location for this order only (%(lat).5f, %(lng).5f). "
                                    "Their saved address is unchanged.", lat=lat, lng=lng))
            rider = job.sa_delivery_partner_id
            if rider:
                job._sa_push_rider(rider, {'type': 'drop_point_changed', 'delivery_order_id': job.id,
                                           'job_code': job.sa_ref_code or '',
                                           'latitude': lat, 'longitude': lng},
                                   _("New drop point - #%s", job.sa_ref_code or ''),
                                   _("The customer shared a location. The map has moved to it."))
            job._sa_notify_counter()
        rest = self - one_off
        if rest:
            return super(StockPickingRiderProblems, rest).sa_set_customer_pin(lat, lng, source=source)
        return True

    # ------------------------------------------------------------------
    # What the rider may do while a problem is open
    # ------------------------------------------------------------------
    def sa_allowed_actions(self):
        self.ensure_one()
        actions = super().sa_allowed_actions()
        if self._sa_relay_active():
            return ['report_issue', 'cancel_handover']
        if self._sa_waiting():
            actions = [a for a in actions if a != 'return_to_shop']
        return actions

    def sa_action_blocked(self, action):
        """None, or {'code', 'message', ...} when `action` must wait."""
        self.ensure_one()
        if self._sa_relay_active() and action not in ('accept',):
            return {'code': 'handover_waiting',
                    'message': _("This parcel is being handed to another rider. Cancel the handover first.")}
        if action == 'return_to_shop' and self._sa_waiting():
            return {'code': 'wait', 'wait_until': self._sa_iso(self.sa_wait_until),
                    'message': _("The customer has been messaged. Please wait until the time shown before returning.")}
        return None

    def sa_set_state(self, state):
        if state in ('delivered', 'returning', 'returned', 'cancelled', 'failed'):
            vals = {'sa_wait_until': False, 'sa_wait_for': False, 'sa_drop_pending': False}
            for job in self:
                if job.sa_relay_state:
                    vals.update({'sa_relay_state': False, 'sa_relay_to_id': False,
                                 'sa_relay_expires_on': False, 'sa_relay_code': False})
                if state == 'returning' and not job.sa_cancel_reason and job.sa_return_reason:
                    job.sudo().write({'sa_cancel_reason': job._sa_reason_text(job.sa_return_reason)})
            self.sudo().write(vals)
        return super().sa_set_state(state)

    def _sa_check_auto_near(self, lat, lng, accuracy=0.0):
        self.ensure_one()
        if self._sa_relay_active():
            return False                 # this rider is not moving the parcel
        return super()._sa_check_auto_near(lat, lng, accuracy)

    # ------------------------------------------------------------------
    # Report a problem
    # ------------------------------------------------------------------
    def sa_problem_block(self):
        self.ensure_one()
        if not self.sa_problem_on:
            return None
        return {'reason': self.sa_problem_kind or '', 'at': self._sa_iso(self.sa_problem_on),
                'reason_label': self._sa_reason_text(self.sa_problem_kind),
                'note': self.sudo().sa_report_ids.sorted('id')[-1:].note or '',
                'wait_until': self._sa_iso(self.sa_wait_until) if self._sa_waiting() else '',
                'waiting_for': {'customer': 'customer', 'location': 'customer_location'}.get(self.sa_wait_for, '')
                if self._sa_waiting() else '',
                'return_reason': self.sa_return_reason or ''}

    def _sa_start_wait(self, what):
        """Start the timer once; a second report does not restart it."""
        self.ensure_one()
        if self._sa_waiting():
            return self.sa_wait_until
        until = fields.Datetime.now() + timedelta(minutes=self._sa_wait_minutes())
        self.sudo().write({'sa_wait_until': until, 'sa_wait_for': what})
        return until

    def _sa_add_problem_photo(self, filename, payload):
        self.ensure_one()
        import base64
        import re
        name = re.sub(r'[^A-Za-z0-9._ -]+', '_', (filename or '').replace('\\', '/').split('/')[-1]).strip(' .')[:120]
        if not name:
            name = 'problem-%s-%s.jpg' % (self.sa_ref_code or self.id, fields.Datetime.now().strftime('%Y%m%d-%H%M%S'))
        same = self.sudo().sa_problem_photo_ids.filtered(lambda a: a.name == name)[:1]
        if same:
            return same
        att = self.env['ir.attachment'].sudo().create({
            'name': name, 'res_model': 'stock.picking', 'res_id': self.id,
            'datas': base64.b64encode(payload), 'description': 'Parcel photo - problem'})
        self.sudo().write({'sa_problem_photo_ids': [(4, att.id)]})
        return att

    def sa_photo_for(self, attachment_id):
        att = super().sa_photo_for(attachment_id)
        if not att:
            att = self.sudo().sa_problem_photo_ids.filtered(lambda a: a.id == int(attachment_id or 0))[:1]
        return att

    def sa_photos_block(self, prefix):
        out = super().sa_photos_block(prefix)
        tz = out.get('timezone') or self.env['sa.delivery.partner']._sa_company_tz(self.company_id or self.env.company)
        out['problem'] = [{'id': a.id, 'name': a.name or '', 'url': '%s/%d' % (prefix, a.id),
                           'size': a.file_size or 0, 'at': self._sa_iso(a.create_date),
                           'at_local': (fields.Datetime.context_timestamp(self.with_context(tz=tz), a.create_date)
                                        .strftime('%Y-%m-%d %H:%M:%S')) if a.create_date else ''}
                          for a in self.sudo().sa_problem_photo_ids.sorted('id')]
        return out

    @api.depends('sa_problem_photo_ids')
    def _compute_sa_photos(self):
        super()._compute_sa_photos()
        for job in self:
            photos = job.sa_problem_photo_ids
            if not photos:
                continue
            tz = self.env['sa.delivery.partner']._sa_company_tz(job.company_id or self.env.company)
            thumbs = ''.join(
                '<a href="/web/image/%d" class="o_sa_photo" data-group="problem" title="%s" style="display:inline-block;margin:0 8px 8px 0;text-align:center;font-size:11px;color:#64748b">'
                '<img src="/web/image/%d/160x160" style="width:120px;height:120px;object-fit:cover;border:1px solid #fca5a5;border-radius:6px"/><br/>%s<br/><span style="color:#0f172a">%s</span></a>'
                % (a.id, html_escape(a.name or ''), a.id, html_escape(a.name or ''),
                   fields.Datetime.context_timestamp(job.with_context(tz=tz), a.create_date).strftime('%d %b %H:%M:%S') if a.create_date else '')
                for a in photos.sorted('id'))
            # The field's value is Markup: a plain str added to it is escaped
            # and printed as code (rider-app report, 6 Oct 2026). The part is
            # safe HTML with the name and time already escaped above.
            part = Markup('<div style="margin-bottom:6px"><b>%s (%d)</b></div><div>%s</div>'
                          % (html_escape(_("Problem photos")), len(photos), thumbs))
            job.sa_photos_html = Markup(job.sa_photos_html or '') + part

    def sa_report_problem(self, rider, code, text='', photo=None, photo_name=''):
        """The rider reported `code`. Tells the office (as before), then does
        the next step for that reason. Returns {'message', 'next': {...}}."""
        self.ensure_one()
        job = self.sudo()
        code = (code or '').strip().lower()
        label = job._sa_reason_text(code)
        extra = (text or '').strip()
        if extra.lower() == code:
            extra = ''
        line = label
        state = job.sa_delivery_state
        on_road = state in _ON_THE_ROAD
        ref = job.sa_ref_code or job.name
        name = rider.name if rider else _("Our rider")

        att = job._sa_add_problem_photo(photo_name, photo) if photo else self.env['ir.attachment']
        # the rider's own words and the photo travel with the report
        job = job.with_context(sa_note=extra[:500], sa_photo_ids=att.ids)
        # office notes that go on the red line at the counter
        if code == 'customer_refused' and not job.sa_amount_due() and job.sale_id:
            line += _(" - PAID order: the office starts the refund")
        if code == 'damaged':
            line += _(" - send a replacement") + (_(" (photo on the job)") if job.sa_problem_photo_ids else '')
        job.sa_rider_report(rider, code, line[:250])
        job.write({'sa_problem_kind': code, 'sa_problem_on': fields.Datetime.now()})

        nxt = {'kind': 'none'}
        msg = _("The office has been told.")

        if code == 'vehicle_problem':
            return job._sa_problem_vehicle(rider)

        if not on_road:
            return {'message': msg, 'next': nxt}

        if code == 'customer_absent':
            job._sa_tell_customer(_(
                "\U0001F6AA Your rider *%(rider)s* is at your door with order *#%(ref)s*. "
                "Please come out to receive it.", rider=name, ref=ref))
            until = job._sa_start_wait('customer')
            nxt = {'kind': 'wait', 'wait_until': job._sa_iso(until), 'waiting_for': 'customer'}
            msg = _("The customer has been messaged. Wait up to %s minutes.", job._sa_wait_minutes())

        elif code in ('customer_refused', 'payment_refused', 'damaged'):
            job.write({'sa_return_reason': code, 'sa_wait_until': False, 'sa_wait_for': False})
            nxt = {'kind': 'return_allowed'}
            msg = {'customer_refused': _("Noted as refused. Bring the parcel back to the shop."),
                   'payment_refused': _("Noted. If the customer still will not pay, bring the parcel back to the shop."),
                   'damaged': _("Noted. Bring the parcel back; the shop will send a replacement.")}[code]

        elif code in ('address_wrong', 'customer_elsewhere'):
            if code == 'address_wrong':
                body = _("\U0001F4CD Our rider cannot find the address for order *#%(ref)s*. "
                         "Please share your location here (\U0001F4CE then *Location*) so the rider can reach you.", ref=ref)
            else:
                body = _("\U0001F4CD Our rider is told you are at another place today. Please share your location "
                         "here (\U0001F4CE then *Location*) and we will bring order *#%(ref)s* there. "
                         "Your saved address stays the same.", ref=ref)
            job._sa_tell_customer(body)
            job.write({'sa_drop_pending': True, 'sa_return_reason': code})
            until = job._sa_start_wait('location')
            nxt = {'kind': 'wait', 'wait_until': job._sa_iso(until), 'waiting_for': 'customer_location'}
            msg = _("The customer has been asked to share a location. The map moves when they do.")

        elif code == 'address_unreachable':
            lat = job.sa_rider_lat or (rider.last_lat if rider else 0.0)
            lng = job.sa_rider_lng or (rider.last_lng if rider else 0.0)
            where = (rider.address_short if rider else '') or ''
            if lat and lng:
                job._sa_set_drop_point(lat, lng, _("Where the rider is waiting") + ((' - ' + where) if where else ''))
                link = 'https://maps.google.com/?q=%.6f,%.6f' % (lat, lng)
                job._sa_tell_customer(_(
                    "\U0001F6F5 Your rider *%(rider)s* cannot reach your door and is waiting here:\n%(link)s%(where)s\n\n"
                    "Please come out to collect order *#%(ref)s*.", rider=name, link=link,
                    where=('\n' + where) if where else '', ref=ref))
            else:
                job._sa_tell_customer(_(
                    "\U0001F6F5 Your rider *%(rider)s* cannot reach your door and is waiting nearby. "
                    "Please come out to collect order *#%(ref)s*.", rider=name, ref=ref))
            job.write({'sa_return_reason': code})
            until = job._sa_start_wait('customer')
            nxt = {'kind': 'new_drop_point' if (lat and lng) else 'wait', 'wait_until': job._sa_iso(until),
                   'waiting_for': 'customer', 'drop_point': job.sa_drop_block()}
            msg = _("The customer has been sent your position. Wait up to %s minutes.", job._sa_wait_minutes())

        job._sa_notify_counter()
        return {'message': msg, 'next': nxt}

    # ------------------------------------------------------------------
    # Vehicle problem
    # ------------------------------------------------------------------
    def _sa_problem_vehicle(self, rider):
        job = self.sudo()
        state = job.sa_delivery_state
        if state in ('offered', 'accepted'):
            # nothing collected yet: exactly a decline - the next rider is called
            job.sa_action_decline(rider, _("Problem with the rider's vehicle"))
            return {'message': _("The job has been passed on to another rider."),
                    'next': {'kind': 'reassigning'}, 'released': True}
        settings = self.env['sa.delivery.settings'].sudo().get_settings()
        if state not in _ON_THE_ROAD or not settings.relay_enabled:
            return {'message': _("The office has been told and will call you."), 'next': {'kind': 'none'}}
        if job._sa_relay_active() and job.sa_relay_state != 'none':
            return {'message': _("Another rider is already being found."),
                    'next': dict(job._sa_relay_next(), kind='reassigning')}
        code = ''.join(str(secrets.randbelow(10)) for _n in range(6))
        job.write({'sa_relay_state': 'searching', 'sa_relay_code': code, 'sa_relay_attempts': 0,
                   'sa_relay_on': fields.Datetime.now(), 'sa_relay_to_id': False,
                   'sa_relay_tried_ids': [(5, 0, 0)], 'sa_wait_until': False, 'sa_wait_for': False})
        job._sa_tell_customer(_(
            "⏱ Your delivery *#%(ref)s* is a little late. A new rider is bringing it.",
            ref=job.sa_ref_code or job.name))
        job._sa_relay_call_next()
        return {'message': _("Stay with the parcel. Another rider is being sent to you - show them the handover code."),
                'next': dict(job._sa_relay_next(), kind='reassigning')}

    def _sa_relay_next(self):
        self.ensure_one()
        to = self.sa_relay_to_id
        return {'relay_state': self.sa_relay_state or '', 'handover_code': self.sudo().sa_relay_code or '',
                'to_rider': {'id': to.id, 'name': to.name or '', 'phone': to.phone or ''} if to else None}

    def _sa_relay_origin(self):
        """Where the parcel is: with the rider who holds it."""
        self.ensure_one()
        holder = self.sa_delivery_partner_id
        if self.sa_rider_lat and self.sa_rider_lng:
            return self.sa_rider_lat, self.sa_rider_lng, self.sa_rider_fix_on
        if holder and holder.last_lat and holder.last_lng:
            return holder.last_lat, holder.last_lng, holder.last_fix_on
        return None, None, None

    def _sa_relay_call_next(self):
        """Offer the takeover to ONE rider: the nearest free rider to the
        parcel, never somebody already tried."""
        self.ensure_one()
        job = self.sudo()
        holder = job.sa_delivery_partner_id
        lat, lng, _on = job._sa_relay_origin()
        ctx = {'sa_origin': (lat, lng)} if lat and lng else {}
        cands = job.with_context(**ctx).sa_candidates(exclude=holder | job.sa_relay_tried_ids, include_busy=False)
        ranked = job.sa_rank_candidates(cands)
        if not ranked:
            job.write({'sa_relay_state': 'none', 'sa_relay_to_id': False, 'sa_relay_expires_on': False})
            job.with_context(sa_note='', sa_photo_ids=[]).sa_rider_report(holder, 'vehicle_problem',
                                _("Vehicle problem: NO rider is free to take the parcel over from %s - call the rider.",
                                  holder.name or '-')[:250])
            job._sa_push_rider(holder, {'type': 'relay_none', 'delivery_order_id': job.id, 'job_code': job.sa_ref_code or ''},
                               _("No rider free - #%s", job.sa_ref_code or ''), _("The office has been told and will call you."))
            return self.env['sa.delivery.partner']
        nxt = ranked[0]['rider']
        settings = self.env['sa.delivery.settings'].sudo().get_settings()
        expires = fields.Datetime.now() + timedelta(seconds=max(15, settings.offer_timeout_seconds or 90))
        job.write({'sa_relay_state': 'offered', 'sa_relay_to_id': nxt.id, 'sa_relay_expires_on': expires,
                   'sa_relay_tried_ids': [(4, nxt.id)]})
        job.message_post(body=_("Vehicle problem: takeover offered to %(to)s (parcel is with %(holder)s).",
                                to=nxt.name, holder=holder.name or '-'))
        job._sa_push_rider(nxt, {'type': 'job_offer', 'relay': 'true', 'delivery_order_id': job.id,
                                 'job_code': job.sa_ref_code or '', 'pickup_from': holder.name or '',
                                 'expires_at': job._sa_iso(expires)},
                           _("Take over delivery #%s", job.sa_ref_code or ''),
                           _("Collect the parcel from %s (vehicle problem) and deliver it.", holder.name or _("a rider")))
        try:
            session = job._sa_session()
            if session and nxt.phone and self.env['sa.outbox.guard'].sudo().claim('relay|%s|%s' % (job.id, nxt.id), 900):
                session.send_message(nxt.phone, _(
                    "\U0001F6F5 *Take over delivery #%(ref)s*\n%(holder)s has a vehicle problem and is waiting with the "
                    "parcel. Open the rider app to accept and see where to collect it.",
                    ref=job.sa_ref_code or '-', holder=holder.name or _("A rider")))
        except Exception as err:  # noqa: BLE001
            _logger.warning("Relay: WhatsApp nudge for %s failed: %s", job.sa_ref_code, err)
        job._sa_notify_counter()
        return nxt

    def sa_relay_accept(self, rider):
        self.ensure_one()
        job = self.sudo()
        if job.sa_relay_state != 'offered' or job.sa_relay_to_id != rider:
            raise UserError(_("This takeover is no longer offered to you."))
        if job.sa_relay_expires_on and fields.Datetime.now() > job.sa_relay_expires_on:
            job.sa_relay_decline(rider, _("no answer in time"))
            raise UserError(_("This offer has expired - it went to another rider."))
        job.write({'sa_relay_state': 'accepted', 'sa_relay_expires_on': False})
        holder = job.sa_delivery_partner_id
        job.message_post(body=_("%(to)s accepted the takeover and is riding to %(holder)s.",
                                to=rider.name, holder=holder.name or '-'))
        job._sa_push_rider(holder, {'type': 'relay_accepted', 'delivery_order_id': job.id,
                                    'job_code': job.sa_ref_code or '', 'rider': rider.name or ''},
                           _("%s is coming", rider.name or _("A rider")),
                           _("Show them the handover code when they arrive."))
        job._sa_notify_counter()
        return True

    def sa_relay_decline(self, rider, reason=''):
        self.ensure_one()
        job = self.sudo()
        if job.sa_relay_state not in ('offered', 'accepted') or job.sa_relay_to_id != rider:
            raise UserError(_("This takeover is not with you."))
        job.message_post(body=_("%(to)s did not take the parcel over - %(why)s.",
                                to=rider.name, why=reason or _("declined")))
        job.write({'sa_relay_state': 'searching', 'sa_relay_to_id': False, 'sa_relay_expires_on': False})
        job._sa_relay_call_next()
        return True

    def sa_relay_cancel(self, rider=None):
        """The rider with the parcel can go on after all."""
        self.ensure_one()
        job = self.sudo()
        if not job._sa_relay_active():
            return False
        to = job.sa_relay_to_id
        job.write({'sa_relay_state': False, 'sa_relay_to_id': False, 'sa_relay_expires_on': False,
                   'sa_relay_code': False})
        job.message_post(body=_("Handover cancelled - %s continues the delivery.",
                                job.sa_delivery_partner_id.name or '-'))
        if to:
            job._sa_push_rider(to, {'type': 'relay_cancelled', 'delivery_order_id': job.id,
                                    'job_code': job.sa_ref_code or ''},
                               _("Takeover cancelled - #%s", job.sa_ref_code or ''),
                               _("The first rider is continuing the delivery."))
        job._sa_notify_counter()
        return True

    def sa_relay_new_code(self):
        self.ensure_one()
        job = self.sudo()
        if not job._sa_relay_active():
            raise UserError(_("No handover is open for this delivery."))
        code = ''.join(str(secrets.randbelow(10)) for _n in range(6))
        job.write({'sa_relay_code': code, 'sa_relay_attempts': 0})
        return code

    def sa_relay_verify(self, rider, code):
        """The second rider types the code the first rider shows: the parcel
        (and the job) is theirs. (ok, message)."""
        self.ensure_one()
        job = self.sudo()
        if job.sa_relay_state != 'accepted' or job.sa_relay_to_id != rider:
            return False, _("This takeover is not with you.")
        if job.sa_relay_attempts >= 5:
            return False, _("Too many wrong attempts. Ask the other rider for a new code.")
        code = ''.join(c for c in (code or '') if c.isdigit())
        if len(code) != 6 or not hmac.compare_digest(code, job.sa_relay_code or ''):
            job.write({'sa_relay_attempts': job.sa_relay_attempts + 1})
            return False, _("Invalid code.")
        first = job.sa_delivery_partner_id
        job.write({
            'sa_delivery_partner_id': rider.id, 'sa_relay_from_id': first.id,
            'sa_relay_state': False, 'sa_relay_to_id': False, 'sa_relay_code': False,
            'sa_relay_expires_on': False, 'sa_delivery_state': 'dispatched',
            'sa_near_since': False, 'sa_near_auto': False, 'sa_arrived_customer_on': False,
            'sa_wait_until': False, 'sa_wait_for': False, 'sa_out_on': False,
            'sa_issue_kind': False, 'sa_issue_text': False, 'sa_issue_on': False,
        })
        try:
            job._sa_apply_rider_fee(rider)          # the trip pay goes to the rider who delivers
        except Exception as err:  # noqa: BLE001
            _logger.warning("Relay: fee for %s failed: %s", job.sa_ref_code, err)
        job.message_post(body=_("Parcel handed over from %(a)s to %(b)s (vehicle problem) - handover code verified. "
                                "Per-trip pay, if any, is set for %(b)s; a share for %(a)s is the office's decision.",
                                a=first.name or '-', b=rider.name or '-'))
        job._sa_push_rider(first, {'type': 'relay_done', 'delivery_order_id': job.id,
                                   'job_code': job.sa_ref_code or '', 'rider': rider.name or ''},
                           _("Parcel handed over - #%s", job.sa_ref_code or ''),
                           _("%s has the parcel now. This delivery is off your list.", rider.name or _("The other rider")))
        job._sa_notify_counter()
        return True, _("Code verified. The parcel is yours - deliver to the address shown.")

    def _sa_expire_offers(self):
        n = super()._sa_expire_offers()
        jobs = self.sudo().search([('sa_relay_state', '=', 'offered'), ('sa_relay_expires_on', '!=', False),
                                   ('sa_relay_expires_on', '<', fields.Datetime.now())])
        for job in jobs:
            try:
                with self.env.cr.savepoint():
                    job.sa_relay_decline(job.sa_relay_to_id, _("no answer in time"))
            except Exception as err:  # noqa: BLE001
                _logger.warning("Relay: expiring the offer of %s failed: %s", job.sa_ref_code, err)
        return n

    # ------------------------------------------------------------------
    # What each rider sees
    # ------------------------------------------------------------------
    def sa_problem_overlay(self, viewer):
        """Fields laid over the rider API's job block. `viewer` = the rider
        asking (the second rider of a handover sees a different job)."""
        self.ensure_one()
        job = self.sudo()
        out = {'problem': job.sa_problem_block(), 'drop_point': job.sa_drop_block(),
               'taken_over_from': job.sa_relay_from_id.name or '' if job.sa_relay_from_id else ''}
        shop = None
        drop = job.sa_drop_block()
        if drop:
            out.update({'latitude': drop['latitude'], 'longitude': drop['longitude'],
                        'customer_latitude': drop['latitude'], 'customer_longitude': drop['longitude'],
                        'customer_pin_source': 'drop_point', 'location_source': 'customer_pin'})
        out['pickup_from'] = {'kind': 'shop'}
        if not job._sa_relay_active():
            return out
        holder = job.sa_delivery_partner_id
        if viewer and viewer == job.sa_relay_to_id:
            lat, lng, fix_on = job._sa_relay_origin()
            out.update({
                'is_relay': True,
                'delivery_status': 'offered' if job.sa_relay_state == 'offered' else 'accepted',
                'offer_expires_at': job._sa_iso(job.sa_relay_expires_on) if job.sa_relay_state == 'offered' else '',
                'allowed_actions': ['accept', 'decline'] if job.sa_relay_state == 'offered'
                else ['verify_handover', 'decline', 'report_issue'],
                'pickup_from': {'kind': 'rider', 'id': holder.id, 'name': holder.name or '',
                                'phone': holder.phone or '', 'latitude': lat or None, 'longitude': lng or None,
                                'fix_at': job._sa_iso(fix_on), 'address': holder.address_short or ''},
                'customer_location_locked': True,       # until the parcel is theirs
                'pickup_code_ready': False,
            })
        else:
            out.update({
                'is_relay': True,
                'delivery_status': 'handover_waiting',
                'handover_code': job.sa_relay_code or '',
                'relay': job._sa_relay_next(),
                'allowed_actions': job.sa_allowed_actions(),
            })
        return out

    def _compute_sa_stage_text(self):
        super()._compute_sa_stage_text()
        for p in self:
            if p.sa_relay_state:
                a = p.sa_delivery_partner_id.name or '-'
                b = p.sa_relay_to_id.name or ''
                p.sa_stage_text = {
                    'searching': _("Vehicle problem - looking for a rider to take the parcel over from %s", a),
                    'offered': _("Vehicle problem - takeover offered to %(b)s (parcel is with %(a)s)", a=a, b=b),
                    'accepted': _("Vehicle problem - %(b)s is riding to %(a)s to take the parcel over", a=a, b=b),
                    'none': _("Vehicle problem - NO rider is free to take over from %s: call the rider", a),
                }.get(p.sa_relay_state, p.sa_stage_text)
            elif p.sa_wait_until and fields.Datetime.now() < p.sa_wait_until:
                p.sa_stage_text = _("%(why)s - the customer was messaged; the rider waits until %(t)s",
                                    why=p._sa_reason_text(p.sa_problem_kind),
                                    t=fields.Datetime.context_timestamp(p, p.sa_wait_until).strftime('%H:%M'))

    # ------------------------------------------------------------------
    # The office's buttons while a handover is open
    # ------------------------------------------------------------------
    def action_sa_relay_retry(self):
        """Look for a takeover rider again, from everybody (job form)."""
        for job in self.sudo():
            if not job._sa_relay_active():
                raise UserError(_("No handover is open for this delivery."))
            job.write({'sa_relay_state': 'searching', 'sa_relay_to_id': False,
                       'sa_relay_expires_on': False, 'sa_relay_tried_ids': [(5, 0, 0)]})
            job._sa_relay_call_next()
        return True

    def action_sa_relay_cancel(self):
        for job in self:
            job.sa_relay_cancel()
        return True
