# -*- coding: utf-8 -*-
"""How long the links in a WhatsApp group order's chat work (owner, 23 Nov 2026:
"after one week show as expired"): always while the order is open, a week after
it was delivered or cancelled. Website orders have no such limit, and neither
has anyone who may see the order by their own login."""
import logging
from datetime import timedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

LINK_DAYS = 7


class SaleOrderLinkExpiry(models.Model):
    _inherit = 'sale.order'

    sa_cancelled_on = fields.Datetime('Cancelled on', copy=False, readonly=True)

    def write(self, vals):
        if vals.get('state') == 'cancel' and 'sa_cancelled_on' not in vals:
            vals = dict(vals, sa_cancelled_on=fields.Datetime.now())
        return super().write(vals)

    def _sa_link_ended(self):
        """When this order was over, or False while it is open."""
        self.ensure_one()
        o = self.sudo()
        req = o._sa_group_enquiry()
        if not req or not req.group_id:
            return False
        if o.state == 'cancel':
            return o.sa_cancelled_on or o.write_date
        if o.state != 'sale':
            return False
        if req.sa_pay_link_sent_on and not o._sa_portal_status().get('paid'):
            return False                    # there is something to pay
        ends = []
        for job in o.picking_ids.filtered(lambda p: p.state != 'cancel' and p.picking_type_code == 'outgoing'):
            state = getattr(job, 'sa_delivery_state', 'none') or 'none'
            if state == 'delivered':
                ends.append(job.sa_delivered_on or job.date_done or job.write_date)
            elif state in ('returned', 'cancelled'):
                ends.append(job.write_date)
            elif state in ('none',) and job.state == 'done':
                ends.append(job.date_done or job.write_date)
            else:
                return False                # still on its way
        if ends:
            return max(ends)
        if req.sa_paid_told_on or req.sa_paid_on:
            return req.sa_paid_told_on or req.sa_paid_on
        # the flow ends at the signed order or its invoice
        if req._sa_flow_end() in ('order', 'invoice'):
            return o.signed_on or o.date_order
        return False

    def _sa_link_expired(self):
        self.ensure_one()
        ended = self._sa_link_ended()
        return bool(ended and ended < fields.Datetime.now() - timedelta(days=LINK_DAYS))


class SaAddressLinkExpiry(models.Model):
    _inherit = 'sa.address.link'

    def _result_expired(self):
        """"Address saved" is shown for a week."""
        self.ensure_one()
        return bool(self.used_on and self.used_on < fields.Datetime.now() - timedelta(days=LINK_DAYS))

    @api.model
    def _cron_links_clean(self):
        """Daily: the browser text of a form filled in over a week ago goes; who,
        when and which address stays as proof."""
        old = self.sudo().with_context(active_test=False).search(
            [('used_on', '<', fields.Datetime.now() - timedelta(days=LINK_DAYS)), ('used_ua', '!=', False)], limit=2000)
        old.write({'used_ua': False})
        return True
