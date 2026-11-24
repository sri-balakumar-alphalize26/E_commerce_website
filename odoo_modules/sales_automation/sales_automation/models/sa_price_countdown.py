# -*- coding: utf-8 -*-
"""Two prices - approve one: counts down, then goes by itself (24 Nov 2026).

Only with Automatic, and never when our price is far below the product page's:
that is more often a slip of the vendor's than a bargain. Any button before the
end stops it."""
import logging
from datetime import timedelta

import psycopg2

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import config

_logger = logging.getLogger(__name__)

DAY = 24 * 60


class SaAiSettingsPriceCountdown(models.Model):
    _inherit = 'sa.ai.settings'

    price_auto_minutes = fields.Integer('Two Prices: Goes by Itself After (minutes)', default=1)
    price_auto_max_below = fields.Float('Two Prices: Not by Itself When Below the Page by More Than (%)', default=50.0)

    def _easy_problems(self, names):
        out = super()._easy_problems(names)
        if 'price_auto_minutes' in names and not 0 <= self.price_auto_minutes <= DAY:
            out.append(_("How long before it goes by itself? Type 0 (wait for me) to 1440 minutes (a day)."))
        if 'price_auto_max_below' in names and not 0 <= self.price_auto_max_below <= 100:
            out.append(_("How far below the page price is too low? Type 0 to 100 percent."))
        return out


class SaGroupRequestPriceCountdown(models.Model):
    _inherit = 'sa.group.request'

    sa_price_auto_on = fields.Datetime('Goes by Itself On', readonly=True, copy=False, index='btree_not_null')

    def _sa_price_below(self):
        """How far our price is below the page's, in percent; 0 when it is not."""
        self.ensure_one()
        page = self.sa_price_page or 0.0
        return max(0.0, (page - (self.sa_price_vendor or 0.0)) / page * 100.0) if page > 0 else 0.0

    def _sa_price_may_go(self):
        self.ensure_one()
        settings = self._settings()
        return bool(settings.vendor_choice_mode == 'auto' and settings.price_auto_minutes > 0 and self.sa_price_vendor > 0
                    and self._sa_price_below() <= settings.price_auto_max_below + 0.005)

    def _sa_price_seconds_left(self):
        """Seconds until it goes by itself; -1 when it waits for a person."""
        self.ensure_one()
        if not (self.sa_price_choice_pending and self.sa_price_auto_on):
            return -1
        return max(0, int((self.sa_price_auto_on - fields.Datetime.now()).total_seconds()))

    def _sa_hold_for_price_choice(self, quote, page, vendor_sell):
        res = super()._sa_hold_for_price_choice(quote, page, vendor_sell)
        until = False
        if self._sa_price_may_go():
            until = fields.Datetime.now() + timedelta(minutes=self._settings().price_auto_minutes)
        self.sa_price_auto_on = until
        if until:
            self._sa_wake_at(until)
            self._sa_enquiry_notify()
        return res

    def _sa_apply_price_choice(self, choice, sell=None, source=''):
        """One at a time: the button and the countdown never both send."""
        self.ensure_one()
        if not self._sa_lock_enquiry():
            raise UserError(_("Somebody is changing this enquiry. Try again in a moment."))
        self.invalidate_recordset(['sa_price_choice_pending', 'sa_price_auto_on'])
        res = super()._sa_apply_price_choice(choice, sell=sell, source=source)
        self.sa_price_auto_on = False
        return res

    def _sa_price_go(self):
        """The countdown is over. True when the customer was told."""
        self.ensure_one()
        if not self._sa_lock_enquiry():
            return False            # somebody presses a button right now
        self.invalidate_recordset(['sa_price_choice_pending', 'sa_price_auto_on', 'sa_price_vendor', 'sa_price_page'])
        if not self.sa_price_auto_on or self.sa_price_auto_on > fields.Datetime.now():
            return False
        if self.state != 'sourcing' or not self.sa_price_choice_pending or not self._sa_price_may_go():
            self.sa_price_auto_on = False       # waits for a person, as before
            self._sa_enquiry_notify()
            return False
        self._sa_apply_price_choice('vendor', source=_("by itself"))
        return True

    @api.model
    def _cron_close_sourcing(self):
        res = super()._cron_close_sourcing()
        test = config['test_enable']
        for request_id in self.sudo().search([('sa_price_auto_on', '<=', fields.Datetime.now())], order='sa_price_auto_on, id').ids:
            request = self.sudo().browse(request_id)
            try:
                with self.env.cr.savepoint():
                    request._sa_price_go()
                if not test:
                    self.env.cr.commit()
            except psycopg2.OperationalError as err:
                _logger.info("Sales Automation: the price of enquiry %s goes at the next run (%s)", request_id, str(err).split('\n')[0])
                if not test:
                    self.env.cr.rollback()
                self.env.invalidate_all()
            except Exception:  # noqa: BLE001 - a person decides instead, the others go on
                _logger.exception("Sales Automation: the price of enquiry %s could not go by itself", request_id)
                self.env.invalidate_all()
                request.sa_price_auto_on = False
                if not test:
                    self.env.cr.commit()
        return res
