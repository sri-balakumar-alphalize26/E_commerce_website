"""Where the parcel is, for the customer's own order page.

The WhatsApp customer follows a token link (`/wa/track/<id>?token=`) that the
delivery stack draws itself. The website draws its own card instead, so this
is the same answer as that page's `/pos` poll, read off the same job - but
reached through the customer's signed-in order, never through the token. The
token and the link it makes never leave this file: whoever holds them can
watch the rider, and the website has no reason to hand that out.

**The rider's name has one source.** It is the `sa.delivery.partner` on the
order's delivery job - the record the rider app and the shop work from. The
order page, the live map and both chatbots ask `_mart369_rider_name()`, so they
cannot drift apart again the way the made-up names did (orderState.js used to
hash the order number into a list of five invented riders).

Where the delivery stack is new enough to build the payload itself
(`stock.picking.sa_track_payload`, delivery 19.0.23 and later - the Dubai
server), that is used, so the website shows exactly what the WhatsApp page
shows: the server decides whether the rider may be seen, and draws the road.
Older stacks get the local equivalent of `/wa/track/<id>/pos`.
"""

import logging
import re

from odoo import fields, models

_logger = logging.getLogger(__name__)

# The job stages a rider is moving in - `/wa/track/<id>/pos`'s own `live`.
LIVE = ('accepted', 'picked', 'dispatched', 'out_for_delivery')
# From here on there is nothing left to follow.
ENDED = ('delivered', 'returned', 'cancelled', 'failed')
# Stages in which the rider is really theirs: accepted, not just pencilled in.
RIDER_KNOWN = LIVE + ('returning', 'delivered')

# A rider app that has not reported for this long has lost its signal.
STALE_AFTER = 120

# Names that are a role, not a person. The test rider is literally "rider".
PLACEHOLDERS = {
    'rider', 'driver', 'delivery', 'delivery boy', 'delivery partner',
    'courier', 'test', 'test rider', 'user', 'admin', 'new', 'none',
}


def _clean_name(name, login=''):
    """A name fit to show a customer, or '' when there is none."""
    name = ' '.join((name or '').split())
    if not name:
        return ''
    low = name.lower()
    # A phone number, or a generated record ("Addr A 1789648770") - a long
    # run of digits is never part of somebody's name.
    if (low in PLACEHOLDERS or '@' in name
            or re.search(r'\d{5,}', name)
            or re.fullmatch(r'[\d\s+()-]+', name)
            or (login and low == login.strip().lower())):
        return ''
    # Typed all in one case ("bala", "BALA KUMAR") reads as a name once
    # capitalised; anything mixed was typed on purpose and is left alone.
    if name.islower() or name.isupper():
        name = name.title()
    return name


def _digits(phone):
    digits = ''.join(ch for ch in (phone or '') if ch.isdigit())
    return ('+' + digits) if digits else ''


def _iso(value):
    """A stored (UTC, naive) datetime as ISO-8601 the browser reads as UTC."""
    return value.replace(microsecond=0).isoformat() + 'Z' if value else ''


def _point(lat, lng):
    return {'lat': lat, 'lng': lng} if (lat or lng) else None


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # ------------------------------------------------------------- the rider

    def _mart369_rider(self):
        """(rider record, console user) actually delivering this order.

        The rider record is the job's, and only once the rider has accepted:
        before that a name is a guess, and a customer told "Bala is on the
        way" by a pencilled-in assignment gets the wrong person at the door.
        An order with no job (the bridge not yet reached it) falls back to
        the console's own rider.
        """
        self.ensure_one()
        job = self._mart369_bridge_job()
        if job:
            if job.sa_delivery_state in RIDER_KNOWN:
                return job.sa_delivery_partner_id, self.sudo().mart369_rider_id
            return self.env['sa.delivery.partner'], self.env['res.users']
        return self.env['sa.delivery.partner'], self.sudo().mart369_rider_id

    def _mart369_rider_name(self):
        """The rider's real name, or '' - never a login or a placeholder.

        Only the rider record's own name. Its linked contact is not a
        fallback: on a test database that is any partner somebody picked,
        and a wrong name is worse than "Your rider".
        """
        self.ensure_one()
        rider, user = self._mart369_rider()
        if rider:
            login = (rider.user_id.login if 'user_id' in rider._fields and rider.user_id
                     else user.login if user else '')
            return _clean_name(rider.name, login)
        if user:
            return _clean_name(user.partner_id.name or user.name, user.login)
        return ''

    def _mart369_rider_phone(self):
        self.ensure_one()
        rider, user = self._mart369_rider()
        return _digits(rider.phone if rider else '') or _digits(
            user.partner_id.phone if user else '')

    # ---------------------------------------------------------- the payload

    def _mart369_track(self):
        """What the order page's live card draws, or None with no job yet."""
        self.ensure_one()
        job = self._mart369_bridge_job()
        if not job:
            return None
        payload = self._mart369_track_local(job)
        if hasattr(job, 'sa_track_payload'):
            try:
                payload.update(self._mart369_track_stack(job, payload))
            except Exception:  # noqa: BLE001 - the card never fails over the road
                _logger.exception('mart369: sa_track_payload failed for %s', job.id)
        # Withheld once the job is over, as the WhatsApp page does: the
        # customer follows a parcel, not a person. The phone only while the
        # rider is on the way - it is the rider's own number.
        if not payload['live']:
            payload.update({'lat': 0.0, 'lng': 0.0, 'show_rider': False})
        if not payload['live']:
            payload['rider']['phone'] = ''
        return payload

    def _mart369_track_local(self, job):
        """The local equivalent of `/wa/track/<id>/pos`, and a bit more."""
        state = job.sa_delivery_state or 'to_assign'
        live = state in LIVE
        fix = job.sa_rider_fix_on
        age = int((fields.Datetime.now() - fix).total_seconds()) if fix else None
        dest = job.partner_id or self.partner_shipping_id
        shop = job.sa_shop_id._sa_address() if job.sa_shop_id else None
        return {
            'picking_id': job.id,
            'state': state,
            'label': dict(job._fields['sa_delivery_state'].selection).get(state, state),
            'live': live,
            'ended': state in ENDED or self.mart369_state in ('delivered', 'cancelled'),
            # Quick and Express both show the rider here; the newer stack
            # decides per kind and overrides this below.
            'show_rider': live and bool(job.sa_rider_lat or job.sa_rider_lng),
            'lat': job.sa_rider_lat or 0.0,
            'lng': job.sa_rider_lng or 0.0,
            'fix_on': _iso(fix),
            'age': age,
            'stale': live and age is not None and age > STALE_AFTER,
            'eta': _iso(job.sa_promised_on),
            'eta_text': self.mart369_eta or '',
            'dest': _point(dest.partner_latitude, dest.partner_longitude) if dest else None,
            'shop': (dict(_point(shop.partner_latitude, shop.partner_longitude) or {},
                          name=job.sa_shop_id.name or '')
                     if shop and (shop.partner_latitude or shop.partner_longitude) else None),
            'route': None,
            'route_approx': True,
            'rider': {
                'name': self._mart369_rider_name(),
                'phone': self._mart369_rider_phone(),
            },
        }

    def _mart369_track_stack(self, job, local):
        """The delivery stack's own payload, in this card's shape.

        Read defensively: only the keys it sends are taken, and a missing one
        keeps the local answer. `rider` arrives as null when the stack hides
        the rider (Express between stops), which hides the dot here too.
        """
        theirs = job.sa_track_payload() or {}
        if not isinstance(theirs, dict):
            return {}
        out = {}
        for key in ('state', 'label', 'live', 'ended', 'stale', 'eta',
                    'lat', 'lng', 'show_rider'):
            if key in theirs and theirs[key] is not None:
                out[key] = theirs[key]
        if 'fix_on' in theirs:
            out['fix_on'] = theirs['fix_on'] or ''
        route = theirs.get('route')
        if isinstance(route, dict):
            out['route'] = route.get('points') or route.get('coordinates')
            out['route_approx'] = bool(route.get('approximate'))
        elif isinstance(route, list):
            out['route'] = route
            out['route_approx'] = bool(theirs.get('approximate'))
        if 'rider' in theirs and theirs['rider'] is None:
            out['show_rider'] = False
        # The name is always ours: one source, cleaned the same way.
        return out

    # ------------------------------------------------------- the order JSON

    def _mart369_serialize(self):
        """The order says who is delivering it, once somebody really is."""
        data = super()._mart369_serialize()
        name = self._mart369_rider_name()
        data['rider'] = {'name': name} if name else None
        return data
