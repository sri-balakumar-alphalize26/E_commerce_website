"""The counter's queue says which door each order came in by.

What the bridge adds to the Store's `sa_store_queue`: one `channel` key per
row, read off the order. 369 Mart › Sales › New Orders (mart369_store_board)
shows it on each card.
"""

from odoo.tests import tagged

from .common import Mart369BridgeCase


@tagged('post_install', '-at_install')
class TestStoreChannel(Mart369BridgeCase):

    def _row(self, job):
        rows = self.env['stock.picking'].sa_store_queue()['rows']
        return next((r for r in rows if r['id'] == job.id), None)

    def test_a_website_order_is_on_the_counter_as_website(self):
        order = self._web_order()
        job = self._job(order)
        self.assertEqual(job.sa_delivery_state, 'awaiting_shop', 'rings on New')
        row = self._row(job)
        self.assertTrue(row, 'a paid website order waits at the counter')
        self.assertEqual(row['channel'], 'website')
        # What the board's tabs and cards read.
        self.assertEqual(row['kind'], 'express' if order.mart369_mode == 'all' else 'quick')
        self.assertTrue(row['lines'], 'the card lists what was ordered')

    def test_a_whatsapp_order_is_on_the_counter_as_whatsapp(self):
        order = self._wa_order()
        self.assertEqual(order.mart369_channel, 'whatsapp')
        job = self._job(order)
        self.assertTrue(job, 'the WhatsApp order has its delivery job')
        row = self._row(job)
        self.assertTrue(row, 'a paid WhatsApp order waits at the same counter')
        self.assertEqual(row['channel'], 'whatsapp')

    def test_the_store_screen_still_gets_its_own_keys(self):
        """The Store app's screen reads the same method; the extra key must
        not take anything away from it."""
        row = self._row(self._job(self._web_order()))
        for key in ('state', 'ref', 'customer', 'lines', 'kind', 'paid', 'collect'):
            self.assertIn(key, row)
