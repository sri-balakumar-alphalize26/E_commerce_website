# -*- coding: utf-8 -*-
from odoo import fields, models


class SaAiSettingsConfirm(models.Model):
    _inherit = 'sa.ai.settings'

    confirm_enabled = fields.Boolean(
        'Customers confirm on the page', default=True,
        help="A matched product is confirmed on the picture + details page (ACCEPT / REJECT) "
             "instead of a YES / NO poll in the chat.")
    confirm_vendor_enabled = fields.Boolean(
        'Vendors confirm on the page', default=True,
        help="The price check carries the picture and the page link; ACCEPT means 'I have this exact "
             "product' and the price is then asked.")
    confirm_fetch_images = fields.Boolean(
        'Draw an AI reference picture when there is none', default=True,
        help="A product or enquiry with no picture gets an AI reference picture, marked as a reference "
             "on the page. Pictures are never searched for on the internet.")
    confirm_remind_minutes = fields.Integer('Remind after (minutes)', default=10,
                                            help="One reminder when the customer has not pressed anything.")
    confirm_link_count = fields.Integer(compute='_compute_confirm_counts')
    confirm_click_count = fields.Integer(compute='_compute_confirm_counts')

    def _compute_confirm_counts(self):
        Link = self.env['sa.confirm.link'].sudo()
        Click = self.env['sa.link.click'].sudo()
        for s in self:
            s.confirm_link_count = Link.search_count([])
            s.confirm_click_count = Click.search_count([])
