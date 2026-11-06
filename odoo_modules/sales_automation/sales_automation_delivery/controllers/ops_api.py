# -*- coding: utf-8 -*-
"""The full-flow API (`/api/sa/*`): every WhatsApp order from the enquiry to
the delivered parcel, read and driven by an external app (the shop / admin
APK). The rider's own API stays at `/api/delivery/*`.

Auth: header `X-SA-Key` = Delivery Settings > "Order flow API key", or an
Odoo session of an internal user. Multi-database servers: send
`X-Odoo-Database: <db>` (or `?db=`) on every call.

Every setter ends in the same model method the Odoo button calls, so the
counter, the rider link, the rider app and this API never disagree.
"""
import functools
import hmac
import logging

from odoo import _, fields, http
from odoo.http import request

from .delivery_api import _body, _currency_block, _dt, _fail, _json, _money

_logger = logging.getLogger(__name__)

_PREFIX = '/api/sa'

# What the shop may press next, per job state (mirrors the form buttons).
_SHOP_ACTIONS = {
    'awaiting_shop': ['accept', 'cancel'],
    'preparing': ['packed', 'unaccept', 'cancel'],
    'ready': ['call_rider', 'generate_pickup_code', 'dispatch', 'cancel'],
    'to_assign': ['call_rider', 'generate_pickup_code', 'dispatch', 'cancel'],
    'offered': ['next_rider', 'call_rider', 'generate_pickup_code', 'dispatch', 'cancel'],
    'accepted': ['branch_dispatch', 'generate_pickup_code', 'dispatch', 'cancel'],
    'picked': ['generate_pickup_code', 'dispatch', 'cancel'],
    'dispatched': ['near', 'fail', 'cancel'],
    # (any state) 'issue_seen' clears the rider's report
    'out_for_delivery': ['reached', 'deliver', 'fail', 'cancel'],
    'returning': ['confirm_return'],
}


def _flow_step(order, req, job, inv_paid, inv):
    """One word for where the order stands, in flow order."""
    if job and job.sa_delivery_state not in ('none', False):
        return 'delivery_' + job.sa_delivery_state
    if inv_paid:
        return 'paid'
    if inv:
        return 'invoiced'
    if order.state in ('sale', 'done'):
        return 'signed' if (getattr(order, 'signature', False) or
                            (req and req.sa_sign_link_sent_on)) else 'confirmed'
    if order.state == 'cancel':
        return 'cancelled'
    if req and req.sa_sign_link_sent_on:
        return 'awaiting_signature'
    return 'order_created'


def ops_auth(func):
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        settings = request.env['sa.delivery.settings'].sudo().get_settings()
        key = (request.httprequest.headers.get('X-SA-Key') or
               _body().get('api_key') or '')
        ok = False
        if key and settings.ops_api_key:
            ok = hmac.compare_digest(key, settings.ops_api_key)
        if not ok and request.session.uid:
            user = request.env['res.users'].sudo().browse(request.session.uid)
            ok = bool(user.exists() and not user.share)
        if not ok:
            _logger.warning("Order flow API: refused call from %s",
                            request.httprequest.remote_addr)
            return _fail(_("Not authorised."), status=401, code='unauthorized')
        return func(self, settings, *args, **kwargs)
    return wrapper


class SaOpsApi(http.Controller):

    # ------------------------------------------------------------------
    # blocks
    # ------------------------------------------------------------------
    def _job_block(self, job):
        if not job or job.sa_delivery_state in ('none', False):
            return None
        partner = job.partner_id
        return {
            'delivery_order_id': job.id,
            'delivery_order_name': job.name,
            'job_code': job.sa_ref_code or '',
            'state': job.sa_delivery_state,
            'state_label': dict(job._fields['sa_delivery_state']._description_selection(
                request.env)).get(job.sa_delivery_state, ''),
            'stage_text': job.sa_stage_text or '',
            'stock_state': job.state,
            'shop': {'id': job.sa_shop_id.id, 'name': job.sa_shop_id.name or ''} if job.sa_shop_id else None,
            'rider': {'id': job.sa_delivery_partner_id.id,
                      'name': job.sa_delivery_partner_id.name or '',
                      'phone': job.sa_delivery_partner_id.phone or ''} if job.sa_delivery_partner_id else None,
            'delivery_type': job.sa_delivery_kind or '',
            'promised_by': _dt(job.sa_promised_on),
            'amount_to_collect': _money(job.sa_amount_due(), job.sa_currency_id),
            'pickup_code': job.sa_pickup_code_shown or '',     # clear only until Dispatch
            'pickup_handover': job.sa_pickup_mode(),
            'rider_arrived_at': _dt(job.sa_arrived_shop_on),
            'near_customer_at': _dt(job.sa_out_on),
            'near_customer_auto': bool(job.sa_near_auto),
            'handover': job.sa_handover_block(),
            'photos': job.sa_photos_block(_PREFIX + '/proof'),
            'photos_missing': job.sa_photos_missing_list(),
            # what the rider reported last and what is running because of it
            'problem': job.sa_problem_block(),
            'drop_point': job.sa_drop_block(),
            'relay': ({'state': job.sa_relay_state,
                       'to_rider': job.sa_relay_to_id.name or '',
                       'from_rider': job.sa_delivery_partner_id.name or ''}
                      if job.sa_relay_state else None),
            'taken_over_from': job.sa_relay_from_id.name or '',
            'reached_customer_on': _dt(job.sa_arrived_customer_on),
            'timestamps': {
                'offered': _dt(job.sa_offered_on), 'accepted': _dt(job.sa_accepted_on),
                'picked_up': _dt(job.sa_picked_on), 'dispatched': _dt(job.sa_dispatched_on),
                'out_for_delivery': _dt(job.sa_out_on), 'delivered': _dt(job.sa_delivered_on),
            },
            'last_error': job.sa_last_error or '',
            'tracking_url': job.sa_track_url or '',
            'rider_earning': _money(job.sa_rider_fee, job.sa_currency_id) if job.sa_rider_fee else None,
            'shop_to_customer_m': job.sa_trip_m or None,
            'delivery_note': job.sa_delivery_note or '',
            'customer_pin': {'latitude': partner.partner_latitude or None,
                             'longitude': partner.partner_longitude or None,
                             'source': job.sa_pin_source or ''},
            'rider_report': {'kind': job.sa_issue_kind or '', 'text': job.sa_issue_text or '',
                             'note': job.sa_issue_note or '',
                             'at': _dt(job.sa_issue_on)} if job.sa_issue_on else None,
            'reports': job.sa_reports_block(_PREFIX + '/proof'),
            'tracking_live': job.sa_tracking_enabled(),
            'rider_position': ({'latitude': pos['lat'], 'longitude': pos['lng'],
                                'fix_at': _dt(pos.get('fix_on')), 'source': pos.get('source')}
                               if (pos := job.sa_live_position()) else None),
            'shop_actions': list(_SHOP_ACTIONS.get(job.sa_delivery_state, [])),
            'rider_actions': job.sa_allowed_actions(),
            'customer_address': ', '.join(filter(None, [
                partner.street, partner.street2, partner.city, partner.zip])),
            'write_date': _dt(job.write_date),
        }

    def _order_block(self, order):
        order = order.sudo()
        req = order._sa_group_enquiry() if hasattr(order, '_sa_group_enquiry') else None
        req = req.sudo() if req else None
        inv = order.invoice_ids.filtered(lambda m: m.move_type == 'out_invoice'
                                         and m.state != 'cancel').sorted('id')
        posted = inv.filtered(lambda m: m.state == 'posted')
        inv_paid = bool(posted) and all(m.payment_state in ('paid', 'in_payment')
                                        for m in posted)
        if not inv and order.transaction_ids.filtered(lambda t: t.state == 'done'):
            inv_paid = True
        jobs = order.picking_ids.filtered(
            lambda p: p.picking_type_code == 'outgoing' and p.state != 'cancel')
        job = jobs.filtered(lambda p: p.sa_delivery_state not in ('none', False)).sorted('id')[:1] \
            or jobs.sorted('id')[:1]
        partner = order.partner_id
        first = inv[:1]
        stamps = [order.write_date] + [p.write_date for p in jobs] + [m.write_date for m in inv]
        if req:
            stamps.append(req.write_date)
        return {
            'order_id': order.id,
            'name': order.name,
            'state': order.state,
            'flow_step': _flow_step(order, req, job, inv_paid, inv),
            'enquiry': {'id': req.id, 'ref': req.ref_code or '', 'state': req.state,
                        'group': req.group_id.name or '',
                        'sign_link_sent': _dt(req.sa_sign_link_sent_on),
                        'pay_link_sent': _dt(req.sa_pay_link_sent_on),
                        'paid_told': _dt(req.sa_paid_told_on)} if req else None,
            'customer': {'id': partner.id, 'name': partner.name or '',
                         'phone': partner.phone or partner.mobile or '',
                         'address': ', '.join(filter(None, [
                             partner.street, partner.street2, partner.city, partner.zip]))},
            'lines': [{'product_id': l.product_id.id, 'name': l.product_id.display_name,
                       'qty': l.product_uom_qty, 'price_unit': l.price_unit,
                       'subtotal': l.price_subtotal}
                      for l in order.order_line if l.product_id and not l.display_type],
            'amount_total': _money(order.amount_total, order.currency_id),
            'currency': _currency_block(order.currency_id),
            'signed': bool(getattr(order, 'signature', False)),
            'invoice': {'id': first.id, 'name': first.name or '', 'state': first.state,
                        'payment_state': first.payment_state or '',
                        'amount_residual': _money(first.amount_residual, order.currency_id)} if first else None,
            'paid': inv_paid,
            'delivery': self._job_block(job),
            'date_order': _dt(order.date_order),
            'write_date': _dt(max(d for d in stamps if d)),
        }

    def _orders(self, since=None, limit=100, state=None, step=None):
        Order = request.env['sale.order'].sudo()
        domain = ['|', ('sa_group_request_id', '!=', False),
                  ('picking_ids.sa_delivery_state', 'not in', ('none', False))]
        if state:
            domain.append(('state', '=', state))
        orders = Order.search(domain, order='id desc', limit=max(1, min(int(limit or 100), 500)))
        if since:
            dt = fields.Datetime.to_datetime(since.replace('Z', '').replace('T', ' ')[:19])
            # anything whose order / job / invoice / enquiry moved since
            keep = Order
            for o in orders:
                stamps = [o.write_date] + [p.write_date for p in o.picking_ids] + \
                         [m.write_date for m in o.invoice_ids]
                req = o._sa_group_enquiry() if hasattr(o, '_sa_group_enquiry') else None
                if req:
                    stamps.append(req.write_date)
                if max(d for d in stamps if d) > dt:
                    keep |= o
            orders = keep
        out = [self._order_block(o) for o in orders]
        if step:
            out = [b for b in out if b['flow_step'] == step]
        return out

    # ------------------------------------------------------------------
    # routes
    # ------------------------------------------------------------------
    @http.route(_PREFIX + '/ping', type='http', auth='public', methods=['GET', 'POST'], csrf=False)
    @ops_auth
    def ping(self, settings, **kw):
        Mod = request.env['ir.module.module'].sudo()
        return _json({'success': True, 'db': request.db, 'now': _dt(fields.Datetime.now()),
                      'flow_end': settings.flow_end,
                      'versions': {m.name: m.latest_version for m in Mod.search(
                          [('name', 'like', 'sales_automation%'), ('state', '=', 'installed')])}})

    @http.route(_PREFIX + '/settings', type='http', auth='public', methods=['GET'], csrf=False)
    @ops_auth
    def settings(self, settings, **kw):
        return _json({'success': True, 'flow_end': settings.flow_end,
                      'shop_confirms': getattr(settings, 'shop_confirms', True),
                      'quick_enabled': settings.quick_enabled, 'quick_hours': settings.quick_hours,
                      'express_days': settings.express_days, 'cutoff_hour': settings.cutoff_hour,
                      'otp_test_mode': settings.otp_test_mode,
                      'call_rider_mode': settings.call_rider_mode or 'ask',
                      'pickup_handover': settings.pickup_handover or 'branch',
                      'hide_customer_until_pickup': bool(settings.hide_customer_until_pickup),
                      'dispatch_radius_km': settings.dispatch_radius_km,
                      'offer_timeout_seconds': settings.offer_timeout_seconds,
                      'job_states': [{'key': k, 'label': v} for k, v in request.env['stock.picking']
                                     ._fields['sa_delivery_state']._description_selection(request.env)],
                      'shop_actions': _SHOP_ACTIONS})

    @http.route(_PREFIX + '/orders', type='http', auth='public', methods=['GET'], csrf=False)
    @ops_auth
    def orders(self, settings, **kw):
        rows = self._orders(since=kw.get('since'), limit=kw.get('limit') or 100,
                            state=kw.get('state'), step=kw.get('step'))
        return _json({'success': True, 'now': _dt(fields.Datetime.now()), 'count': len(rows), 'orders': rows})

    @http.route(_PREFIX + '/updates', type='http', auth='public', methods=['GET'], csrf=False)
    @ops_auth
    def updates(self, settings, **kw):
        """Poll this with `since` = the `now` of the previous reply."""
        since = kw.get('since')
        if not since:
            return _fail(_("since is required (ISO datetime, UTC)."), code='bad_request')
        rows = self._orders(since=since, limit=kw.get('limit') or 200)
        return _json({'success': True, 'now': _dt(fields.Datetime.now()), 'count': len(rows), 'orders': rows})

    @http.route(_PREFIX + '/orders/<int:order_id>', type='http', auth='public', methods=['GET'], csrf=False)
    @ops_auth
    def order_detail(self, settings, order_id, **kw):
        order = request.env['sale.order'].sudo().browse(order_id).exists()
        if not order:
            return _fail(_("Not found."), status=404, code='not_found')
        return _json({'success': True, 'order': self._order_block(order)})

    @http.route(_PREFIX + '/jobs/<int:job_id>', type='http', auth='public', methods=['GET'], csrf=False)
    @ops_auth
    def job_detail(self, settings, job_id, **kw):
        job = request.env['stock.picking'].sudo().browse(job_id).exists()
        if not job:
            return _fail(_("Not found."), status=404, code='not_found')
        return _json({'success': True, 'job': self._job_block(job),
                      'order': self._order_block(job.sale_id) if job.sale_id else None})

    @http.route(_PREFIX + '/riders', type='http', auth='public', methods=['GET'], csrf=False)
    @ops_auth
    def riders(self, settings, **kw):
        rows = request.env['sa.delivery.partner'].sudo().search([('active', '=', True)])
        lat0 = lng0 = None
        if kw.get('shop_id'):
            shop = request.env['sa.delivery.shop'].sudo().browse(int(kw['shop_id'])).exists()
            if shop:
                lat0, lng0 = shop._sa_position()
        Ping = request.env['sa.delivery.ping'].sudo()
        out = []
        for r in rows:
            dist = None
            if lat0 and lng0 and r.last_lat and r.last_lng:
                dist = int(Ping._sa_metres(lat0, lng0, r.last_lat, r.last_lng))
            out.append({'id': r.id, 'name': r.name, 'phone': r.phone or '',
                        'on_duty': bool(r.on_duty), 'is_busy': bool(r.is_busy),
                        'fleet_state': r.fleet_state or '', 'address_short': r.address_short or '',
                        'latitude': r.last_lat or None, 'longitude': r.last_lng or None,
                        'last_fix_at': _dt(r.last_fix_on), 'duty_since': _dt(r.duty_since),
                        'distance_m': dist,
                        'shop_ids': r.shop_ids.ids})
        return _json({'success': True, 'riders': out})

    @http.route(_PREFIX + '/jobs/<int:job_id>/position', type='http', auth='public',
                methods=['GET'], csrf=False)
    @ops_auth
    def job_position(self, settings, job_id, **kw):
        """Live position of the rider on this job, for the shop app's own map.
        Poll every 5-10 s while `live` is true."""
        job = request.env['stock.picking'].sudo().browse(job_id).exists()
        if not job or job.sa_delivery_state in ('none', False):
            return _fail(_("Not found."), status=404, code='not_found')
        pos = job.sa_live_position()
        shop_lat, shop_lng = job.sa_shop_position()
        partner = job.partner_id
        return _json({'success': True, 'job_code': job.sa_ref_code or '', 'state': job.sa_delivery_state,
                      'state_label': dict(job._fields['sa_delivery_state']._description_selection(
                          request.env)).get(job.sa_delivery_state, ''),
                      'live': job.sa_tracking_enabled(),
                      'rider': job.sa_delivery_partner_id.name or '',
                      'position': {'latitude': pos['lat'], 'longitude': pos['lng'],
                                   'fix_at': _dt(pos.get('fix_on')), 'source': pos.get('source')} if pos else None,
                      'shop': {'latitude': shop_lat, 'longitude': shop_lng, 'name': job.sa_shop_id.name or ''},
                      'destination': {'latitude': partner.partner_latitude or None,
                                      'longitude': partner.partner_longitude or None,
                                      'address': ', '.join(filter(None, [partner.street, partner.city, partner.zip]))},
                      'tracking_url': job.sa_track_url or ''})

    @http.route(_PREFIX + '/proof/<int:attachment_id>', type='http', auth='public',
                methods=['GET'], csrf=False)
    @ops_auth
    def proof_get(self, settings, attachment_id, **kw):
        """One parcel photo (pickup or delivery) of a delivery job."""
        att = request.env['ir.attachment'].sudo().browse(attachment_id).exists()
        job = request.env['stock.picking'].sudo().browse(att.res_id) \
            if att and att.res_model == 'stock.picking' else None
        if not job or not job.sa_photo_for(att.id):
            return _fail(_("Not found."), status=404, code='not_found')
        return request.make_response(att.raw or b'', headers=[
            ('Content-Type', att.mimetype or 'image/jpeg'),
            ('Content-Disposition', 'inline; filename="%s"' % (att.name or 'photo.jpg')),
            ('Cache-Control', 'private, max-age=86400')])

    @http.route(_PREFIX + '/jobs/<int:job_id>/candidates', type='http', auth='public',
                methods=['GET'], csrf=False)
    @ops_auth
    def job_candidates(self, settings, job_id, **kw):
        """The ranked riders for this job, as the Call a Rider dialog shows them."""
        job = request.env['stock.picking'].sudo().browse(job_id).exists()
        if not job or job.sa_delivery_state in ('none', False):
            return _fail(_("Not found."), status=404, code='not_found')
        return _json({'success': True, 'job_code': job.sa_ref_code or '', 'state': job.sa_delivery_state,
                      'offered_to': job.sa_delivery_partner_id.name or '',
                      'offer_seconds_left': job.sa_offer_seconds_left,
                      'round': job.sa_offer_round or 0,
                      'candidates': job.sa_candidates_brief()})

    @http.route(_PREFIX + '/shops', type='http', auth='public', methods=['GET'], csrf=False)
    @ops_auth
    def shops(self, settings, **kw):
        rows = request.env['sa.delivery.shop'].sudo().search([])
        return _json({'success': True, 'shops': [
            {'id': s.id, 'name': s.name, 'phone': getattr(s, 'phone', '') or '',
             'warehouse': s.warehouse_id.name if getattr(s, 'warehouse_id', False) else ''} for s in rows]})

    @http.route(_PREFIX + '/jobs/<int:job_id>/<string:action>', type='http', auth='public',
                methods=['POST'], csrf=False)
    @ops_auth
    def job_action(self, settings, job_id, action, **kw):
        """The shop-side buttons, by name (see `shop_actions` on the job)."""
        job = request.env['stock.picking'].sudo().browse(job_id).exists()
        if not job or job.sa_delivery_state in ('none', False):
            return _fail(_("Not found."), status=404, code='not_found')
        data = _body()
        allowed = list(_SHOP_ACTIONS.get(job.sa_delivery_state, [])) + ['issue_seen']
        if job.sa_relay_state:
            allowed += ['relay_retry', 'relay_cancel']
        if action not in allowed:
            return _fail(_("Job #%(ref)s is %(state)s - '%(action)s' is not possible now.",
                          ref=job.sa_ref_code, state=job.sa_delivery_state, action=action),
                         status=409, code='wrong_state', shop_actions=allowed)
        extra = {}
        try:
            if action == 'relay_retry':
                job.action_sa_relay_retry()
            elif action == 'relay_cancel':
                job.action_sa_relay_cancel()
            elif action == 'accept':
                job.sa_shop_accept()
            elif action == 'packed':
                job.sa_shop_ready()
            elif action == 'unaccept':
                job.sa_shop_unaccept()
            elif action == 'branch_dispatch':
                # the branch's Dispatch: the code for the staff to read out
                res = job.sa_action_branch_dispatch()
                extra.update({'pickup_code': res['code'], 'expires_at': res['expires_at'],
                              'rider_arrived': res['arrived']})
            elif action == 'generate_pickup_code':
                job.sa_action_generate_pickup_code()
                extra['pickup_code'] = job.sa_pickup_code_shown or ''
            elif action == 'dispatch':
                rider_id = data.get('rider_id')
                job.sa_action_dispatch_with_otp(str(data.get('otp') or ''),
                                                rider_id=int(rider_id) if rider_id else None)
            elif action == 'near':
                job.sa_action_rider_near()
            elif action == 'reached':
                job.sa_action_reached_customer()
            elif action == 'deliver':
                job.sa_action_deliver_with_otp(str(data.get('otp') or ''))
            elif action == 'fail':
                job.sa_action_fail(data.get('reason') or 'other')
            elif action == 'cancel':
                job.sa_action_cancel(reason=data.get('reason') or '')
            elif action == 'call_rider':
                ids = data.get('rider_ids') or ([data.get('rider_id')] if data.get('rider_id') else [])
                if isinstance(ids, str):
                    ids = [x for x in ids.replace('[', '').replace(']', '').split(',') if x.strip()]
                chosen = job.sa_action_call_rider(rider_ids=[int(x) for x in ids] or None)
                extra['called'] = chosen.name if chosen else ''
            elif action == 'next_rider':
                chosen = job.sa_action_next_rider()
                extra['called'] = chosen.name if chosen else ''
            elif action == 'confirm_return':
                job.sa_action_confirm_return()
            elif action == 'issue_seen':
                job.sa_action_issue_seen()
        except Exception as err:  # noqa: BLE001 - the app gets the words
            request.env.cr.rollback()
            msg = getattr(err, 'args', [str(err)])[0] if getattr(err, 'args', None) else str(err)
            _logger.info("Order flow API: %s on %s refused: %s", action, job.sa_ref_code, msg)
            return _fail(str(msg), status=400, code='refused',
                         shop_actions=_SHOP_ACTIONS.get(job.sa_delivery_state, []))
        job.invalidate_recordset()
        out = {'success': True, 'action': action, 'job': self._job_block(job)}
        out.update(extra)
        return _json(out)
