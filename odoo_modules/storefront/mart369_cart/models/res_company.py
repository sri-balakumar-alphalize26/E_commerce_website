# -*- coding: utf-8 -*-
"""Delivery slots on or off, per company (13 Nov 2026, owner).

On (the default): the slots added in the backend are offered - at the
storefront checkout and on the WhatsApp order page - and picking one is
optional. Off: no slot choice anywhere for that company's orders.
"""
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    mart369_slots_on = fields.Boolean(
        string='Offer delivery slots', default=True,
        help="On: customers can pick one of the delivery slots set up under "
             "Delivery > Slots, at the storefront checkout and on the "
             "WhatsApp order page (optional for them). Off: no slot choice "
             "for this company's orders.")
