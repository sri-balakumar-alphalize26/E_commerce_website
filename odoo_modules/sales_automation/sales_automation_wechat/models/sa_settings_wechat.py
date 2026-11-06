# -*- coding: utf-8 -*-
import hmac
import secrets
from datetime import timedelta

from odoo import api, fields, models


class SaAiSettingsWeChat(models.Model):
    _inherit = 'sa.ai.settings'

    wechat_enabled = fields.Boolean('WeChat bridge on', default=False,
                                    help="Off: WeChat vendors are not asked and the API refuses the bridge.")
    wechat_api_key = fields.Char('API key', groups='base.group_system', copy=False,
                                 help="Paste this into the bridge's config.json on the WeChat PC.")
    wechat_stale_minutes = fields.Integer(
        'Bridge counts as down after (minutes)', default=3,
        help="No heartbeat for this long: queued messages appear on the counter screen to relay by hand.")
    wechat_manual_when_down = fields.Boolean(
        'Relay by hand when the bridge is down', default=True)
    wechat_last_seen = fields.Datetime('Bridge last seen', readonly=True, copy=False)
    wechat_bridge_id = fields.Char('Bridge id', readonly=True, copy=False)
    wechat_bridge_alive = fields.Boolean(compute='_compute_wechat_status')
    wechat_queued_count = fields.Integer(compute='_compute_wechat_status')
    wechat_public_url = fields.Char(compute='_compute_wechat_status')

    @api.depends('wechat_last_seen', 'wechat_stale_minutes')
    def _compute_wechat_status(self):
        Msg = self.env['sa.wechat.message'].sudo()
        base = ''
        try:
            base = self.env['wa.auto.reply'].sudo()._sa_public_base() or ''
        except Exception:  # noqa: BLE001
            base = ''
        for s in self:
            s.wechat_bridge_alive = s._sa_wechat_alive()
            s.wechat_queued_count = Msg.search_count([('direction', '=', 'out'),
                                                      ('state', 'in', ('queued', 'claimed'))])
            s.wechat_public_url = base

    def _sa_wechat_alive(self):
        self.ensure_one()
        if not self.wechat_last_seen:
            return False
        minutes = max(1, self.wechat_stale_minutes or 3)
        return self.wechat_last_seen >= fields.Datetime.now() - timedelta(minutes=minutes)

    def _sa_wechat_key_ok(self, candidate):
        self.ensure_one()
        key = (self.sudo().wechat_api_key or '').strip()
        candidate = (candidate or '').strip()
        return bool(key) and hmac.compare_digest(key, candidate)

    def action_wechat_new_key(self):
        for s in self:
            s.sudo().write({'wechat_api_key': secrets.token_urlsafe(32)})
        return True
