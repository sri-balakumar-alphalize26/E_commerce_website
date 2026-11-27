# -*- coding: utf-8 -*-
from odoo import fields, models


class SaAiSettingsLoyalty(models.Model):
    _inherit = 'sa.ai.settings'

    loyalty_offer_enabled = fields.Boolean(
        'Offer points before the pay link', default=True,
        help="A customer whose card can redeem is asked, in the group, whether to use the "
             "points on this order before the pay link is sent.")
    loyalty_offer_wait_minutes = fields.Integer(
        'Offer waits (minutes)', default=10,
        help="No answer to the offer for this long: the pay link goes out for the full amount.")
    loyalty_offer_text = fields.Text(
        'Offer text',
        default="\U0001F381 You have *{points}* loyalty points (worth {cur} {value}). "
                "Use them on order *#{ref}*?",
        help="Placeholders: {points} {value} {cur} {ref}")
    loyalty_paid_text = fields.Text(
        'Points-earned text',
        default="\U0001F381 You earned *{earned}* loyalty points on this order. Balance: *{balance}* points.",
        help="Placeholders: {earned} {balance} {ref}")
    loyalty_notify_dm = fields.Boolean(
        'Tell private-chat customers too', default=True,
        help="Orders that were made in a private WhatsApp chat (not a group) get the "
             "points-earned line in that chat.")
