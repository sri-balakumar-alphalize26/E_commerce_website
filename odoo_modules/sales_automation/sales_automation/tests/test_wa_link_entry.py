# -*- coding: utf-8 -*-
"""A pay link opens the order's payment page in one hop fewer (17 Nov 2026).

`/wa/pay/<id>` only redirects to the order's portal page, so the doorway now
sends the customer there itself: on a slow server every hop is about a second.
A wrong token still goes the old way and still gets its 404."""
from urllib.parse import urlsplit

from odoo.tests import HttpCase, tagged

from .test_portal_page import _Orders


@tagged('post_install', '-at_install')
class TestWaLinkEntry(HttpCase, _Orders):

    def _open(self, order_id, token):
        url = '/scoped_app/wa-link?db=%s&to=/wa/pay/%s?method=upi%%26token=%s' % (
            self.env.cr.dbname, order_id, token)
        return self.url_open(url)

    def test_a_pay_link_skips_the_wa_pay_hop(self):
        order = self._make(self.env)
        response = self._open(order.id, order.access_token)
        hops = [r.headers.get('Location', '') for r in response.history]
        self.assertFalse([h for h in hops if '/wa/pay/' in h], hops)
        self.assertTrue(urlsplit(response.url).path.startswith('/my/orders/%s' % order.id), response.url)

    def test_a_wrong_token_still_goes_the_old_way(self):
        order = self._make(self.env)
        response = self._open(order.id, 'not-the-token')
        hops = [r.headers.get('Location', '') for r in response.history]
        self.assertTrue([h for h in hops if '/wa/pay/' in h], hops)
        self.assertEqual(response.status_code, 404)
