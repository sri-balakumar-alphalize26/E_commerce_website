import logging
from datetime import timedelta

from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)

# How many BROADCAST messages to send per cron run. With the cron running every
# minute this is the send pace (~20/min ≈ 1,200/hr) — slow enough to avoid the
# unofficial (Baileys) WhatsApp number getting banned for bursting.
BROADCAST_BATCH_PER_RUN = 20
# Transactional (welcome/purchase) messages are prompt but still capped so a bulk
# card generation (hundreds at once) spreads over runs instead of bursting.
TRANS_BATCH_PER_RUN = 40


class WhatsappSendQueue(models.Model):
    """Deferred, throttled outbox for ALL WhatsApp sending.

    POS never sends inline — it drops a row here (instant) and the cron drains
    the queue off-request. This keeps POS fast (new-card welcome + purchase
    notifications) and provides the throttled fan-out for bulk broadcasts.
    """
    _name = 'whatsapp.send.queue'
    _description = 'WhatsApp Deferred Send Queue'
    _order = 'priority desc, scheduled_at asc, id asc'

    send_type = fields.Selection([
        ('welcome', 'New Card Welcome'),
        ('purchase', 'Purchase Notification'),
        ('broadcast', 'Broadcast / Offer'),
    ], required=True, index=True)
    campaign_id = fields.Many2one('whatsapp.campaign', string='Campaign',
                                  ondelete='cascade', index=True)
    res_model = fields.Char(string='Source Model')
    res_id = fields.Integer(string='Source Record')
    phone = fields.Char(string='Phone')
    partner_name = fields.Char(string='Recipient Name')
    scheduled_at = fields.Datetime(string='Scheduled', index=True,
                                   default=fields.Datetime.now)
    # Higher runs first. Transactional (welcome/purchase) beats broadcast so a
    # single welcome never waits behind a 1,000-recipient campaign.
    priority = fields.Integer(default=10, index=True)
    state = fields.Selection([
        ('pending', 'Pending'),
        ('sent', 'Sent'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ], default='pending', required=True, index=True)
    attempts = fields.Integer(default=0)
    max_attempts = fields.Integer(default=3)
    error = fields.Char(string='Last Error')
    sent_date = fields.Datetime(string='Sent On')
    company_id = fields.Many2one('res.company', default=lambda s: s.env.company)

    # ------------------------------------------------------------------
    # Enqueue (called from POS-facing create/order paths — must be fast)
    # ------------------------------------------------------------------
    @api.model
    def _enqueue(self, send_type, record, delay_seconds=30, campaign=None,
                 phone=None, partner_name=None, priority=None):
        """Queue one deferred send. Returns the created queue row.

        This is a plain INSERT (no network), so callers stay fast. `record` is
        the source record (pos.loyalty.card for welcome, pos.order for purchase,
        pos.loyalty.card for a broadcast recipient)."""
        if priority is None:
            # welcome outranks purchase so a brand-new customer gets their card
            # (image + message + PDF) BEFORE the first order's receipt; broadcast
            # is lowest so bulk offers never delay a welcome or receipt.
            priority = {
                'welcome': 110,
                'purchase': 100,
                'broadcast': 10,
            }.get(send_type, 100)
        vals = {
            'send_type': send_type,
            'campaign_id': campaign.id if campaign else False,
            'res_model': record._name if record else False,
            'res_id': record.id if record else False,
            'phone': phone or (getattr(record, 'phone', False) if record else False),
            'partner_name': partner_name or (getattr(record, 'name', False) if record else False),
            'scheduled_at': fields.Datetime.now() + timedelta(seconds=delay_seconds),
            'priority': priority,
        }
        return self.sudo().create(vals)

    # ------------------------------------------------------------------
    # Cron worker — drains the queue with throttling
    # ------------------------------------------------------------------
    @api.model
    def _cron_process_queue(self):
        now = fields.Datetime.now()
        base = [('state', '=', 'pending'), ('scheduled_at', '<=', now)]

        # Transactional first (prompt, lightly capped) so welcomes/receipts go out fast.
        trans = self.sudo().search(
            base + [('send_type', 'in', ('welcome', 'purchase'))],
            limit=TRANS_BATCH_PER_RUN)
        for row in trans:
            row._process_one()

        # Broadcast next, throttled to the per-run cap (= the send pace).
        bcast = self.sudo().search(
            base + [('send_type', '=', 'broadcast')], limit=BROADCAST_BATCH_PER_RUN)
        for row in bcast:
            row._process_one()

        # Mark campaigns whose rows are all resolved as done.
        campaigns = (trans | bcast).mapped('campaign_id')
        for camp in campaigns:
            camp._refresh_state()
        return True

    def _process_one(self):
        self.ensure_one()
        try:
            ok, err = self._dispatch()
        except Exception as e:  # never let one row kill the batch
            ok, err = False, str(e)
            _logger.exception('WA QUEUE: dispatch crashed for row %s', self.id)
        now = fields.Datetime.now()
        if ok:
            self.write({'state': 'sent', 'sent_date': now, 'error': False})
        else:
            attempts = self.attempts + 1
            if attempts >= self.max_attempts:
                self.write({'state': 'failed', 'attempts': attempts,
                            'error': (err or 'send failed')[:500]})
            else:
                # back off and retry on a later run
                self.write({'attempts': attempts, 'error': (err or 'send failed')[:500],
                            'scheduled_at': now + timedelta(minutes=5)})

    def _dispatch(self):
        """Return (ok, error_message). Runs off-request in the cron."""
        self.ensure_one()
        env = self.env
        if self.send_type == 'welcome':
            card = env['pos.loyalty.card'].sudo().browse(self.res_id).exists()
            if not card:
                return True, ''  # card gone, nothing to do
            env['pos.loyalty.whatsapp.service'].sudo().send_new_card_welcome(card.id)
            try:
                if card.state == 'active':
                    card._maybe_email_card()
            except Exception as e:
                _logger.warning('WA QUEUE: welcome email failed for %s: %s', card.card_number, e)
            return True, ''

        if self.send_type == 'purchase':
            order = env['pos.order'].sudo().browse(self.res_id).exists()
            if not order:
                return True, ''
            env['pos.order'].sudo()._send_whatsapp_notification(order.id)
            return True, ''

        if self.send_type == 'broadcast':
            camp = self.campaign_id
            if not camp:
                return False, 'no campaign'
            svc = env['pos.loyalty.whatsapp.service'].sudo()
            msg = camp.render_message(self.partner_name)
            ok = svc._send_text(self.phone, msg)
            if ok and camp.attachment:
                # Binary fields return bytes; the send helpers expect a base64 str.
                att = camp.attachment
                if isinstance(att, bytes):
                    att = att.decode()
                if (camp.attachment_mimetype or '').startswith('image/'):
                    svc._send_image(self.phone, att, caption='')
                else:
                    svc._send_document(self.phone, att,
                                       camp.attachment_name or 'file',
                                       caption='',
                                       mimetype=camp.attachment_mimetype or 'application/pdf')
            return (bool(ok), '' if ok else 'send_text returned False')

        return False, 'unknown send_type'
