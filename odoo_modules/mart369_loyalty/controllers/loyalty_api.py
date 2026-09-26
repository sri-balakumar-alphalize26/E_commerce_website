"""The customer's loyalty card, and points on the bill.

GET /369mart/loyalty is the Account page's Points screen: the card, what the
points are worth, how they are earned, and the history - the counter's rows and
the online ones together, because it is one card.

POST /369mart/cart/bill is mart369_cart's route, re-declared so a signed-in
customer's bill can price their points. The bill itself stays mart369_cart's;
this only says who is asking and whether they want to spend.
"""

from odoo import http
from odoo.http import request

from odoo.addons.mart369_cart.controllers.cart_api import Mart369CartApi

_GET = {'type': 'http', 'auth': 'user', 'methods': ['GET'], 'csrf': False, 'sitemap': False}

HISTORY_SHOWN = 200


class Mart369LoyaltyApi(http.Controller):

    def _json(self, payload, status=200):
        return request.make_json_response(payload, status=status)

    @http.route('/369mart/loyalty', **_GET)
    def loyalty(self, **kwargs):
        Card = request.env['pos.loyalty.card'].sudo()
        config = request.env['mart369.config'].sudo()._get()
        enabled = Card._mart369_enabled()
        rule = Card._mart369_rule()
        # Looked up, never made: a card is made by the first order that earns.
        card = Card._mart369_card_for(request.env.user.partner_id) if enabled else Card.browse()
        history = []
        if card:
            rows = request.env['pos.loyalty.history'].sudo().search(
                [('card_id', '=', card.id)], order='id desc', limit=HISTORY_SHOWN)
            # A basket that was never paid for is not history yet.
            rows = rows.filtered(lambda h: not (
                h.sale_order_id and h.sale_order_id.mart369_state == 'draft'))
            history = [row._mart369_serialize() for row in rows]
        return self._json({
            'ok': True,
            'enabled': enabled,
            'redeem': bool(config.loyalty_redeem),
            'earnOn': config.loyalty_earn_on or 'delivered',
            'settleDays': config.loyalty_settle_days,
            'card': card._mart369_serialize(rule) if card else None,
            'rule': rule._mart369_serialize() if rule else None,
            'history': history,
        })


class Mart369LoyaltyCartApi(Mart369CartApi):

    @http.route()
    def bill(self, **kwargs):
        user = request.env.user
        if not user._is_public():
            body = self._body()
            request.update_context(
                mart369_partner_id=user.partner_id.commercial_partner_id.id,
                mart369_use_points=bool(body.get('usePoints')),
            )
        return super().bill(**kwargs)
