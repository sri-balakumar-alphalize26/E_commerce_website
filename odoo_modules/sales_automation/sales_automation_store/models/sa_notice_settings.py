# -*- coding: utf-8 -*-
from odoo import fields, models


class SaAiSettingsNotify(models.Model):
    _inherit = 'sa.ai.settings'

    notice_on = fields.Boolean('Side Notifications', default=True,
                               help="New order, vendor price, cheaper vendor, payment and WhatsApp problems, "
                                    "at the side of every Odoo page.")
