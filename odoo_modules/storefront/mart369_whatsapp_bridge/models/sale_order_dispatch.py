"""A website order becomes a real rider-app job, with the right numbers.

The delivery stack already makes a job for every confirmed order - including
the website's. Three of its fields come out wrong for a website order, and
each wrong one costs money or trust:

* **kind** came from the stack's own promise rules, not from what the
  customer chose at checkout (Quick / Express);
* **cash to collect** read `order.transaction_ids`, but the website links its
  payments through the invoice - so a *prepaid* order told the rider to
  collect the whole total at the door;
* **the door code** was the stack's own, while the customer's app showed the
  website's - two codes for one doorstep, and the rider holds the wrong one.

Fixed here, right after the job is made, and nowhere else.
"""

from odoo import models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _sa_dispatch_deliveries(self):
        result = super()._sa_dispatch_deliveries()
        for order in self.filtered('mart369_ref'):
            jobs = order.picking_ids.filtered(
                lambda p: p.picking_type_id.code == 'outgoing'
                and p.sa_delivery_state not in (False, 'none')
                and p.state not in ('done', 'cancel'))
            if not jobs:
                continue
            cod = sum(
                tx.amount for tx in order.sudo()._mart369_transactions()
                if tx.provider_id.mart369_is_cod
                and tx.state in ('draft', 'pending'))
            jobs.sudo().write({
                'sa_delivery_kind': ('express' if order.mart369_mode == 'all'
                                     else 'quick'),
                'sa_cod_amount': cod,
                'sa_last_delivery_code': order.sudo().mart369_otp_code or False,
            })
        return result

    def _mart369_issue_otp(self):
        """The website's code is the job's code, always - a retry included."""
        code = super()._mart369_issue_otp()
        if self.mart369_ref:
            job = self._mart369_bridge_job()
            if job:
                job.sudo().sa_last_delivery_code = code
        return code
