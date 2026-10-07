"""The live map on the customer's own order page.

`GET /369mart/orders/<ref>/track` - polled every few seconds while the parcel
is moving. It is the signed-in twin of the delivery stack's public
`/wa/track/<id>/pos`: the same answer, but found through `_own()` like every
other order route, so it is the customer's session that opens it and the
tracking token never has to reach a browser.

Another customer's order, or a made-up number, is a 404 - not 403, which
would confirm the order exists.
"""

from odoo import http

from odoo.addons.mart369_order.controllers.order_api import Mart369OrderApi, _GET


class Mart369OrderTrackApi(Mart369OrderApi):

    @http.route('/369mart/orders/<string:ref>/track', **_GET)
    def track(self, ref, **kwargs):
        order = self._own(ref)
        if not order:
            return self._fail('No such order.', status=404)
        return self._json({'ok': True, 'track': order._mart369_track()})
