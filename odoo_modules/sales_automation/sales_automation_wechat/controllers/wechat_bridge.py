# -*- coding: utf-8 -*-
"""The API the WeChat bridge PC calls. Pull model: the PC polls, Odoo never
calls the PC. Every call carries the key in `X-SA-Key` and names the
database in `X-Odoo-Database` (the server serves several databases and
these routes carry no session cookie).

Nothing here exposes phone numbers, other vendors' prices or customer data:
the outbox carries the vendor's WeChat remark and the ask text; the
contacts list carries remarks only.
"""
import functools
import json
import logging
import time

from odoo import fields, http
from odoo.http import request

_logger = logging.getLogger(__name__)

_PREFIX = '/sa/wechat'
_RATE = {}          # ip -> [window_start, count]
_RATE_LIMIT = 120   # requests per minute per ip


def _json(payload, status=200):
    return request.make_json_response(payload, status=status)


def _fail(message, status=400):
    return _json({'ok': False, 'error': message}, status=status)


def _body():
    try:
        raw = request.httprequest.get_data(as_text=True) or ''
        if raw.strip().startswith('{'):
            return json.loads(raw)
    except (ValueError, TypeError):
        pass
    return dict(request.httprequest.values)


def _rate_ok(ip):
    now = time.time()
    win = _RATE.get(ip)
    if not win or now - win[0] > 60:
        _RATE[ip] = [now, 1]
        return True
    win[1] += 1
    return win[1] <= _RATE_LIMIT


def bridge_auth(func):
    """Key check, on/off switch, rate limit, heartbeat stamp."""
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        ip = request.httprequest.remote_addr or '?'
        if not _rate_ok(ip):
            return _fail('too many requests', 429)
        settings = request.env['sa.ai.settings'].sudo().get_settings()
        key = request.httprequest.headers.get('X-SA-Key') or ''
        if not settings._sa_wechat_key_ok(key):
            _logger.warning("WeChat bridge: bad key from %s", ip)
            return _fail('unauthorized', 401)
        if not settings.wechat_enabled:
            return _fail('wechat bridge is switched off', 503)
        data = _body()
        bridge_id = str(data.get('bridge_id') or request.httprequest.headers.get('X-SA-Bridge') or '')[:40]
        settings.sudo().write({'wechat_last_seen': fields.Datetime.now(),
                               'wechat_bridge_id': bridge_id or settings.wechat_bridge_id})
        return func(self, settings, data, bridge_id, *args, **kwargs)
    return wrapper


class SaWeChatBridge(http.Controller):

    @http.route(_PREFIX + '/heartbeat', type='http', auth='public', methods=['POST'], csrf=False)
    @bridge_auth
    def heartbeat(self, settings, data, bridge_id, **kw):
        Msg = request.env['sa.wechat.message'].sudo()
        return _json({'ok': True, 'server_time': fields.Datetime.now().isoformat() + 'Z',
                      'queued': Msg.search_count([('direction', '=', 'out'), ('state', 'in', ('queued', 'claimed'))]),
                      'wechat_ok': bool(data.get('wechat_ok', True))})

    @http.route(_PREFIX + '/outbox', type='http', auth='public', methods=['GET', 'POST'], csrf=False)
    @bridge_auth
    def outbox(self, settings, data, bridge_id, **kw):
        limit = kw.get('limit') or data.get('limit') or 20
        peek = str(kw.get('peek') or data.get('peek') or '') in ('1', 'true', 'yes')
        rows = request.env['sa.wechat.message'].sudo()._claim_outbox(limit=limit, peek=peek, bridge_id=bridge_id)
        return _json({'ok': True, 'rows': rows})

    @http.route(_PREFIX + '/sent', type='http', auth='public', methods=['POST'], csrf=False)
    @bridge_auth
    def sent(self, settings, data, bridge_id, **kw):
        ok = str(data.get('ok', '')).lower() in ('1', 'true', 'yes')
        done = request.env['sa.wechat.message'].sudo()._mark_sent(
            data.get('id'), ok, error=str(data.get('error') or ''), bridge_id=bridge_id)
        return _json({'ok': bool(done)})

    @http.route(_PREFIX + '/contacts', type='http', auth='public', methods=['GET', 'POST'], csrf=False)
    @bridge_auth
    def contacts(self, settings, data, bridge_id, **kw):
        partners = request.env['res.partner'].sudo().search(
            [('sa_via_wechat', '=', True), ('sa_wechat_name', '!=', False)])
        return _json({'ok': True, 'contacts': sorted({(p.sa_wechat_name or '').strip() for p in partners} - {''})})

    @http.route(_PREFIX + '/inbound', type='http', auth='public', methods=['POST'], csrf=False)
    @bridge_auth
    def inbound(self, settings, data, bridge_id, **kw):
        res = request.env['sa.wechat.message'].sudo()._sa_ingest(
            data.get('from'), data.get('text'), wx_id=data.get('wx_id') or '',
            at=data.get('at'), bridge_id=bridge_id)
        return _json(res)
