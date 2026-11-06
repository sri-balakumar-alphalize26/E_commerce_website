# -*- coding: utf-8 -*-
from odoo import fields, models


class SaDeliverySettings(models.Model):
    _inherit = 'sa.delivery.settings'

    shop_confirms = fields.Boolean(
        'Shop Confirms Orders', default=True,
        help="On, a paid order waits on the shop's screen until somebody "
             "accepts it and says it is packed. Only then is a rider "
             "called.\n\n"
             "Off, the rider is called the moment the order is paid - which "
             "is right for a business where the same person packs and "
             "delivers, and wrong for anywhere a rider can arrive before the "
             "goods are off the shelf.")

    alarm_ring_seconds = fields.Integer(
        'Ring For (seconds)', default=30,
        help="How long one ring lasts. The screen beeps continuously for "
             "this long, rests for the repeat interval, and rings again "
             "until the order is accepted.")
    alarm_repeat_seconds = fields.Integer(
        'Alarm Repeats Every (s)', default=10,
        help="How often the shop screen sounds while an order is waiting. It "
             "keeps sounding until every waiting order has been accepted - "
             "one alarm for the queue, not one per order.")

    # ---- The enquiry desk. A separate alarm, on purpose: a counter needs to
    # know whether it is being asked to pack something or to choose a
    # supplier, and those are different jobs for different people.
    # ---- "no vendor replied" - its own cadence ----
    stalled_ring_seconds = fields.Integer(
        'No-Reply Ring For (seconds)', default=30,
        help="How long one no-reply alarm lasts before it rests.")
    stalled_repeat_minutes = fields.Integer(
        'No-Reply Alarm Repeats Every (minutes)', default=2,
        help="The gap between no-reply alarms. Minutes, not seconds: "
             "somebody has to phone a supplier before this card can be "
             "cleared, and beeping every ten seconds while they are on the "
             "phone only gets the speakers turned off.")
    stalled_alarm_minutes = fields.Integer(
        'Stop the No-Reply Alarm After (minutes)', default=10,
        help="Zero means never stop.")
    # ---- Chasing stock that has been bought in ----
    supply_remind_hour = fields.Integer(
        'Remind About Waiting Stock At (hour)', default=9,
        help="Hour of the morning, 0-23, in your own timezone. Each shop is "
             "sent one WhatsApp listing everything it is still waiting for, "
             "and the counter screen rings.")
    supply_remind_days = fields.Integer(
        'Keep Reminding For (days)', default=0,
        help="Stop chasing an order this many days after the suppliers were "
             "asked. Zero keeps reminding until somebody marks the goods "
             "arrived - which is the honest default, because the order is "
             "still owed to a customer either way.")
    enquiry_ring_seconds = fields.Integer(
        'Enquiry Ring For (seconds)', default=30,
        help="How long one enquiry alarm lasts before it rests.")
    enquiry_repeat_seconds = fields.Integer(
        'Enquiry Alarm Repeats Every (s)', default=10,
        help="The quiet gap between enquiry alarms.")
    enquiry_alarm_minutes = fields.Integer(
        'Stop the Enquiry Alarm After (minutes)', default=1,
        help="Unlike the packing alarm, this one gives up. A counter that "
             "has been beeping for an hour is a counter where somebody has "
             "turned the speakers off.\n\n"
             "Zero means never stop.")
