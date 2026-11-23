# -*- coding: utf-8 -*-
"""The vendors' reply window (owner, 23 Nov 2026).

It is as long as the setting says, from the moment the vendors are asked. When
it ends, the prices that came in time are looked at together: the lowest wins,
the customer gets it with the margin. A price that comes later is kept and
shown, and never changes by itself what the customer was told."""
import logging
from datetime import timedelta

import psycopg2

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import config

_logger = logging.getLogger(__name__)

# arrivals are stored by the second, the deadline too
SLACK = timedelta(seconds=1)
OPEN_FOR_BETTER = ('quoted', 'negotiating')


class SaVendorQuoteWindow(models.Model):
    _inherit = 'sa.vendor.quote'

    sa_rank = fields.Integer('Place', readonly=True, copy=False, help="1 is the lowest price that came in time.")
    sa_in_window = fields.Boolean('In Time', readonly=True, copy=False)
    sa_late = fields.Boolean('Late', readonly=True, copy=False, help="Came after the prices were looked at.")
    sa_sell_price = fields.Monetary('Customer Would Pay', currency_field='currency_id', compute='_compute_sa_sell_price')

    @api.depends('price', 'request_id.sa_margin_used')
    def _compute_sa_sell_price(self):
        margin = self.env['sa.ai.settings'].sudo().get_settings().margin_percent or 0.0
        for rec in self:
            used = rec.request_id.sa_margin_used if rec.request_id.sa_evaluated_on else margin
            rec.sa_sell_price = (rec.price or 0.0) * (1.0 + used / 100.0)

    @api.model_create_multi
    def create(self, vals_list):
        quotes = super().create(vals_list)
        for quote in quotes:
            request = quote.request_id
            if request.sa_evaluated_on and request.state != 'sourcing' and quote.matched_by != 'manual':
                quote.sa_late = True
        return quotes

    def _sa_arrived(self):
        self.ensure_one()
        return self.message_id.create_date or self.create_date or fields.Datetime.now()

    def _sa_who(self):
        self.ensure_one()
        return self.partner_id.id or ('p', (self.vendor_phone or '')[-9:]) if (self.partner_id or self.vendor_phone) else ('q', self.id)

    def action_sa_use_late(self):
        """The counter: give the customer this better price."""
        self.ensure_one()
        self.request_id._sa_use_better(self)
        return True


class SaGroupRequestWindow(models.Model):
    _inherit = 'sa.group.request'

    sa_evaluated_on = fields.Datetime('Prices Looked At On', readonly=True, copy=False)
    sa_margin_used = fields.Float('Margin Used (%)', readonly=True, copy=False)
    sa_window_extended = fields.Boolean(readonly=True, copy=False,
                                        help="Somebody has it but nobody had given a price: waited once more.")
    sa_better_quote_id = fields.Many2one('sa.vendor.quote', compute='_compute_sa_better_quote', string='Late but Cheaper')

    @api.depends('quote_ids.sa_late', 'quote_ids.price', 'best_quote_id', 'state')
    def _compute_sa_better_quote(self):
        for rec in self:
            late = rec.quote_ids.filtered(lambda q: q.sa_late and q != rec.best_quote_id) if rec.state in OPEN_FOR_BETTER else rec.quote_ids[:0]
            best = late.sorted(lambda q: (q.price, q.id))[:1]
            rec.sa_better_quote_id = best if best and rec.best_quote_id and best.price < rec.best_quote_id.price - 0.004 else False

    # ------------------------------------------------------------ the clock
    def _sa_wake_at(self, when):
        """The closing job runs at that moment, not up to a minute later."""
        cron = self.env.ref('sales_automation.cron_sa_close_sourcing', raise_if_not_found=False)
        if cron and when:
            cron.sudo()._trigger(at=when + SLACK)

    def _start_sourcing(self, vendors):
        res = super()._start_sourcing(vendors)
        if self.state == 'sourcing' and self.sourcing_deadline:
            self.write({'sa_evaluated_on': False, 'sa_window_extended': False})
            self._sa_wake_at(self.sourcing_deadline)
        return res

    # A vendor's "I have it" no longer starts the window again.
    def _sa_vendor_window_again(self):
        return True

    def _sa_wechat_extend_window(self):
        return True

    # ------------------------------------------------------------ the end
    @api.model
    def _cron_close_sourcing(self):
        """Each enquiry on its own: one that cannot be closed now stops none of
        the others and is tried again, unchanged, at the next run."""
        due = self.sudo().search([('state', '=', 'sourcing'), ('sourcing_deadline', '<=', fields.Datetime.now())], order='sourcing_deadline, id')
        test = config['test_enable']
        for request_id in due.ids:
            request = self.sudo().browse(request_id)
            try:
                with self.env.cr.savepoint():
                    request._close_sourcing()
                if not test:
                    self.env.cr.commit()
            except psycopg2.OperationalError as err:
                _logger.info("Sales Automation: enquiry %s is being changed by somebody - closed at the next run (%s)",
                             request_id, str(err).split('\n')[0])
                if not test:
                    self.env.cr.rollback()
                self.env.invalidate_all()
            except Exception as err:  # noqa: BLE001 - one bad enquiry must not stall every other one
                _logger.exception("Sales Automation: closing enquiry %s failed", request_id)
                self.env.invalidate_all()
                request.write({'state': 'dropped', 'drop_reason': 'error', 'error': str(err)[:2000]})
                if not test:
                    self.env.cr.commit()

    def _sa_lock_enquiry(self):
        """False when somebody else is closing this one right now."""
        self.ensure_one()
        self.flush_recordset()
        self.env.cr.execute('SELECT id FROM sa_group_request WHERE id = %s FOR UPDATE SKIP LOCKED', [self.id])
        if not self.env.cr.fetchone():
            return False
        self.invalidate_recordset(['state', 'sourcing_deadline', 'sa_price_stalled'])
        return True

    def _sa_window_quotes(self):
        """(in time, after the window): one price per vendor, their newest."""
        self.ensure_one()
        deadline = self.sourcing_deadline or fields.Datetime.now()
        newest = {}
        for quote in self.quote_ids.sorted('id'):
            if (quote.price or 0.0) > 0:
                newest.setdefault('in' if quote._sa_arrived() <= deadline + SLACK else 'after', {})[quote._sa_who()] = quote
        pick = lambda key: self.quote_ids.browse([q.id for q in newest.get(key, {}).values()])  # noqa: E731
        return pick('in'), pick('after')

    def _close_sourcing(self):
        self.ensure_one()
        if not self._sa_lock_enquiry():
            return False
        if self.state != 'sourcing' or (self.sourcing_deadline and self.sourcing_deadline > fields.Datetime.now()):
            return False
        in_time, after = self._sa_window_quotes()
        pool = in_time or after         # nobody in time, but somebody meanwhile: better than nothing
        if not pool:
            held = [h.get('partner') for h in self._sa_held().values()]
            waiting = (self.sa_vendor_yes_ids - self.sa_vendor_no_ids).filtered(lambda p: p.id not in held)
            if waiting and not self.sa_window_extended and not self.sa_price_stalled:
                window = max(1, self._settings().sourcing_window_minutes or 10)
                until = fields.Datetime.add(fields.Datetime.now(), minutes=window)
                self.write({'sa_window_extended': True, 'sourcing_deadline': until})
                self._sa_wake_at(until)
                _logger.info("Sales Automation: enquiry %s - %s said yes, no price yet: waiting once more", self.id, waiting.mapped('name'))
                return True
            return super()._close_sourcing()
        order = pool.sorted(lambda q: (round(q.price, 4), q._sa_arrived(), q.delay_days or 0, q.id))
        margin = self._settings().margin_percent or 0.0
        self.write({'sa_evaluated_on': fields.Datetime.now(), 'sa_margin_used': margin})
        (self.quote_ids - order).write({'sa_rank': 0, 'sa_in_window': False})
        for place, quote in enumerate(order, 1):
            quote.write({'sa_rank': place, 'sa_in_window': quote in in_time, 'sa_late': False})
        best = order[:1]
        _logger.info("Sales Automation: enquiry %s - %s price(s), lowest %.2f from %s", self.id, len(order), best.price,
                     best.partner_id.name or best.vendor_name or best.vendor_phone)
        return self._apply_winning_quote(best)

    # ------------------------------------------------------------ late, but cheaper
    def _sa_use_better(self, quote):
        self.ensure_one()
        if not self._sa_lock_enquiry():
            raise UserError(_("Somebody is changing this enquiry. Try again in a moment."))
        if quote.request_id != self or self.state not in OPEN_FOR_BETTER:
            raise UserError(_("The customer has answered already; the price stays."))
        if not self.best_quote_id or quote.price >= self.best_quote_id.price:
            raise UserError(_("That price is not lower."))
        self._say(_("\U0001F44D Good news - we got you a better price.\n\n_Ref %s_") % (self.ref_code or self.id))
        self.with_context(sa_price_approved=True)._apply_winning_quote(quote)
        _logger.info("Sales Automation: enquiry %s - late price %.2f used by %s", self.id, quote.price, self.env.user.name)
        return True
