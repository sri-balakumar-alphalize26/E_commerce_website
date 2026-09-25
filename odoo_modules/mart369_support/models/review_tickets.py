"""A one- or two-star rating is a support case, not just a number.

When a customer rates an order or reviews a product with one or two stars, a
ticket is opened for them - or their open one reused, the way the bot does
(`mart369.ticket._mart369_open`) - with what they wrote posted on it, so
somebody calls them back instead of the rating sitting in a list. The staff
Reviews screens show which ticket it is.

Here rather than in mart369_account, because tickets are this module's: it
depends on the account module, never the other way round.
"""

from odoo import api, fields, models

LOW = 2


class RatingRating(models.Model):
    _inherit = 'rating.rating'

    mart369_ticket_id = fields.Many2one('mart369.ticket', string='Support ticket', readonly=True)

    def _mart369_low_rating_ticket(self, partner, order, what):
        """Open (or reuse) a ticket for a low rating, once per rating."""
        self.ensure_one()
        if self.rating > LOW or self.mart369_ticket_id:
            return self.mart369_ticket_id
        stars = int(round(self.rating))
        ticket = self.env['mart369.ticket'].sudo()._mart369_open(
            partner, '%s-star %s' % (stars, what), order=order or None)
        lines = ['Rated %s of 5 - %s.' % (stars, what)]
        if self.mart369_title:
            lines.append(self.mart369_title)
        if self.feedback:
            lines.append(self.feedback)
        ticket._mart369_say('\n'.join(lines), from_customer=True)
        self.sudo().mart369_ticket_id = ticket
        return ticket

    @api.model
    def _mart369_write_review(self, partner, product, values):
        row = super()._mart369_write_review(partner, product, values)
        # The order it came in, when there is one, so the agent sees it.
        order = self.env['sale.order'].sudo().search([
            ('partner_id', '=', partner.id),
            ('mart369_state', '=', 'delivered'),
            ('order_line.product_id.product_tmpl_id', '=', product.id),
        ], order='mart369_placed_at desc', limit=1)
        row._mart369_low_rating_ticket(partner, order, 'review of %s' % product.display_name)
        return row

    @api.model
    def _mart369_rate_order(self, partner, order, values):
        row = super()._mart369_rate_order(partner, order, values)
        row._mart369_low_rating_ticket(partner, order, 'rating of order %s' % (order.mart369_ref or ''))
        return row

    def _mart369_admin_serialize(self, names=None):
        out = super()._mart369_admin_serialize(names)
        out['ticket'] = self.mart369_ticket_id.name or ''
        out['ticketId'] = self.mart369_ticket_id.id or False
        return out
