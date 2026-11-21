"""Which AI answers "is this a product enquiry?", and with what key.

The tracker already holds API keys for the same three providers on
`wa.voice.config`, so those are reused by default and nobody types a key
twice. What is *not* reused is the model name: `wa.voice.config` stores
transcription models - whisper-large-v3 cannot classify text - so a chat model
is named here.

Nothing in this module touches `wa.voice.config.action_save_config` or
`action_test_connection`. Both write to or exec paths that do not exist on this
machine (`D:\\odoo-packages\\...`, and a python.exe under an Odoo build number
that is two releases old). Reading the stored fields sidesteps all of it.
"""

import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

DEFAULT_CHAT_MODEL = {
    # Not the newest: gemini-3.7-flash and gemini-flash-latest both answered
    # 503 "high demand", and 3.6-flash worked but took 22.9s - over the 20s
    # default timeout, so it would fail and drop to catalog matching. 3.5-flash
    # returned the same verdict in 3.0s. gemini-2.5-flash now 404s for new keys.
    'gemini': 'gemini-3.5-flash',
    'groq': 'llama-3.3-70b-versatile',
    'openai': 'gpt-4o-mini',
    # SinoRouter is a router, so the catalog is whatever the account is
    # entitled to. This is only a starting point - set Chat Model to a name
    # the account actually serves. A wrong name is not fatal: the call fails,
    # a warning is logged and catalog matching answers instead.
    'sinorouter': 'deepseek-chat',
}

# Chat-completions endpoint per provider. Every one of these except Gemini
# speaks the OpenAI wire format, so they share a single caller.
DEFAULT_BASE_URL = {
    'groq': 'https://api.groq.com/openai/v1/chat/completions',
    'openai': 'https://api.openai.com/v1/chat/completions',
    'sinorouter': 'https://api.sinorouter.ai/v1/chat/completions',
}


class SaAiSettings(models.Model):
    _name = 'sa.ai.settings'
    _description = 'Sales Automation AI Settings'
    _rec_name = 'provider'

    provider = fields.Selection([
        ('gemini', 'Google Gemini'),
        ('groq', 'Groq'),
        ('openai', 'OpenAI'),
        ('sinorouter', 'SinoRouter'),
    ], string='Provider', default='gemini', required=True)
    model_name = fields.Char(
        'Chat Model',
        help="A text model, not a transcription one. Leave empty for the "
             "provider's default: %s." % ', '.join(
                 '%s -> %s' % (k, v) for k, v in DEFAULT_CHAT_MODEL.items()),
    )
    api_key = fields.Char(
        'API Key',
        help="Leave empty to reuse the key already saved for this provider "
             "under WA Tracker > AI / Voice Settings.",
    )
    api_base_url = fields.Char(
        'Base URL',
        help="Full chat-completions endpoint. Leave empty to use the "
             "provider's standard URL. Set it when the provider is reached "
             "through a proxy or serves a non-standard path - a router's exact "
             "path can then be corrected here without touching code.",
    )
    timeout_seconds = fields.Integer('Timeout (s)', default=20)

    # ---- Vendor sourcing ----
    # One setting rather than one per group. These were on the vendor group,
    # and vendor groups are gone - vendors are contacts on a product category
    # now, so there is no per-group row left to hang them on. They are the same
    # two numbers for the whole business anyway.
    customer_reply_minutes = fields.Integer(
        'Customer Must Reply Within (minutes)', default=0,
        help="How long the customer gets to answer a question before the "
             "enquiry is closed.\n\n"
             "The remaining time is printed in the question itself, and the "
             "clock restarts every time we send them anything - so a customer "
             "who is answering never runs out.\n\n"
             "Zero is off, which is what this did before: only the 24-hour "
             "sweep closes an abandoned enquiry, and nothing tells the "
             "customer.\n\n"
             "Keep it generous. A customer reading WhatsApp between jobs is "
             "normal, and a closed enquiry means their tap on ACCEPT lands "
             "on nothing.")
    sourcing_window_minutes = fields.Integer(
        'Reply Window (minutes)', default=10,
        help="How long to wait for vendor prices before quoting the customer "
             "the cheapest one. Too short and you lose the better price that "
             "was still coming; too long and the customer gives up.",
    )
    shop_picks_vendors = fields.Boolean(
        'Shop Chooses the Vendors', default=False,
        help="Hold an out-of-stock enquiry at the shop counter so a person "
             "can choose which suppliers to ask, instead of messaging every "
             "vendor automatically.\n\n"
             "Left off, nothing changes.",
    )
    shop_pick_window_minutes = fields.Integer(
        'Shop Must Choose Within (minutes)', default=5,
        help="With nobody at the counter this long, every candidate vendor "
             "is asked automatically - so an unattended shop still answers "
             "the customer.",
    )
    shop_pick_customer_text = fields.Text(
        'Message While the Shop Decides',
        default="Let me check that for you \u23F3\n\n*{product}*\n\n"
                "Our shopkeeper is checking this and will come back to you "
                "shortly.\n\n_Ref {ref}_",
        help="Placeholders: {product}, {ref}, {customer}, {shop}.\n\n"
             "Keep {product} or {ref} in it. WhatsApp suppresses a message "
             "identical to one sent to the same chat minutes earlier, so a "
             "message with nothing varying in it arrives as silence.",
    )
    price_escalation_phone = fields.Char(
        'Tell This Number When No Vendor Replies',
        help="A WhatsApp number that is told when a price check comes back "
             "empty, with a link to type the price in. Usually the shop "
             "counter.\n\n"
             "Left blank, the enquiry still waits on the Enquiries screen - "
             "only the message is skipped.",
    )
    price_approval_enabled = fields.Boolean(
        'Shop Approves When the Vendor Price Differs', default=True,
        help="A product that already has a sale price: when the vendor's "
             "quote plus margin differs from that price, the customer is not "
             "quoted until somebody on the Enquiries screen picks the page "
             "price, the vendor price or types another.")
    price_approval_tolerance_percent = fields.Float(
        'Ignore Differences Under (%)', default=0.0,
        help="0 = any difference asks the shop. 5 = a vendor-based price "
             "within 5%% of the page price is quoted without asking.")
    unlisted_vendor_ids = fields.Many2many(
        'res.partner', 'sa_settings_unlisted_vendor_rel',
        'settings_id', 'partner_id', string='Vendors for Unlisted Products',
        domain="[('supplier_rank', '>', 0)]",
        help="Who to ask when a customer wants something that is not in the "
             "catalog at all - there is no category to route by, so this is "
             "the list.\n\n"
             "Left empty, the vendors named on any product category are used "
             "instead, capped at 20. Never every contact in the database.",
    )
    new_product_category_id = fields.Many2one(
        'product.category', string='Category for New Products',
        help="Where a product created from an enquiry is filed. Leave empty "
             "to use 369ai's default category.",
    )
    margin_percent = fields.Float(
        'Margin (%)', default=20.0,
        help="Added to what the goods cost - the cheapest vendor reply, or the "
             "vendor price list when nobody answers: "
             "quoted = cost x (1 + margin / 100).",
    )
    # Bargaining lives beside the margin because it is the margin it spends.
    # It was per-group, which meant the same three numbers copied into every
    # customer group and no single place to answer "how far can the price
    # actually fall?".
    bargain_enabled = fields.Boolean(
        'Allow Bargaining', default=True,
        help="Let the customer negotiate in the group after being quoted. "
             "Off, the quoted price is final and only ACCEPT or CANCEL is "
             "understood.",
    )
    bargain_step_percent = fields.Float(
        'Reduction per Step (%)', default=5.0,
        help="How much comes off each time the customer pushes back. Taken "
             "off the price first quoted, so two steps of 5% is 10% off "
             "that - not 5% off 5% off.",
    )
    bargain_max_steps = fields.Integer(
        'Bargaining Steps', default=2,
        help="How many times the price may come down before the assistant "
             "says it is final.",
    )
    min_margin_percent = fields.Float(
        'Lowest Margin (%)', default=5.0,
        help="How far the margin may be given away. The price never goes "
             "below cost x (1 + this / 100), whatever the customer offers "
             "and however many steps are left.",
    )
    bargain_hint = fields.Char(
        'Room to Bargain', compute='_compute_bargain_hint',
        help="What the two margins above work out to in practice.",
    )

    @api.depends('margin_percent', 'min_margin_percent', 'bargain_enabled',
                 'bargain_max_steps', 'bargain_step_percent')
    def _compute_bargain_hint(self):
        """Say in money terms what the percentages mean.

        Two margins and a step size are three numbers nobody holds in their
        head at once. Showing the resulting discount is what makes it obvious
        that a 20% margin with a 5% floor is only 12.5% of room - and that
        three steps of 5% cannot reach it.
        """
        for record in self:
            top = 1.0 + (record.margin_percent or 0.0) / 100.0
            bottom = 1.0 + (record.min_margin_percent or 0.0) / 100.0
            if not record.bargain_enabled:
                record.bargain_hint = _("Bargaining is off - the quoted price "
                                        "is final.")
                continue
            if bottom >= top:
                record.bargain_hint = _(
                    "The lowest margin is not below the margin, so there is "
                    "no room to bargain at all.")
                continue
            room = (1.0 - bottom / top) * 100.0
            steps = ((record.bargain_max_steps or 0)
                     * (record.bargain_step_percent or 0.0))
            reachable = min(room, steps)
            record.bargain_hint = _(
                "On a 100.00 quote the price can fall to %(floor).2f "
                "(%(room).1f%% off at most). %(steps)s of %(step).1f%% "
                "reach %(reach).2f.",
                floor=100.0 - room, room=room,
                steps=record.bargain_max_steps or 0,
                step=record.bargain_step_percent or 0.0,
                reach=100.0 - reachable)

    # Postcodes are national. This database alone runs an Omani company
    # beside Indian ones - three digits against six - and customers write from
    # anywhere, so the shape is taken from the customer's own country first.
    pincode_country_id = fields.Many2one(
        'res.country', string='Default Address Country',
        default=lambda self: self.env.company.country_id,
        help="Whose postcode format to expect when the customer's own contact "
             "does not name a country. Leave empty to accept any reasonable "
             "postcode.")
    pincode_prefixes = fields.Char(
        'Accepted Postcode Prefixes',
        help="Comma-separated areas you actually deliver to, e.g. 691,690,682. "
             "A postcode starting with none of them is refused and the "
             "customer is asked again.\n\n"
             "Leave empty to accept any correctly formed postcode. Without a "
             "national postcode list this is the only exact check available: "
             "no format rule can tell 691001 from 789655, because both are "
             "shaped like a real Indian pincode.")

    # The private address form link (21 Nov 2026), see sa_address_link.py.
    address_link_enabled = fields.Boolean(
        'Send an Address Form Link', default=True,
        help="A new address, or a change to a saved one (in an order or from "
             "MORE > CHANGE ADDRESS), is filled in on a form with the same "
             "fields as the shop's Delivery Address page, sent to the "
             "customer's private chat. When WhatsApp hides their number the "
             "link goes to the group and the questions are asked there too. "
             "On by default; switch it off to keep the questions in the group only.")
    # Personal links and PDFs in the private chat (21 Nov 2026), see
    # sa_private_links.py.
    private_links = fields.Boolean(
        'Send Links & PDFs Privately', default=True,
        help="Personal links - product details, sign, pay, live tracking, the "
             "rider's location - and the invoice and order PDFs go to the "
             "customer's private chat, with a short note in the group. When "
             "WhatsApp hides the customer's number, or the private message "
             "cannot be sent, they go to the group as before. Polls stay in "
             "the group.")
    address_link_minutes = fields.Integer(
        'Address Link Works For (minutes)', default=30,
        help="How long the address form link can be used. It always works only "
             "once, and stops as soon as the address is given in the group.")

    stale_after_minutes = fields.Integer(
        'Forget a Conversation After (minutes)', default=60,
        help="How long an unanswered question stays live. After this, a YES "
             "or a tapped option is treated as a new message rather than an "
             "answer to something the customer has long forgotten.\n\n"
             "Set too high, an old prompt lies in wait: on 31 Aug an ACCEPT "
             "resolved a question asked 88 minutes earlier and quoted the "
             "customer a product they had not asked about.")

    max_order_quantity = fields.Integer(
        'Largest Quantity Accepted', default=1000,
        help="A quantity above this is refused and the customer is asked "
             "again. There was no limit at all until a test typed 100000 and "
             "raised a quotation for 2,808,000.\n\n"
             "Zero removes the limit.")

    # ---- Messages that are not enquiries ----
    chatter_action = fields.Selection([
        ('ignore', 'Say nothing'),
        ('reply', 'Send a short acknowledgement'),
    ], string='Small Talk', default='ignore', required=True,
        help="What to do with a message in a customer group that is not a "
             "product enquiry - \"thanks\", \"have a nice day\", ordinary "
             "conversation between members.\n\n"
             "Saying nothing is the default because a sales group is mostly "
             "people talking to each other, and answering all of it turns the "
             "assistant into noise. Turn the acknowledgement on for a quiet "
             "group where silence reads as the bot being broken.")

    chatter_reply_text = fields.Char(
        'Acknowledgement', default="\U0001F642",
        help="Sent once per person per minute at most, so a burst of chat "
             "cannot turn into a burst of replies.")

    media_action = fields.Selection([
        ('ignore', 'Say nothing, keep the message'),
        ('reply', 'Ask for the product name as text'),
        ('discard', 'Say nothing, and keep no record of it'),
    ], string='Photos, Video and Files', default='ignore', required=True,
        help="A photo, video, sticker or document with no caption carries "
             "nothing this module can read, so it is never an enquiry.\n\n"
             "*Keep no record of it* stops the message being stored in 369ai "
             "at all - useful where groups are full of forwards. It cannot "
             "delete anything from WhatsApp itself: the shared gateway allows "
             "sending and lookups only, and a delete route there would let "
             "one client remove another client's messages.")

    media_reply_text = fields.Char(
        'Photo Reply',
        default="I can't read photos or video - please type the product name "
                "and I'll check it for you.",
        help="Sent once per person per minute at most.")

    # ---- Guided finder ----
    finder_enabled = fields.Boolean(
        'Guided Finder', default=True,
        help="A generic word - headphone, laptop, charger - opens a tap-only "
             "finder in the customer's private chat: kind, brand, model, "
             "picture, confirm. Exact product names still get a price at once.")
    finder_image_model = fields.Char(
        'Image Model', default='gemini-3.1-flash-image',
        help="Gemini model used to draw a reference picture when the "
             "catalogue has none.")
    finder_image_fallback_model = fields.Char(
        'Image Model (fallback)', default='gemini-2.5-flash-image')
    finder_cache_days = fields.Integer(
        'Keep AI Suggestions (days)', default=7,
        help="Types, brands, models and reference images are remembered this "
             "long, so the same question is not put to the AI twice.")
    finder_max_options = fields.Integer(
        'Options per Poll', default=10,
        help="WhatsApp allows twelve; two are kept for Back and Not listed.")

    active = fields.Boolean('Enabled', default=True)
    status_message = fields.Char('Last Test', readonly=True)

    test_message = fields.Text(
        'Sample Message',
        default='do you have 10 laptop chargers in stock',
        help="A message as a group member would type it. Press Test "
             "Classifier to see what the AI makes of it.",
    )
    test_result = fields.Text('Test Result', readonly=True, copy=False)

    @api.onchange('provider')
    def _onchange_provider_clears_overrides(self):
        """A URL and a model name belong to the provider they were typed for.

        Kept, they are actively dangerous: switching SinoRouter -> OpenAI while
        its Base URL is still set would send OpenAI-keyed requests to
        SinoRouter's host. Clearing lets the new provider's defaults apply.
        """
        for rec in self:
            rec.api_base_url = False
            rec.model_name = False
            rec.test_result = False

    @api.model
    def get_settings(self):
        settings = self.search([], limit=1)
        if not settings:
            settings = self.create({})
        return settings

    def _effective_key(self):
        """This record's key, or the tracker's key for the same provider.

        The tracker only ever stored keys for its own three providers, so a
        provider it never knew about - SinoRouter - has nothing to inherit and
        must have its key typed here.
        """
        self.ensure_one()
        if self.api_key:
            return self.api_key
        voice = self.env['wa.voice.config'].sudo().search([], limit=1)
        if not voice:
            return ''
        return {
            'gemini': voice.gemini_api_key,
            'groq': voice.groq_api_key,
            'openai': voice.openai_api_key,
        }.get(self.provider) or ''

    def _effective_model(self):
        self.ensure_one()
        return self.model_name or DEFAULT_CHAT_MODEL.get(self.provider) or ''

    def _effective_base_url(self):
        """Where to POST. Empty for Gemini, which has its own call shape.

        The override is ignored for Gemini rather than merely unused: a URL
        left behind by a previous provider was being reported as the endpoint
        for a Gemini call that never went near it, which is exactly the kind of
        thing that sends someone debugging in the wrong direction.
        """
        self.ensure_one()
        if self.provider == 'gemini':
            return ''
        return (self.api_base_url or '').strip() or DEFAULT_BASE_URL.get(
            self.provider) or ''

    def action_test_classifier(self):
        """Run the sample message and write the full report into the form.

        Saved first, so the message and any key or URL just typed are the ones
        actually tested - otherwise the report describes the previous
        configuration and quietly contradicts what is on screen.
        """
        self.ensure_one()
        report = self.env['sa.ai.classifier'].diagnose(self.test_message, self)
        first = next((line for line in report.split(chr(10))
                      if line.startswith(('Verdict', 'Error', 'Prefilter     : REJECTED',
                                          'API key       : MISSING'))), '')
        self.write({
            'test_result': report,
            'status_message': first.split(':', 1)[-1].strip() or _('see result below'),
        })
        return False
