"""The Counter, for the web admin console (components/admin/AdminCounter.jsx).

Same answers as the Odoo Counter screen - it is the Store's own
`sa_store_queue` and `sa_store_act` underneath - so an order accepted in the
console is accepted at the counter, and the other way round.

Each row also carries the order exactly as the console's All orders list
draws it (`_mart369_admin_row`, bridge-extended for WhatsApp orders), so the
two lists share one look, and a click opens the same order drawer.

Same shape as mart369_order's admin routes: type='http' answering bare JSON,
failures as {ok: false, error}, staff only.
"""

import logging

from odoo import http
from odoo.exceptions import AccessError, UserError
from odoo.http import request

_logger = logging.getLogger(__name__)

_GET = {'type': 'http', 'auth': 'user', 'methods': ['GET'], 'csrf': False, 'sitemap': False}
_POST = {'type': 'http', 'auth': 'user', 'methods': ['POST'], 'csrf': False, 'sitemap': False}

# What the console's buttons may do - the Odoo Counter's own, Cancel included.
# A cancel is the Store's (`sa_action_cancel`); the bridge then runs the website
# order's own cancel or return, refund and all, as it does from the Odoo Counter.
ACTIONS = ('accept', 'ready', 'unaccept', 'cancel')


class Mart369CounterApi(http.Controller):

    def _json(self, payload, status=200):
        return request.make_json_response(payload, status=status)

    def _fail(self, error, status=400):
        return self._json({'ok': False, 'error': error}, status=status)

    def _body(self):
        try:
            data = request.get_json_data()
        except Exception:  # noqa: BLE001 - an empty or broken body is just "no body"
            data = None
        return data if isinstance(data, dict) else {}

    def _may_use(self):
        """Who works the counter: the same people who may see the orders."""
        user = request.env.user
        return (user.has_group('website.group_website_designer')
                or user.has_group('sales_team.group_sale_salesman'))

    def _rows(self, queue):
        """The counter's rows (models/stock_picking.py) in the console's words."""
        rows = []
        for r in queue.get('rows', []):
            rows.append({
                'job': r['id'],
                'code': r.get('ref') or '',
                'counter': r.get('state') or '',
                'kind': r.get('kind') or '',
                'channel': r.get('channel') or '',
                'lines': r.get('lines') or [],
                'paid': bool(r.get('paid')),
                'collect': r.get('collect') or 0.0,
                'rider': r.get('rider') or '',
                'pickupCode': r.get('pickup_code') or '',
                'waiting': r.get('waiting') or 0,
                'supplyWaiting': bool(r.get('supply_waiting')),
                'canCancel': bool(r.get('can_cancel')),
                'invoicePaid': bool(r.get('invoice_paid')),
                'customer': r.get('customer') or '',
                'address': r.get('address') or '',
                'order': r.get('order'),
            })
        return rows

    @http.route('/369mart/admin/counter', **_GET)
    def counter(self, shop=None, **kwargs):
        if not self._may_use():
            return self._fail('You do not have access to this.', status=403)
        Picking = request.env['stock.picking']
        try:
            shop_id = int(shop) if shop else None
        except (TypeError, ValueError):
            shop_id = None
        queue = Picking.mart369_counter(shop_id)
        return self._json({
            'ok': True,
            'rows': self._rows(queue),
            'ringing': queue.get('ringing', 0),
            'packing': queue.get('packing', 0),
            'ring': queue.get('ring', 30),
            'repeat': queue.get('repeat', 10),
            'shops': queue.get('shops', []),
        })

    @http.route('/369mart/admin/counter/<int:job_id>', **_POST)
    def act(self, job_id, **kwargs):
        if not self._may_use():
            return self._fail('You do not have access to this.', status=403)
        action = (self._body().get('action') or '').strip()
        if action not in ACTIONS:
            return self._fail('That is not something the counter can do.')
        try:
            request.env['stock.picking'].sa_store_act(job_id, action)
        except (UserError, AccessError) as exc:
            return self._fail(str(exc))
        return self._json({'ok': True})
