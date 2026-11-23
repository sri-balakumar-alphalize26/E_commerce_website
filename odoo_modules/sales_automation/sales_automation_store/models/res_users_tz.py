# -*- coding: utf-8 -*-
"""The browser's timezone becomes the user's preference (see
static/src/browser_tz_service.js)."""
import logging

import pytz

from odoo import api, models

_logger = logging.getLogger(__name__)


class ResUsersBrowserTz(models.Model):
    _inherit = 'res.users'

    @api.model
    def sa_set_browser_tz(self, zone):
        """Set the current user's timezone to the browser's zone. Own record
        only, a real IANA zone only."""
        if not zone or zone not in pytz.all_timezones_set:
            return False
        user = self.env.user
        if user.tz != zone:
            user.sudo().write({'tz': zone})
            _logger.info("Store: timezone of %s set to the browser's %s (was %s)",
                         user.login, zone, user.tz)
        return True
