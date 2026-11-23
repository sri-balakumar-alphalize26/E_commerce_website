# -*- coding: utf-8 -*-
"""The rider's app: one signed link, three buttons, no login."""

import hmac
import json
from datetime import timedelta
import logging
from urllib.parse import quote_plus

import pytz

from odoo import http, fields
from odoo.http import request

from odoo.addons.sales_automation.controllers.link_expired import expired_page, visit_expired

_logger = logging.getLogger(__name__)

_NEXT = {
    'offered': 'accepted',
    'accepted': 'picked',
    'picked': 'delivered',
}


class SaDeliveryJob(http.Controller):
    """Public, token-gated. Modelled on the tracker's payment pages.

    A rider is not an Odoo user and never will be - asking a courier to hold
    an account is how a delivery flow stops being used. The token is the whole
    of the security here, so it is long, compared in constant time, and never
    printed back into the page.
    """

    def _job(self, picking_id, token):
        picking = request.env['stock.picking'].sudo().browse(int(picking_id))
        if not picking.exists() or not picking.sa_access_token or not token:
            return None
        if not hmac.compare_digest(str(picking.sa_access_token), str(token)):
            return None
        return picking

    @http.route('/wa/delivery/<int:picking_id>', type='http', auth='public',
                website=False, csrf=False)
    def job(self, picking_id, token=None, **kw):
        picking = self._job(picking_id, token)
        if not picking:
            # 404, not "wrong token" - a wrong guess should learn nothing.
            return request.not_found()
        values = self._values(picking, token)
        values['error'] = (kw.get('error') or '')[:160]
        return request.render(
            'sales_automation_delivery.delivery_job_page', values)

    @http.route('/wa/delivery/<int:picking_id>/<string:action>', type='http',
                auth='public', methods=['GET', 'POST'], csrf=False)
    def job_action(self, picking_id, action, token=None, **kw):
        picking = self._job(picking_id, token)
        if not picking:
            return request.not_found()

        state = picking.sa_delivery_state
        error = ''
        try:
            if action == 'accepted' and state == 'offered':
                picking.sa_set_state('accepted')
            elif action == 'picked' and state in picking._SA_DISPATCH_FROM:
                # The pickup code (Delivery > Create OTP), typed by the rider.
                picking.sa_action_dispatch_with_otp(kw.get('otp') or '')
            elif action == 'start' and state == 'dispatched':
                picking.sa_action_rider_near()
            elif action == 'reached' and state in ('dispatched', 'out_for_delivery'):
                picking.sa_action_reached_customer()
            elif action == 'delivered' and state in ('dispatched', 'out_for_delivery'):
                # The customer's code, given after the parcel is in their hands.
                picking.sa_action_deliver_with_otp(kw.get('otp') or '')
            else:
                error = ''
            if action in ('accepted', 'picked', 'start', 'reached', 'delivered') and not error:
                _logger.info("Delivery: job %s -> %s by the rider",
                             picking.sa_ref_code, action)
        except Exception as err:  # noqa: BLE001 - shown on the page
            error = str(err)
        url = '/wa/delivery/%s?token=%s' % (picking.id, token)
        if error:
            from urllib.parse import quote
            url += '&error=' + quote(error[:160])
        return request.redirect(url)

    # There was a `/wa/rider/<rider_id>` route here: a rider's job list,
    # auth='public' with no token of its own, whose template printed each
    # job's sa_access_token into the links. Iterating small integer rider ids
    # therefore returned customers' names, addresses and phone numbers plus a
    # working action token for every one of that rider's jobs - enough to mark
    # somebody else's parcel delivered. Nothing ever generated the link.
    #
    # The rider app is served by controllers/delivery_api.py instead, which
    # authenticates with a hashed bearer token and scopes every object to the
    # rider it belongs to.

    # ------------------------------------------------------------------
    # Live position
    # ------------------------------------------------------------------
    @http.route('/wa/delivery/<int:picking_id>/ping', type='http',
                auth='public', methods=['POST'], csrf=False)
    def ping(self, picking_id, token=None, lat=None, lng=None, acc=None, **kw):
        """The rider's page reporting where it is.

        Accepted only while the job is actually in the rider's hands. Once it
        is delivered the page stops asking and this stops listening, so a
        forgotten browser tab cannot keep broadcasting somebody's location.
        """
        picking = self._job(picking_id, token)
        if not picking:
            return request.make_json_response({'ok': False}, status=404)
        if picking.sa_delivery_state not in ('accepted', 'picked'):
            return request.make_json_response({'ok': False, 'stop': True})
        request.env['sa.delivery.ping'].sudo()._sa_record(
            picking, lat, lng, acc)
        return request.make_json_response({'ok': True})

    def _tracked(self, picking_id, token):
        """The job a *customer* tracking token opens - watch only."""
        picking = request.env['stock.picking'].sudo().browse(int(picking_id))
        if not picking.exists() or not picking.sa_track_token or not token:
            return None
        if not hmac.compare_digest(str(picking.sa_track_token), str(token)):
            return None
        return picking

    @http.route('/wa/track/<int:picking_id>', type='http', auth='public',
                csrf=False)
    def track(self, picking_id, token=None, **kw):
        picking = self._tracked(picking_id, token)
        if not picking:
            return request.not_found()
        if picking.sale_id and visit_expired(picking.sale_id):
            return expired_page()
        partner = picking.partner_id
        company = picking.company_id
        return request.render('sales_automation_delivery.delivery_track_page', {
            'picking': picking,
            'token': token,
            'partner': partner,
            'rider': picking.sa_delivery_partner_id,
            'dest_lat': partner.partner_latitude or 0.0,
            'dest_lng': partner.partner_longitude or 0.0,
            'brand': company.name or 'Your order',
            'tagline': request.env['ir.config_parameter'].sudo().get_param(
                'sa_delivery.track_tagline', 'Beyond control. Beyond growth'),
            # Set `sa_delivery.track_logo_url` to a public image to replace
            # the drawn mark; the company logo is not used because Odoo ships
            # it pre-filled with its own placeholder.
            'logo_url': ((request.env['sa.brand'].logo_url(fallback='') if 'sa.brand' in request.env else '')
                         or request.env['ir.config_parameter'].sudo().get_param('sa_delivery.track_logo_url', '')),
            'tr': self._track_values(picking),
            # the first paint: the same answer /pos gives, so the map and the
            # headline are right before the first poll
            'init_json': json.dumps(picking.sudo().sa_track_payload(), default=str),
        })

    # ------------------------------------------------------------------
    # Everything the page shows, worked out once, here
    # ------------------------------------------------------------------
    _TRACK = {
        # state: (label, tone, progress, headline, sub)
        'to_assign': ('Order received', 'live', .06, 'Getting it ready',
                      'Your payment is in and the shop has your order.'),
        'awaiting_shop': ('Order received', 'live', .06, 'Getting it ready',
                          'Your payment is in. The shop is about to pick your items.'),
        'preparing': ('Being packed', 'live', .18, 'Being packed now',
                      'Somebody at the shop is packing your order right now.'),
        'ready': ('Packed', 'live', .3, 'Packed and ready',
                  'Your parcel is sealed. A rider is being called to collect it.'),
        'offered': ('Packed', 'live', .3, 'Packed and ready',
                    'Your parcel is sealed. A rider is being called to collect it.'),
        'accepted': ('Rider on the way to the shop', 'live', .42, 'Rider assigned',
                     'Your rider is heading to the shop to collect the parcel.'),
        'picked': ('Collected', 'live', .55, 'On its way',
                   'Your parcel has left the shop with the rider.'),
        'dispatched': ('Dispatched', 'live', .66, 'On its way',
                       'Your parcel is moving. The rider will message when close.'),
        'out_for_delivery': ('Out for delivery', 'live', .8, 'Arriving soon',
                             'Keep your phone nearby - you will get a code to hand to the rider.'),
        'delivered': ('Delivered', 'ok', 1.0, 'Delivered',
                      'Handed over at your door. Thank you for ordering with us.'),
        'returning': ('Going back to the shop', 'alert', .55, 'Could not be delivered',
                      'The rider could not complete the delivery and is returning the parcel. We will be in touch.'),
        'returned': ('Returned to the shop', 'alert', .55, 'Back at the shop',
                     'Your parcel is back at the shop. Someone will contact you about what happens next.'),
        'cancelled': ('Cancelled', 'alert', 0, 'Order cancelled',
                      'This order was cancelled. If you paid, the refund is being arranged.'),
        'failed': ('Delivery failed', 'alert', .8, 'Could not be delivered',
                   'The rider could not complete the delivery. Someone will contact you.'),
    }

    def _track_values(self, picking):
        state = picking.sa_delivery_state or 'to_assign'
        label, tone, progress, eta, sub = self._TRACK.get(
            state, self._TRACK['to_assign'])
        tz = pytz.timezone(picking.company_id.partner_id.tz
                           or picking.partner_id.tz or 'Asia/Muscat')

        def local(dt):
            return fields.Datetime.context_timestamp(
                picking.with_context(tz=tz.zone), dt) if dt else None

        def day(dt):
            if not dt:
                return ''
            loc = local(dt)
            return loc.strftime('%A, {} %B').format(loc.day)

        def clock(dt):
            return local(dt).strftime('%I:%M %p').lstrip('0') if dt else ''

        shop = picking.sa_shop_id.name or 'the shop'
        rider = picking.sa_delivery_partner_id
        rider_name = rider.name or 'Your rider'
        initials = ''.join(w[0] for w in rider_name.split()[:2]).upper() or 'R'
        # The shop's number, else the WhatsApp number this order runs on, else
        # the company's: never "#", which only reopened this page.
        shop_phone = picking._sa_help_number()

        # The promised time reads as the headline while the parcel is moving.
        promised = local(picking.sa_promised_on)
        if state == 'delivered':
            eta_tail = 'at %s, %s' % (clock(picking.sa_delivered_on),
                                       day(picking.sa_delivered_on))
        elif tone == 'alert':
            eta_tail = 'we will contact you'
        elif promised:
            eta_tail = 'by %s, %s' % (clock(picking.sa_promised_on),
                                       day(picking.sa_promised_on))
        else:
            eta_tail = 'time to be confirmed'

        # The journey, from the real stamps. Anything without a stamp has not
        # happened, so it is not shown as done.
        F = picking._fields
        stamps = [
            (picking.sale_id.date_order or picking.create_date,
             'Order confirmed', 'Payment received in full.', shop),
            (picking.sa_shop_seen_on if 'sa_shop_seen_on' in F else None,
             'Accepted by the shop', 'Your items are being picked.', shop),
            (picking.sa_shop_ready_on if 'sa_shop_ready_on' in F else None,
             'Packed and sealed', 'Ready for the rider.', shop),
            (picking.sa_offered_on, 'Rider called',
             'Looking for a rider to collect it.', shop),
            (picking.sa_accepted_on, 'Rider assigned',
             '%s is on the way to the shop.' % rider_name, shop),
            (picking.sa_picked_on, 'Collected from the shop',
             'Handed to %s.' % rider_name, shop),
            (picking.sa_dispatched_on, 'Dispatched',
             'Leaving for your address.', 'On the road'),
            (picking.sa_out_on, 'Out for delivery',
             'Last leg. A code was sent to you.', 'Near you'),
            (picking.sa_delivered_on, 'Delivered',
             'Handed over and confirmed with your code.', 'Your door'),
        ]
        if state in ('returning', 'returned'):
            stamps.append((picking.sa_returned_on or fields.Datetime.now(),
                           'Returning to the shop',
                           'The delivery could not be completed.', 'On the road'))
        if state == 'cancelled':
            stamps.append((picking.write_date, 'Cancelled', '', shop))

        events = []
        done = [s for s in stamps if s[0]]
        done.sort(key=lambda s: s[0])
        for i, (dt, title, note, place) in enumerate(done):
            last = i == len(done) - 1
            cls = ('is-ok' if last and state == 'delivered' else
                   'is-fail' if last and tone == 'alert' else
                   'is-now' if last else '')
            events.append({'day': day(dt), 'time': clock(dt), 'title': title,
                           'note': note, 'place': place, 'cls': cls})

        ladder = [('preparing', 'Being packed', 'Shortly', shop),
                  ('ready', 'Packed', 'Shortly', shop),
                  ('accepted', 'Rider assigned', 'When packed', shop),
                  ('picked', 'Collected', 'Once the rider arrives', shop),
                  ('out_for_delivery', 'Out for delivery',
                   'Promised %s' % eta_tail, 'Near you'),
                  ('delivered', 'Delivered', 'Promised %s' % eta_tail,
                   'Your door')]
        order = ['to_assign', 'awaiting_shop', 'preparing', 'ready', 'offered',
                 'accepted', 'picked', 'dispatched', 'out_for_delivery',
                 'delivered']
        pos = order.index(state) if state in order else len(order)
        nxt = [(t, w, p) for s, t, w, p in ladder
               if s in order and order.index(s) > pos] if tone != 'alert' else []

        # The person the customer is dealing with right now.
        if state in ('accepted', 'picked', 'dispatched', 'out_for_delivery',
                     'delivered'):
            who = ('Delivered by' if state == 'delivered' else 'Your rider',
                   rider_name, 'From %s' % shop, initials)
            note = {
                'accepted': 'Heading to %s to collect your parcel.' % shop,
                'picked': 'Has your parcel and is setting off.',
                'dispatched': 'On the road to you.',
                'out_for_delivery': 'Close by. Have your code ready - it was sent to you on WhatsApp.',
                'delivered': 'Confirmed with your code at the door.',
            }[state]
            actions = []
            if rider.phone and state != 'delivered':
                actions.append(('Call rider', 'btn-primary', 'tel:+%s' % ''.join(
                    ch for ch in rider.phone if ch.isdigit())))
        else:
            who = ('Handled by', shop, 'Dispatch counter', (shop[:1] or 'S').upper())
            note = {
                'to_assign': 'Your order is with the shop.',
                'awaiting_shop': 'Waiting for the counter to pick it up - usually a minute or two.',
                'preparing': 'Being packed now. You will be told when a rider is called.',
                'ready': 'Sealed and waiting for the rider.',
                'offered': 'Sealed. A rider has been asked to collect it.',
            }.get(state, 'Someone from the shop will contact you.')
            actions = []
        # The reference the customer knows is the enquiry's (the chat says
        # "Order #LX"); the job's own code is the delivery's.
        order_ref = ''
        sale = picking.sale_id
        if sale and hasattr(sale, '_sa_group_enquiry'):
            try:
                enquiry = sale.sudo()._sa_group_enquiry()
                order_ref = (enquiry.ref_code or '') if enquiry else ''
            except Exception:  # noqa: BLE001 - the page never fails over a label
                order_ref = ''
        order_ref = order_ref or picking.sa_ref_code or picking.name
        if shop_phone:
            actions.append(('WhatsApp the shop', 'btn-ghost',
                            'https://wa.me/%s?text=%s' % (
                                shop_phone, quote_plus('Order #%s: ' % order_ref))))

        due = picking.sa_amount_due()
        currency = picking.sa_currency_id or picking.company_id.currency_id
        promised = picking.sa_promised_on
        promise = ''
        if promised and state not in ('delivered', 'cancelled', 'failed', 'returned', 'returning'):
            promise = ('Promised between %s and %s' % (clock(promised - timedelta(hours=2)), clock(promised))
                       if picking.sa_delivery_kind == 'express' else 'Promised by %s' % clock(promised))
        return {
            'state': state, 'label': label, 'tone': tone, 'progress': progress,
            'eta': eta, 'eta_tail': eta_tail, 'sub': sub,
            'kind': picking.sa_delivery_kind or 'quick', 'promise': promise,
            'ref': '#%s' % order_ref,
            'delivery_ref': ('#%s' % picking.sa_ref_code) if (picking.sa_ref_code and picking.sa_ref_code != order_ref) else '',
            'who_head': who[0], 'who_name': who[1], 'who_role': who[2],
            'who_initials': who[3], 'who_note': note, 'actions': actions,
            'waypoints_json': json.dumps([shop, 'Packed', 'With rider', 'Your door']),
            'events': events, 'next': nxt,
            'live': state in ('accepted', 'picked', 'dispatched', 'out_for_delivery'),
            'items': [(m.product_id.name, ('%g' % m.product_uom_qty))
                      for m in picking.move_ids],
            'due': bool(due),
            'pay_label': 'To pay at the door' if due else 'Paid online',
            'pay_value': ('%s %s' % (
                ('%.*f' % (currency.decimal_places, due)) if due
                else ('%.*f' % (currency.decimal_places,
                                picking.sa_cod_amount or 0.0)),
                currency.name or '')).strip(),
            'help_text': ('Message us on WhatsApp and quote #%s.' % order_ref) if shop_phone else
                         ('Reply to this order\'s WhatsApp chat and quote #%s.' % order_ref),
            # The same reference the top of the page shows. '' hides the
            # button rather than linking to "#".
            'help_link': ('https://wa.me/%s?text=%s' % (
                shop_phone, quote_plus('Order #%s: ' % order_ref))) if shop_phone else '',
        }

    @http.route('/wa/track/<int:picking_id>/pos', type='http', auth='public',
                csrf=False)
    def track_position(self, picking_id, token=None, **kw):
        """What the customer's map polls for."""
        picking = self._tracked(picking_id, token)
        if not picking or (picking.sale_id and visit_expired(picking.sale_id)):
            return request.make_json_response({'ok': False}, status=404)
        state = picking.sa_delivery_state
        # One answer, decided on the server: who may see the rider, the stop
        # order, route, ETA, stale, ended (6 Oct 2026). The older keys stay.
        payload = picking.sudo().sa_track_payload()
        live = bool(payload['show_rider'])
        out = dict(payload)
        out.update({
            'ok': True,
            'state': state,
            'label': dict(picking._fields['sa_delivery_state'].selection
                          ).get(state, state),
            'live': live,
            # Withheld once the job is over: the customer follows a parcel,
            # not a person.
            'lat': (picking.sa_live_position().get('lat') or 0.0) if live else 0.0,
            'lng': (picking.sa_live_position().get('lng') or 0.0) if live else 0.0,
            'fix_on': (picking.sa_live_position()['fix_on'].isoformat()
                       if live and picking.sa_live_position().get('fix_on') else ''),
            'source': picking.sa_live_position().get('source') or '' if live else '',
            # degrees, 0 = north, clockwise; null until the rider has moved
            'heading': (picking.sa_rider_heading or None) if live else None,
            # The two ends of the trip, in both spellings: `latitude` is what
            # this page's map reads (it used to be overwritten here with
            # `lat` alone, so a known shop pin vanished after the first
            # poll), `lat` what other clients of this route read.
            'shop': self._both_spellings(payload.get('shop')),
            'dest': self._both_spellings(payload.get('dropoff')),
            'dropoff': self._both_spellings(payload.get('dropoff')),
            'rider': payload['rider'],
        })
        return request.make_json_response(out)

    @staticmethod
    def _both_spellings(place):
        place = dict(place or {})
        lat, lng = place.get('latitude') or None, place.get('longitude') or None
        place.update({'latitude': lat, 'longitude': lng, 'lat': lat, 'lng': lng,
                      'approximate': bool(place.get('approximate'))})
        return place

    def _values(self, picking, token):
        partner = picking.partner_id
        where = ', '.join(filter(None, [
            partner.street, partner.street2, partner.city, partner.zip,
            partner.country_id.name]))
        locked = not picking.sa_customer_revealed()
        if locked:
            where = picking.sa_customer_area()
        return {
            'picking': picking,
            'token': token,
            'partner': partner,
            'locked': locked,
            'where': where,
            'map_url': ('https://www.google.com/maps/search/?api=1&query=%s'
                        % quote_plus(where)) if where and not locked else '',
            'next_action': _NEXT.get(picking.sa_delivery_state),
        }
