# -*- coding: utf-8 -*-
"""The counter screen learns about WeChat: relay rows in the queue payload
and a channel mark on every vendor it lists."""
from odoo import api, models


class SaGroupRequestStoreWeChat(models.Model):
    _inherit = 'sa.group.request'

    @api.model
    def sa_enquiry_queue(self):
        data = super().sa_enquiry_queue()
        try:
            data['wechat'] = self.env['sa.wechat.message'].sa_wechat_relay_rows()
        except Exception:  # noqa: BLE001 - the desk must never break over this
            data['wechat'] = {'enabled': False, 'alive': False, 'manual_on': False, 'rows': []}
        for row in data.get('rows', []) or []:
            for v in row.get('vendors', []) or []:
                pid = v.get('id')
                if pid:
                    p = self.env['res.partner'].sudo().browse(pid)
                    v['channel'] = p.sa_channel or 'none'
                    v['wechat_name'] = p.sa_wechat_name or ''
        return data
