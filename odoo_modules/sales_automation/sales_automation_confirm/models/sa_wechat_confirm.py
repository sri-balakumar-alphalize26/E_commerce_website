# -*- coding: utf-8 -*-
"""WeChat vendors: the price check carries the picture and the page link.

The bridge sends the picture first (from `image_url`, a tokened address on
this server) and then the text, whose last line is the link. ACCEPT on the
page = "I have this exact product" (the price step is queued in the chat),
REJECT = "don't have it". The typed 1 / 2 keep working.
"""
import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class SaWeChatMessageConfirm(models.Model):
    _inherit = 'sa.wechat.message'

    wx_image_url = fields.Char('Picture to send first', copy=False,
                               help="The bridge downloads this and sends it as a file before the text.")
    wx_confirm_link_id = fields.Many2one('sa.confirm.link', 'Confirmation link', ondelete='set null', copy=False)

    @api.model
    def _claim_outbox(self, limit=20, peek=False, bridge_id=''):
        rows = super()._claim_outbox(limit=limit, peek=peek, bridge_id=bridge_id)
        if rows:
            by_id = {r.id: r.wx_image_url or '' for r in self.sudo().browse([r['id'] for r in rows])}
            for r in rows:
                r['image_url'] = by_id.get(r['id'], '')
        return rows

    @api.model
    def _sa_page_confirm(self, link, action):
        """ACCEPT / REJECT from the page, recorded like a typed reply."""
        req, partner = link.request_id, link.partner_id
        row = self.sudo().create({
            'direction': 'in', 'state': 'received', 'partner_id': partner.id,
            'wechat_name': (partner.sa_wechat_name or '').strip(),
            'text': '[page] %s' % ('In stock / 有货' if action == 'accept' else 'No stock / 没有'),
            'request_id': req.id, 'received_at': fields.Datetime.now(),
            'wx_id': 'confirm-%s-%s' % (link.id, action),
        })
        if action == 'accept':
            return self._sa_record_yes(row, req, partner)
        return self._sa_record_no(row, req, partner)


class SaGroupRequestWeChatConfirm(models.Model):
    _inherit = 'sa.group.request'

    def _sa_ask_via_wechat(self, vendor, ask, guard, trigger):
        """After the ask row is queued: give it the link line and the picture."""
        before = self.env['sa.wechat.message'].sudo().search(
            [('request_id', '=', self.id), ('partner_id', '=', vendor.id), ('wx_step', '=', 'ask')]).ids
        result = super()._sa_ask_via_wechat(vendor, ask, guard, trigger)
        if not self._sa_confirm_settings().confirm_vendor_enabled:
            return result
        fresh = self.env['sa.wechat.message'].sudo().search(
            [('request_id', '=', self.id), ('partner_id', '=', vendor.id), ('wx_step', '=', 'ask'),
             ('id', 'not in', before), ('wx_confirm_link_id', '=', False)], order='id desc', limit=1)
        if not fresh:
            return result
        try:
            Link = self.env['sa.confirm.link'].sudo()
            link = Link.search([('request_id', '=', self.id), ('kind', '=', 'vendor'),
                                ('partner_id', '=', vendor.id), ('channel', '=', 'wechat')], limit=1)
            if not link:
                link = self._sa_confirm_new_link({'kind': 'vendor', 'channel': 'wechat', 'partner_id': vendor.id,
                                                  'wechat_name': (vendor.sa_wechat_name or '').strip()},
                                                 [('kind', '=', 'vendor'), ('partner_id', '=', vendor.id), ('channel', '=', 'wechat')])
            raw, source = self._sa_confirm_picture(fetch=True)
            link.write({'sent_on': fields.Datetime.now(), 'image_source': source})
            text = (fresh.text or '').rstrip() + "\n\n\U0001F449 Confirm / 确认:\n%s" % link._url()
            fresh.write({'text': text, 'wx_confirm_link_id': link.id,
                         'wx_image_url': link._image_url() if raw else False})
        except Exception:  # noqa: BLE001 - the plain ask still goes out
            _logger.exception("Sales Automation: WeChat confirm link for enquiry %s failed", self.id)
        return result
