# -*- coding: utf-8 -*-
from odoo import models


class SaGroupRequestPollSearch(models.Model):
    _inherit = 'sa.group.request'

    def _sa_menu_search_show(self, term):
        """A new search: the customer's older polls are over (sa_poll_rule.py)."""
        self._sa_poll_close_customer()
        return super()._sa_menu_search_show(term)
