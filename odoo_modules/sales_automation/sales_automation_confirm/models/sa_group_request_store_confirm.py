# -*- coding: utf-8 -*-
"""The desk's detail panel: who got a link, who opened it, who pressed what."""
from odoo import api, fields, models


def _iso(dt):
    return (dt.isoformat() + 'Z') if dt else ''


class SaGroupRequestStoreConfirm(models.Model):
    _inherit = 'sa.group.request'

    @api.model
    def sa_enquiry_detail(self, request_id):
        detail = super().sa_enquiry_detail(request_id)
        Link = self.env['sa.confirm.link'].sudo()
        rows = []
        for link in Link.search([('request_id', '=', int(request_id))], order='id'):
            clicks = [{'action': c.action, 'at': _iso(c.at),
                       'ip': c.ip or '', 'browser': (c.user_agent or '')[:80]}
                      for c in link.click_ids.sorted('id')]
            rows.append({
                'id': link.id, 'kind': link.kind, 'channel': link.channel, 'who': link.identity or '',
                'sent': _iso(link.sent_on),
                'opened': _iso(link.opened_on),
                'opens': link.open_count, 'decided': link.decided or '',
                'decided_on': _iso(link.decided_on),
                'ip': link.decided_ip or '', 'picture': link.image_source or 'none', 'clicks': clicks,
            })
        detail['confirmations'] = rows
        return detail
