# -*- coding: utf-8 -*-
"""The conduct filter's switches, on the AI Settings page the owner already
uses. Inherited here so `sales_automation` itself is not edited for it."""
from odoo import fields, models

from .sa_conduct_remark import (_default_conduct_words, _default_conduct_phrases,
                                _default_conduct_link_words, _default_conduct_doubtful_words,
                                _default_conduct_safe_words,
                                DEFAULT_MEDIA_PROMPT, DEFAULT_TEXT_PROMPT)


class SaAiSettingsConduct(models.Model):
    _inherit = 'sa.ai.settings'

    conduct_enabled = fields.Boolean(
        'Remove abusive messages', default=True,
        help="A customer's or supplier's message containing a listed word is "
             "deleted in WhatsApp, recorded as a remark against them, and "
             "counted against their rating. The bot never reads it.")
    conduct_words = fields.Text(
        'Words', default=lambda self: _default_conduct_words(),
        help="One per line, any language or script. Whole words only.")
    conduct_phrases = fields.Text(
        'Phrases', default=lambda self: _default_conduct_phrases(),
        help="Exact phrases, one per line.")
    conduct_links = fields.Boolean(
        'Remove adult links', default=True,
        help="A link whose address contains one of the fragments below is "
             "removed like a bad word.")
    conduct_link_words = fields.Text(
        'Link fragments', default=lambda self: _default_conduct_link_words(),
        help="One per line. Matched anywhere in the link's address, e.g. "
             "'porn' catches pornhub.com and free-porn.xyz.")
    conduct_media = fields.Boolean(
        'Remove sexual photos and videos', default=True,
        help="Every photo, video, sticker and video note is shown to the AI "
             "model configured above and removed when it says the content is "
             "sexual. Needs a working provider key.")
    conduct_media_prompt = fields.Text(
        'Media check prompt', default=DEFAULT_MEDIA_PROMPT)
    conduct_doubtful_words = fields.Text(
        'Doubtful words', default=lambda self: _default_conduct_doubtful_words(),
        help="Words that are rude only sometimes. A message containing one is "
             "not removed on its own; it is shown to the AI model, which decides.")
    conduct_safe_words = fields.Text(
        'Never doubtful', default=lambda self: _default_conduct_safe_words(),
        help="Ordinary words that must never be sent to the model as a near "
             "miss of a listed word (price is one letter from prick).")
    conduct_doubt_min = fields.Integer(
        'Ask the model from (%)', default=50,
        help="How suspicious a message must look locally before it is worth "
             "asking the model. A near-miss spelling of a listed word scores "
             "55, a listed word hidden inside a longer word 60, a doubtful "
             "word 50. Below this nothing is sent and the message stays.")
    conduct_llm_min_confidence = fields.Integer(
        'Auto-delete when the model is at least (%) sure', default=60,
        help="The model answers with a confidence. At or above this it is "
             "deleted, remarked and rated; below it the message stays.")
    conduct_model_mode = fields.Selection([
        ('doubt', 'Only doubtful messages (recommended)'),
        ('all', 'Every text message'),
    ], 'Ask the model about', default='doubt', required=True,
        help="Doubtful = a near-miss or sound-alike of a listed word, or a "
             "doubtful word. 'Every text message' costs one model call per "
             "message in every group.")
    conduct_doubt_action = fields.Selection([
        ('delete_first', 'Delete at once, ask the model afterwards (fastest)'),
        ('ask_first', 'Ask the model first, delete only if it agrees'),
    ], 'Doubtful messages', default='delete_first', required=True,
        help="Delete at once: a doubtful message is removed the moment it "
             "arrives; the model is asked afterwards only to grade the remark "
             "(its answer is kept on the remark, the message is already gone). "
             "Ask first: the message stays until the model answers - up to the "
             "model timeout below per message.")
    conduct_model_timeout = fields.Integer(
        'Model timeout for this check (seconds)', default=6,
        help="How long one conduct question to the model may take. Short on "
             "purpose: the product classifier's own timeout (20 s) made every "
             "doubtful word wait that long before it was removed.")
    conduct_text_prompt = fields.Text('Text check prompt', default=DEFAULT_TEXT_PROMPT)
    conduct_warn = fields.Selection([
        ('off', 'No warning'),
        ('same', 'Warn in the same chat'),
        ('private', 'Warn privately'),
    ], 'After removing', default='same', required=True)
    conduct_warn_text = fields.Char(
        'Warning text',
        default='Please keep it respectful. Your message was removed.')
