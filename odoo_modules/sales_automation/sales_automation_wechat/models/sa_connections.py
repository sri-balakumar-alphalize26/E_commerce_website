# -*- coding: utf-8 -*-
"""One page for both channels' heartbeats: the WhatsApp gateway session(s)
and the WeChat bridge PC. Read-only, with a Refresh that re-checks the
WhatsApp gateway live and re-reads the bridge's last heartbeat."""
import logging
from datetime import timedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class SaAiSettingsConnections(models.Model):
    _inherit = 'sa.ai.settings'

    conn_whatsapp_html = fields.Html(compute='_compute_connections', sanitize=False)
    conn_wechat_html = fields.Html(compute='_compute_connections', sanitize=False)
    conn_checked_on = fields.Datetime('Last refreshed', readonly=True, copy=False)

    @staticmethod
    def _conn_pill(ok, text):
        color = '#16a34a' if ok else '#dc2626'
        return ('<span style="display:inline-block;padding:2px 10px;border-radius:12px;color:#fff;'
                'font-weight:600;background:%s">%s</span>' % (color, text))

    @staticmethod
    def _conn_ago(dt):
        if not dt:
            return 'never'
        secs = int((fields.Datetime.now() - dt).total_seconds())
        if secs < 60:
            return '%d s ago' % secs
        if secs < 3600:
            return '%d min ago' % (secs // 60)
        if secs < 86400:
            return '%d h ago' % (secs // 3600)
        return '%d days ago' % (secs // 86400)

    @api.depends('wechat_last_seen', 'wechat_stale_minutes', 'wechat_enabled', 'conn_checked_on')
    def _compute_connections(self):
        Msg = self.env['whatsapp.message'].sudo()
        WMsg = self.env['sa.wechat.message'].sudo()
        sessions = self.env['whatsapp.session'].sudo().search([('active', '=', True)])
        last_in = Msg.search([('direction', '=', 'incoming')], order='id desc', limit=1)
        last_out = Msg.search([('direction', '=', 'outgoing'), ('status', 'in', ('sent', 'delivered', 'read'))],
                              order='id desc', limit=1)
        rows = []
        for s in sessions:
            ok = s.status == 'connected'
            label = 'WRONG PHONE' if s.status == 'wrong_number' else (s.status or 'unknown').upper()
            allowed = getattr(s, 'authorized_number', '') or ''
            number = ('+' + s.phone_number) if s.phone_number else '-'
            if allowed:
                number += ' <span style="color:#6b7280">(allowed +%s)</span>' % allowed
            rows.append('<tr><td style="padding:4px 10px 4px 0"><b>%s</b></td><td style="padding:4px 10px">%s</td>'
                        '<td style="padding:4px 10px">%s</td><td style="padding:4px 10px;color:#6b7280">checked %s</td>'
                        '<td style="padding:4px 10px;color:#6b7280">%s</td></tr>' % (
                            s.name, self._conn_pill(ok, label),
                            number,
                            self._conn_ago(s.state_checked), (s.error_message or '')[:80]))
        wa_html = ('<table>%s</table><div style="margin-top:6px;color:#6b7280">Last message from a customer: %s '
                   '&nbsp;·&nbsp; last message sent: %s</div>' % (
                       ''.join(rows) or '<tr><td>No WhatsApp session configured.</td></tr>',
                       self._conn_ago(last_in.create_date) if last_in else 'never',
                       self._conn_ago(last_out.create_date) if last_out else 'never'))
        for rec in self:
            alive = rec._sa_wechat_alive()
            queued = WMsg.search_count([('direction', '=', 'out'), ('state', 'in', ('queued', 'claimed'))])
            failed = WMsg.search_count([('direction', '=', 'out'), ('state', '=', 'failed')])
            last_wx_in = WMsg.search([('direction', '=', 'in')], order='id desc', limit=1)
            if not rec.wechat_enabled:
                pill = self._conn_pill(False, 'SWITCHED OFF')
            else:
                pill = self._conn_pill(alive, 'ALIVE' if alive else 'DOWN')
            rec.conn_whatsapp_html = wa_html
            rec.conn_wechat_html = (
                '<table><tr><td style="padding:4px 10px 4px 0"><b>Bridge PC</b></td><td style="padding:4px 10px">%s</td>'
                '<td style="padding:4px 10px">%s</td><td style="padding:4px 10px;color:#6b7280">heartbeat %s</td></tr></table>'
                '<div style="margin-top:6px;color:#6b7280">Waiting to send: %d &nbsp;·&nbsp; failed: %d &nbsp;·&nbsp; '
                'last vendor reply: %s &nbsp;·&nbsp; counts as down after %d min without a heartbeat</div>' % (
                    pill, rec.wechat_bridge_id or '-', self._conn_ago(rec.wechat_last_seen), queued, failed,
                    self._conn_ago(last_wx_in.create_date) if last_wx_in else 'never',
                    max(1, rec.wechat_stale_minutes or 3)))

    def action_refresh_connections(self):
        """Ask the WhatsApp gateway for its live state, then redraw."""
        for s in self.env['whatsapp.session'].sudo().search([('active', '=', True)]):
            try:
                s._refresh_state(force=True)
            except Exception as err:  # noqa: BLE001 - one dead gateway must not hide the others
                _logger.info("Connections page: WhatsApp refresh of %s failed: %s", s.name, err)
        self.sudo().write({'conn_checked_on': fields.Datetime.now()})
        return True
