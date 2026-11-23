# -*- coding: utf-8 -*-
"""The customer does not wait for a vendor window nobody is left in (owner,
23 Nov 2026): once every vendor asked has given a price or said no, it closes.
One who has not answered is waited for, as before - a cheaper price still counts."""
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class SaGroupRequestAllIn(models.Model):
    _inherit = 'sa.group.request'

    def _sa_close_soon(self):
        """The closing job runs now instead of at its next minute."""
        cron = self.env.ref('sales_automation.cron_sa_close_sourcing', raise_if_not_found=False)
        if cron:
            cron.sudo()._trigger()

    def _sa_all_answered(self):
        self.ensure_one()
        vendors = self.sourcing_vendor_ids
        # posted in a vendor group: who is still typing there cannot be known
        if not vendors or self.sourcing_group_id:
            return False
        held = {h.get('partner') for h in self._sa_held().values()}
        answered = self.quote_ids.partner_id | self.sa_vendor_no_ids
        return all(v in answered or v.id in held for v in vendors)

    def _sa_close_if_all_answered(self):
        for req in self.sudo():
            if req.state != 'sourcing' or req.sa_price_stalled or req.sa_price_choice_pending \
                    or not req.sourcing_deadline or not req._sa_all_answered():
                continue
            now = fields.Datetime.now()
            if req.sourcing_deadline > now:
                req.write({'sourcing_deadline': now})
                _logger.info("Sales Automation: every vendor answered enquiry %s - closing now", req.id)
            req._sa_close_soon()

    def write(self, vals):
        res = super().write(vals)
        if 'sa_vendor_no_ids' in vals:
            self._sa_close_if_all_answered()
        return res

    def _sa_hold_price(self, *args, **kw):
        res = super()._sa_hold_price(*args, **kw)
        self._sa_close_if_all_answered()
        return res

    def _sa_vendor_price_in(self, quote):
        res = super()._sa_vendor_price_in(quote)
        if quote and self.sa_price_stalled:
            self._sa_close_soon()
        return res


class SaVendorQuoteAllIn(models.Model):
    _inherit = 'sa.vendor.quote'

    @api.model_create_multi
    def create(self, vals_list):
        quotes = super().create(vals_list)
        quotes.filtered(lambda q: q.matched_by != 'manual').request_id._sa_close_if_all_answered()
        return quotes
