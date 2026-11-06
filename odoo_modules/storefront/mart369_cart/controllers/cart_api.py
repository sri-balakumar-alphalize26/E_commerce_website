"""The bill, the delivery rules, serviceability and the slots.

All public: a shopper fills a basket, checks a pincode and sees a total long
before they sign in, and the app has always let them.

The one that matters is POST /369mart/cart/bill. Until now the browser decided
what it owed; from here the server does, and mart369_order will place an order
by asking this same code rather than trusting a number the app sends.
"""

import logging

from odoo import http
from odoo.http import request

from odoo.addons.mart369.controllers.public import _PUBLIC_JSON

_logger = logging.getLogger(__name__)

# The bill is a POST because a basket is too big for a query string, but it
# changes nothing, so it stays on the read-only cursor.
_PUBLIC_POST = dict(_PUBLIC_JSON, methods=['POST'])


class Mart369CartApi(http.Controller):

    def _body(self):
        try:
            data = request.get_json_data()
        except Exception:  # noqa: BLE001 - an empty or broken body is just {}
            data = None
        return data if isinstance(data, dict) else {}

    def _cached(self, payload):
        config = request.env['mart369.config'].sudo()._get()
        return request.make_json_response(payload, headers=[
            ('Cache-Control', 'public, max-age=%d' % max(config.cache_seconds or 0, 0)),
        ])

    # ---------------------------------------------------------- the rules

    @http.route('/369mart/cart/rules', **_PUBLIC_JSON)
    def rules(self, **kwargs):
        """CART_RULES and COUPONS, as the cart page and offers page want them.

        Shape: {"rules": {"quick": {...}, "all": {...}}, "coupons": [...]}
        """
        Rule = request.env['mart369.delivery.rule'].sudo()
        Coupon = request.env['mart369.coupon'].sudo()
        return self._cached({
            'rules': {mode: rule._mart369_serialize()
                      for mode, rule in Rule._mart369_rules().items()},
            'coupons': [c._mart369_serialize() for c in Coupon.search([])
                        if c._mart369_live()],
        })

    # ----------------------------------------------------------- the bill

    @http.route('/369mart/cart/bill', **_PUBLIC_POST)
    def bill(self, **kwargs):
        """What this basket costs.

        Body: {"items": {"<product id>": qty, ...}, "coupon": "QUICK20",
               "slotFee": 49, "addressId": 42}

        `addressId` is optional. With it, each line is Quick or Express for
        that address - see `_mart369_bill` - and `modes` says which.
        """
        body = self._body()
        items = body.get('items')
        if not isinstance(items, dict):
            return request.make_json_response(
                {'ok': False, 'error': 'Send the basket as items.'}, status=400)
        try:
            slot_fee = float(body.get('slotFee') or 0.0)
        except (TypeError, ValueError):
            slot_fee = 0.0

        bill = request.env['mart369.cart'].sudo()._mart369_bill(
            items, coupon=body.get('coupon'), slot_fee=slot_fee,
            address=self._own_address(body.get('addressId')))
        bill['ok'] = True
        return request.make_json_response(bill)

    def _own_address(self, address_id):
        """The signed-in customer's own address, or nothing.

        Someone else's id - or any id from a guest - is quietly ignored rather
        than refused: the bill still adds up, it just cannot say which items
        are Quick where. Placing the order checks the address properly.
        """
        Partner = request.env['res.partner']
        user = request.env.user
        if not address_id or user._is_public():
            return Partner.browse()
        try:
            address = Partner.sudo().browse(int(address_id)).exists()
        except (TypeError, ValueError):
            return Partner.browse()
        if not address or address.parent_id != user.partner_id:
            return Partner.browse()
        return address

    # ------------------------------------------------------ serviceability

    @http.route('/369mart/serviceability', **_PUBLIC_JSON)
    def serviceability(self, pin=None, **kwargs):
        """Exactly what `demoCheck` answered, so the picker is unchanged:
        {ok: true, quick: bool, eta: str} or {ok: false, error: str}."""
        answer = request.env['mart369.service.area'].sudo()._mart369_check(pin)
        return request.make_json_response(answer, status=200 if answer['ok'] else 200)

    # ----------------------------------------------------------- the slots

    @http.route('/369mart/slots', **_PUBLIC_JSON)
    def slots(self, **kwargs):
        """{"quick": [chip, ...], "all": [chip, ...]} - the shape useSlots()
        built from the browser clock."""
        return request.make_json_response(
            request.env['mart369.delivery.slot'].sudo()._mart369_slots())
