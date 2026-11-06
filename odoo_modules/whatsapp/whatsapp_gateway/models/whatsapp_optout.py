"""Numbers that must never be messaged again.

Keyed by phone rather than by partner on purpose: an opt-out arrives as an
inbound "STOP" from a number, and that number may belong to no contact, to a
contact recorded under a different number, or to contacts in several tenants.
The number is the only thing we reliably have.

Because one WhatsApp number serves every tenant, an opt-out is global. That is
not a simplification - it is what the recipient actually did. They blocked
NEXGENN's number, and there is no per-tenant way to honour that.
"""

import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

# What a recipient might send to mean "stop". Matched against the whole message
# once trimmed, never as a substring: "please don't stop sending these" must
# not opt anybody out.
STOP_WORDS = {
    'stop', 'unsubscribe', 'opt out', 'optout', 'remove me', 'no more',
    'إيقاف', 'الغاء', 'إلغاء',
}


class WhatsAppOptOut(models.Model):
    _name = 'whatsapp.optout'
    _description = 'WhatsApp Opt-Out'
    _order = 'create_date desc'
    _rec_name = 'phone'
    _sql_constraints = [
        ('phone_uniq', 'unique(phone)', 'This number is already opted out.'),
    ]

    phone = fields.Char('Phone Number', required=True, index=True)
    reason = fields.Char('Reason')
    source = fields.Selection([
        ('inbound', 'Replied STOP'),
        ('manual', 'Added by hand'),
    ], string='Source', default='manual', required=True)
    partner_id = fields.Many2one('res.partner', string='Contact')
    active = fields.Boolean(
        default=True,
        help='Archive to let this number be messaged again - only after the '
             'person has asked for that.',
    )

    @api.model
    def _clean(self, phone):
        if not phone:
            return ''
        for ch in ('+', ' ', '-', '(', ')'):
            phone = phone.replace(ch, '')
        return phone.split('@')[0].strip()

    @api.model
    def is_opted_out(self, phone):
        cleaned = self._clean(phone)
        if not cleaned:
            return False
        return bool(self.sudo().search_count([('phone', '=', cleaned)]))

    @api.model
    def is_stop_word(self, message):
        """Did this inbound message ask us to stop?"""
        text = (message or '').strip().lower().rstrip('.!')
        return bool(text) and text in STOP_WORDS

    @api.model
    def record(self, phone, reason='', source='inbound', partner=None):
        """Opt a number out. Safe to call for a number already opted out."""
        cleaned = self._clean(phone)
        if not cleaned:
            return self.browse()
        existing = self.sudo().with_context(active_test=False).search(
            [('phone', '=', cleaned)], limit=1)
        if existing:
            if not existing.active:
                existing.active = True
            return existing
        _logger.info("WhatsApp: %s opted out (%s).", cleaned, source)
        return self.sudo().create({
            'phone': cleaned,
            'reason': reason or _("Replied with a stop word"),
            'source': source,
            'partner_id': partner.id if partner else False,
        })
