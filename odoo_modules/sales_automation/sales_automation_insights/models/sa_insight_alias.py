# -*- coding: utf-8 -*-
"""A second spelling of the same human.

One customer is one row in `sa.insight.entity`, but the same person reaches
us as a partner id, a phone number, and sometimes a WhatsApp @lid - and the
data records whichever it happened to see. An alias is a spelling that folds
into a row without becoming a row of its own.
"""
from odoo import fields, models


class SaInsightAlias(models.Model):
    _name = 'sa.insight.alias'
    _description = 'Insight Entity Alias'
    _rec_name = 'tail'

    entity_id = fields.Many2one(
        'sa.insight.entity', required=True, ondelete='cascade', index=True)
    tail = fields.Char(
        'Phone Tail', index=True,
        help="The last nine digits, which is how every lookup in "
             "sales_automation compares numbers.")
    lid = fields.Char('WhatsApp LID', index=True)
    source = fields.Char(
        'Learned From',
        help="What taught us this spelling belongs here - 'order partner', "
             "'request carried both', 'merge'.")
