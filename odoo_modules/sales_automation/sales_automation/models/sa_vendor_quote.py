"""One price, from one vendor, against one request.

A vendor group is a room full of people typing numbers. Everything that looks
like a price is captured here with the message it came from and, crucially,
*how* it was matched to a request - because the fallback rule can get that
wrong, and a wrong match means quoting the customer a price for the wrong
product. Recording `matched_by` is what makes such a mistake visible instead of
merely puzzling.

Nothing here is ever sent back to the vendor group. Vendors see their own
messages and no reply.
"""

import logging
import re

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

# A number that sits next to money: a currency symbol or code, or a word people
# actually type when quoting. Checked before falling back to "first number in
# the message", which gets "500 pcs at 120" backwards.
_PRICE_NEAR_MONEY = re.compile(
    r'(?:'
    r'(?:[$£€₹¥]|rs\.?|inr|aed|usd|sar|qar|kwd|omr|bhd|dhs?|rupees?)'
    r'\s*([0-9][0-9,]*(?:\.[0-9]+)?)'
    r'|'
    r'([0-9][0-9,]*(?:\.[0-9]+)?)\s*'
    r'(?:[$£€₹¥]|rs\.?|inr|aed|usd|sar|qar|kwd|omr|bhd|dhs?|rupees?|only|each|/-|per\s+\w+)'
    r')',
    re.IGNORECASE,
)
_PRICE_AFTER_WORD = re.compile(
    r'(?:price|rate|cost|quote|offer|best|final|net)\s*'
    r'(?:is|:|=|-)?\s*'
    r'([0-9][0-9,]*(?:\.[0-9]+)?)',
    re.IGNORECASE,
)
# "3 days", "2-3 days", "1 week", "ready stock". A vendor almost never
# answers with a bare price - the time is the other half of the deal, and a
# customer who is told 18.00 with no date will ask anyway.
# The second number of a range only counts when a dash or "to" joins it.
# Without that the optional group swallowed any preceding number, so the
# reply our own template asks for - "#64 450 3 days" - was read as a
# 450-day delivery, leaving 3 as the price.
_DELAY_DAYS = re.compile(
    r'(\d+)(?:\s*(?:-|to|\u2013)\s*(\d+))?\s*'
    r'(day|days|working\s*day|working\s*days|din)\b', re.IGNORECASE)
_DELAY_WEEKS = re.compile(
    r'(\d+)(?:\s*(?:-|to|\u2013)\s*(\d+))?\s*(week|weeks)\b', re.IGNORECASE)
# A wait, not a price: "15 min", "wait 30 minutes", "2 hrs". On 31 Oct a
# vendor's "15 min" went to the counter as a 15.00 quote. Only ignored by
# the price reader - it is no delivery time either.
_WAIT_TIME = re.compile(
    r'(\d+)(?:\s*(?:-|to|–)\s*(\d+))?\s*'
    r'(min|mins|minute|minutes|hr|hrs|hour|hours|sec|secs|seconds)\b', re.IGNORECASE)
_DELAY_WORDS = (
    (re.compile(r'\b(ready\s*stock|in\s*stock|available\s*now|today)\b',
                re.IGNORECASE), 0),
    (re.compile(r'\b(tomorrow|next\s*day|1\s*day)\b', re.IGNORECASE), 1),
)

# Quantities and pack sizes, so they are not mistaken for the price.
_QUANTITY_CONTEXT = re.compile(
    r'([0-9][0-9,]*(?:\.[0-9]+)?)\s*'
    r'(?:pcs?|pieces?|nos?|units?|qty|kg|kgs|gram|g|ltr|l|box|boxes|ctn|cartons?|packs?)',
    re.IGNORECASE,
)


class SaVendorQuote(models.Model):
    _name = 'sa.vendor.quote'
    _description = 'Vendor Price Quote'
    _order = 'request_id, price, id'
    _rec_name = 'display_name_custom'

    request_id = fields.Many2one(
        'sa.group.request', string='Enquiry',
        required=True, ondelete='cascade', index=True,
    )
    group_id = fields.Many2one(
        'sa.sales.group', string='Vendor Group',
        ondelete='cascade', index=True,
        help="Only set for quotes from the old vendor-group flow. Vendors are "
             "messaged privately now, so this is empty.",
    )
    message_id = fields.Many2one(
        'whatsapp.message', string='Message', ondelete='set null',
    )

    vendor_phone = fields.Char('Vendor', index=True)
    vendor_name = fields.Char('Vendor Name')
    partner_id = fields.Many2one('res.partner', string='Contact')

    price = fields.Monetary('Price', currency_field='currency_id', required=True)
    currency_id = fields.Many2one(
        'res.currency', string='Currency',
        default=lambda self: self.env.company.currency_id,
    )
    raw_text = fields.Text(
        'Message Text', readonly=True,
        help="What the vendor actually typed. Kept so a mis-read price can be "
             "seen and corrected rather than quietly quoted on.",
    )
    matched_by = fields.Selection([
        ('direct', 'Private Reply'),
        ('reply_quote', 'Replied to Our Message'),
        ('newest_open', 'Newest Open Request'),
        ('manual', 'Set by Hand'),
    ], string='Matched By', required=True, default='direct', index=True,
        help="How this price was tied to an enquiry. 'Newest Open Request' is "
             "a guess - the vendor did not reply to our message - so it is "
             "worth checking when a quote looks wrong.",
    )
    delay_days = fields.Integer(
        'Delivery (days)',
        help="How long this vendor said it would take. 0 means ready stock.",
    )
    response_minutes = fields.Integer(
        'Replied After (min)', readonly=True,
        help="How long this vendor took to answer the price check. With ten "
             "vendors in a group and one prompt reply, this is what shows "
             "whether the window is set anywhere near right.",
    )
    is_best = fields.Boolean(
        'Winning Quote', index=True,
        help="The cheapest price when the window closed; the one the customer "
             "was quoted from.",
    )

    product_id = fields.Many2one(
        related='request_id.product_id', store=True, string='Product',
    )
    display_name_custom = fields.Char(compute='_compute_display_name_custom')

    def _compute_display_name_custom(self):
        for rec in self:
            rec.display_name_custom = '%s: %.2f' % (
                rec.vendor_name or rec.vendor_phone or 'Vendor', rec.price)

    # ----------------------------------------------------------
    # Parsing
    # ----------------------------------------------------------
    @api.model
    def _parse_vendor_price(self, text):
        """The price a vendor meant, or None.

        The tracker's `_parse_price` takes the first number in the message,
        which reads "500 pcs at 120" as 500 - an order of magnitude wrong, and
        wrong in the direction that loses money. So money-shaped numbers are
        preferred: next to a currency, after the word "price", or simply the
        only number once quantities are discounted.
        """
        if not text:
            return None
        text = self._strip_reference(text).strip()

        for pattern in (_PRICE_NEAR_MONEY, _PRICE_AFTER_WORD):
            match = pattern.search(text)
            if match:
                value = next((g for g in match.groups() if g), None)
                price = self._to_float(value)
                if price:
                    return price

        # Nothing money-shaped. Discount the numbers that are plainly not the
        # price - pack sizes, and the delivery time. "15, 3 days" is the most
        # natural thing a vendor types, and counting the 3 as a candidate left
        # two numbers, no majority, and so no price at all.
        # One capture group, so findall gives strings here - m[0] would take
        # the first digit of '500' and leave the pack size counting as a
        # price candidate. The delay patterns have two groups and do give
        # tuples, hence the different handling below.
        ignore = {self._to_float(m) for m in _QUANTITY_CONTEXT.findall(text)}
        for pattern in (_DELAY_DAYS, _DELAY_WEEKS, _WAIT_TIME):
            for found in pattern.findall(text):
                # Every number the delay matched, both ends of "3-5 days".
                # Taking only the first left the 5 looking like a second price
                # candidate, so "450 3-5 days" had no majority and no quote.
                parts = found if isinstance(found, tuple) else (found,)
                for part in parts:
                    value = self._to_float(part)
                    if value is not None:
                        ignore.add(value)
        numbers = [self._to_float(n) for n in
                   re.findall(r'[0-9][0-9,]*(?:\.[0-9]+)?', text)]
        candidates = [n for n in numbers if n and n not in ignore]
        if len(candidates) == 1:
            return candidates[0]

        # Several bare numbers and no clue which is the price. Guessing here is
        # how a pack size becomes a quote, so decline and let it be ignored.
        if candidates:
            _logger.info("Sales Automation: ambiguous vendor price in %r "
                         "(candidates %s) - ignored.", text[:80], candidates)
        return None

    @api.model
    @api.model
    def _strip_reference(self, text):
        """Remove the enquiry code, so it is not counted as a price.

        The code is base 36 of the enquiry id, so ids in certain ranges give
        purely numeric codes - 60, 61, 64. Once one of those is in the message
        the reply "#64 1000" holds two numbers, neither obviously the price,
        and the whole quote was discarded as ambiguous. The code has done its
        job by the time the price is read.
        """
        import re as _re
        return _re.sub(r'#\s*[0-9A-Za-z]{1,6}', ' ', text or '')

    def _parse_delay(self, text):
        """Days the vendor quoted, or None when they did not say.

        None and 0 mean different things here: 0 is "ready stock", None is "no
        date given", and only the second one should leave the customer without
        a timeframe.
        """
        if not text:
            return None
        weeks = _DELAY_WEEKS.search(text)
        if weeks:
            value = self._to_float(weeks.group(1))
            if value is not None:
                return int(value * 7)
        days = _DELAY_DAYS.search(text)
        if days:
            value = self._to_float(days.group(1))
            if value is not None and 0 <= value <= 365:
                return int(value)
        for pattern, value in _DELAY_WORDS:
            if pattern.search(text):
                return value
        return None

    @api.model
    def _to_float(self, value):
        try:
            return float(str(value).replace(',', ''))
        except (TypeError, ValueError):
            return None

    # ----------------------------------------------------------
    # Capture
    # ----------------------------------------------------------
    @api.model
    def _capture(self, message, group):
        """Read one vendor-group message as a price. Returns the quote or False."""
        price = self._parse_vendor_price(message.message)
        if not price:
            return False

        request, matched_by = self.env['sa.group.request']._match_vendor_reply(
            message, group)
        if not request:
            _logger.info("Sales Automation: price %.2f in %s matched no open "
                         "request - ignored.", price, group.name)
            return False

        quote = self.sudo().create({
            'request_id': request.id,
            'group_id': group.id,
            'message_id': message.id,
            'vendor_phone': message.participant_phone or '',
            'vendor_name': message.push_name or '',
            'partner_id': self._find_partner(message.participant_phone),
            'price': price,
            'currency_id': request.currency_id.id,
            'raw_text': message.message,
            'delay_days': self._parse_delay(message.message) or 0,
            'response_minutes': request._minutes_since_broadcast(),
            'matched_by': matched_by,
        })
        _logger.info("Sales Automation: quote %.2f from %s on enquiry %s (%s)",
                     price, quote.vendor_name or quote.vendor_phone,
                     request.id, matched_by)
        return quote

    @api.model
    def _capture_direct(self, message, request):
        """One vendor's private answer to one price check."""
        # Drop the code the reply was matched on, hash or no hash: "64 1000"
        # is as ambiguous as "#64 1000" once both numbers are candidates.
        text = message.message or ''
        if request.ref_code:
            import re as _re
            text = _re.sub(r'(?<![0-9A-Za-z])#?%s(?![0-9A-Za-z])'
                           % _re.escape(request.ref_code), ' ', text,
                           flags=_re.IGNORECASE)
        price = self._parse_vendor_price(text)
        if not price:
            return False
        partner = request.sourcing_vendor_ids.filtered(
            lambda v: (v.phone or '').replace(' ', '').endswith(
                (message.participant_phone or '')[-9:]))[:1]
        quote = self.sudo().create({
            'request_id': request.id,
            'message_id': message.id,
            'vendor_phone': message.participant_phone or '',
            'vendor_name': partner.name or message.push_name or '',
            'partner_id': partner.id or self._find_partner(
                message.participant_phone),
            'price': price,
            'currency_id': request.currency_id.id,
            'raw_text': message.message,
            'delay_days': self._parse_delay(text) or 0,
            'response_minutes': request._minutes_since_broadcast(),
            'matched_by': 'direct',
        })
        _logger.info("Sales Automation: quote %.2f from %s on enquiry %s "
                     "(private reply)", price,
                     quote.vendor_name or quote.vendor_phone, request.id)
        return quote

    @api.model
    def _find_partner(self, phone):
        """Best-effort vendor contact, matched the way the tracker matches."""
        digits = ''.join(c for c in (phone or '') if c.isdigit())
        if len(digits) < 8:
            return False
        partner = self.env['res.partner'].sudo().search(
            [('phone_sanitized', 'like', digits[-9:])], limit=1)
        return partner.id or False

    def action_make_best(self):
        """Override the winner by hand when the automatic pick was wrong."""
        self.ensure_one()
        self.request_id._apply_winning_quote(self)
        return True
