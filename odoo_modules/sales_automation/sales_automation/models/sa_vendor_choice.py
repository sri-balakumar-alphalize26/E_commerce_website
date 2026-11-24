# -*- coding: utf-8 -*-
"""Who is the vendor: Automatic or Manual (owner, 24 Nov 2026).

Automatic: the lowest price; the same price: who answered first; the same second:
whom this product was bought from more; then the faster delivery; then the older
answer. Manual: the enquiry waits on Store > Enquiries until somebody chooses.
Changing the setting never sends anything: what waits for a person stays with
that person."""
import logging
from collections import Counter

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

REASONS = [
    ('only_price', 'the only price'),
    ('lowest_price', 'lowest price'),
    ('tie_first', 'same price, answered first'),
    ('tie_bought', 'same price and time, bought more'),
    ('tie_delivery', 'same price and time, faster delivery'),
    ('tie_fixed_order', 'all the same, in order of arrival'),
    ('manual', 'chosen by hand'),
]


class SaAiSettingsChoice(models.Model):
    _inherit = 'sa.ai.settings'

    vendor_choice_mode = fields.Selection([('auto', 'Automatic'), ('manual', 'Manual')], string='Who Chooses the Vendor',
                                          default='auto', required=True)


class SaGroupRequestChoice(models.Model):
    _inherit = 'sa.group.request'

    sa_vendor_choice_pending = fields.Boolean('Waiting for a Vendor to Be Chosen', index=True, copy=False, readonly=True)
    sa_selected_by = fields.Selection([('auto', 'Automatic'), ('manual', 'By Hand')], 'Vendor Chosen', copy=False, readonly=True)
    sa_selected_reason = fields.Selection(REASONS, 'Why This Vendor', copy=False, readonly=True)
    sa_selected_user_id = fields.Many2one('res.users', 'Vendor Chosen By', copy=False, readonly=True)
    sa_selected_on = fields.Datetime('Vendor Chosen On', copy=False, readonly=True)
    sa_close_tries = fields.Integer(copy=False, readonly=True, help="How often closing failed on a broken transaction.")

    # ------------------------------------------------------------ the order
    def _sa_bought_map(self):
        """{(product, vendor): confirmed orders that used this vendor's price}."""
        products = self.product_id
        if not products:
            return Counter()
        used = self.sudo().search([('product_id', 'in', products.ids), ('best_quote_id.partner_id', '!=', False),
                                   ('order_id.state', '=', 'sale')])
        return Counter((r.product_id.id, r.best_quote_id.partner_id.id) for r in used)

    def _sa_rank_key(self, quote, bought):
        times = bought.get((self.product_id.id, quote.partner_id.id), 0) if quote.partner_id else 0
        return (round(quote.price, 4), quote._sa_arrived().replace(microsecond=0), -times, quote.delay_days or 0, quote.id)

    def _sa_rank_quotes(self, quotes, bought=None):
        self.ensure_one()
        bought = self._sa_bought_map() if bought is None else bought
        return quotes.sorted(lambda q: self._sa_rank_key(q, bought))

    def _sa_rank_reason(self, order, bought=None):
        """The rule by which the first one beat the second one."""
        self.ensure_one()
        if len(order) < 2:
            return 'only_price'
        bought = self._sa_bought_map() if bought is None else bought
        one, two = self._sa_rank_key(order[0], bought), self._sa_rank_key(order[1], bought)
        for place, reason in enumerate(('lowest_price', 'tie_first', 'tie_bought', 'tie_delivery')):
            if one[place] != two[place]:
                return reason
        return 'tie_fixed_order'

    # ------------------------------------------------------------ by hand
    def _sa_wait_for_choice(self):
        """Manual: nothing is sent, the counter chooses."""
        self.ensure_one()
        self.write({'sa_vendor_choice_pending': True, 'sa_price_stalled': False, 'sourcing_deadline': False,
                    'sa_price_asked_on': fields.Datetime.now()})
        self._sa_enquiry_notify()
        _logger.info("Sales Automation: enquiry %s waits for somebody to choose the vendor", self.id)
        return True

    def _sa_selected(self, by, reason):
        self.ensure_one()
        self.write({'sa_selected_by': by, 'sa_selected_reason': reason, 'sa_selected_on': fields.Datetime.now(),
                    'sa_selected_user_id': self.env.uid if by == 'manual' else False})

    def _sa_can_choose_vendor(self):
        """Manual: as soon as there is a price, nobody has to wait for the window
        (owner, 24 Nov 2026). What already waits for a person stays with them."""
        self.ensure_one()
        return self.state == 'sourcing' and not self.sa_price_choice_pending and (
            self.sa_vendor_choice_pending or self._settings().vendor_choice_mode == 'manual')

    def _sa_choose_vendor(self, quote):
        """The counter chose this price; the customer is told."""
        self.ensure_one()
        if not self._sa_lock_enquiry():
            raise UserError(_("Somebody is changing this enquiry. Try again in a moment."))
        self.invalidate_recordset(['sa_vendor_choice_pending'])
        if not self._sa_can_choose_vendor():
            raise UserError(_("A vendor is already chosen for this enquiry."))
        mine = self.quote_ids.filtered(lambda q: (q.price or 0.0) > 0)
        newest = {}
        for one in mine.sorted('id'):
            newest[one._sa_who()] = one
        if quote not in newest.values():
            raise UserError(_("That price is no longer there. Look at the prices again."))
        if not self.sa_evaluated_on:
            self.write({'sa_evaluated_on': fields.Datetime.now(), 'sa_margin_used': self._sa_margin_live()})
        self.sourcing_deadline = False
        self._sa_selected('manual', 'manual')
        _logger.info("Sales Automation: enquiry %s - %s chosen at %.2f by %s", self.id,
                     quote.partner_id.name or quote.vendor_name or quote.vendor_phone, quote.price, self.env.user.name)
        return self._apply_winning_quote(quote)

    def _apply_winning_quote(self, quote):
        # whoever won, nobody has to choose any more
        for rec in self:
            if rec.sa_vendor_choice_pending:
                rec.sa_vendor_choice_pending = False
        return super()._apply_winning_quote(quote)

    def _drop(self, reason):
        if self.sa_vendor_choice_pending:
            self.sa_vendor_choice_pending = False
        return super()._drop(reason)
