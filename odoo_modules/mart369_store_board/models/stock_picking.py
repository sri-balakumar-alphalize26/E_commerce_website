"""The counter's queue, with each order as All orders draws it.

`sa_store_queue` (sales_automation_store) is the counter's own read: state,
kind, the ordered lines, paid / to collect, rider, pickup code - and, with
mart369_whatsapp_bridge installed, the channel. This adds the order in the
exact shape mart369_order's All orders list uses (`_mart369_admin_row`), so
the Odoo Counter and the console's Counter draw the same rows as All orders
- one look for the same orders.

One place for both screens: the Odoo Counter calls this over the ORM, and
the console's /369mart/admin/counter (controllers/counter_api.py) serves it.
"""

import logging

from odoo import api, models

_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    @api.model
    def mart369_counter(self, shop_id=None):
        queue = self.sa_store_queue(shop_id)
        ids = [r['order_id'] for r in queue.get('rows', []) if r.get('order_id')]
        drawn = {}
        for order in self.env['sale.order'].sudo().browse(ids).exists():
            try:
                drawn[order.id] = order._mart369_admin_row()
            except Exception:  # noqa: BLE001 - one odd order must not blank the counter
                _logger.exception('counter: could not draw %s', order.name)
        rows = [dict(r, order=drawn.get(r.get('order_id'))) for r in queue.get('rows', [])]
        return dict(queue, rows=rows, shops=self.sa_store_shops())

    @api.model
    def mart369_counter_ringing(self):
        """What the app-wide alarm needs, and nothing more: how many orders
        wait for somebody to press Accept, and the ring cadence from Delivery
        Settings. Polled from every screen, so kept to one count."""
        waiting = self.sudo().search_count([
            ('sa_delivery_state', '=', 'awaiting_shop'),
            ('sa_supply_waiting', '=', False),
        ])
        settings = self.env['sa.delivery.settings'].sudo().get_settings()
        return {
            'ringing': waiting,
            'ring': max(3, settings.alarm_ring_seconds or 30),
            'repeat': max(3, settings.alarm_repeat_seconds or 10),
        }
