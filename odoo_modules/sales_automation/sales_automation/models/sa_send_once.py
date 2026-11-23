# -*- coding: utf-8 -*-
"""A repeated request gives the customer the same code and links again
(whatsapp_gateway/models/send_memo.py, 23 Nov 2026)."""
import uuid

from odoo import api, models
from odoo.addons.whatsapp_gateway.models import send_memo


class SaGroupRequestSendOnce(models.Model):
    _inherit = 'sa.group.request'

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        memo = send_memo.current(self.env)
        if memo is not None:
            for record in records:
                code = memo.value('ref', lambda r=record: r.ref_code)
                if code and record.ref_code != code:
                    record.sudo().ref_code = code
        return records


class SaleOrderSendOnce(models.Model):
    _inherit = 'sale.order'

    def _portal_ensure_token(self):
        memo = send_memo.current(self.env)
        if memo is not None and not self.access_token:
            self.sudo().write({'access_token': memo.value('order token', lambda: str(uuid.uuid4()))})
        return super()._portal_ensure_token()
