"""The website's updates, really sent - and only to those who asked."""

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import Mart369BridgeCase


@tagged('post_install', '-at_install')
class TestNotify(Mart369BridgeCase):

    def _opted_in_order(self, **overrides):
        self.partner.mart369_notify_whatsapp = True
        self.address.phone = '+91 98765 43210'
        order = self._place(whatsapp=True, **overrides)
        return order

    def _texts(self):
        return [body for __, body in self.wa_sent]

    def test_each_state_speaks_once(self):
        order = self._opted_in_order()
        self._pay(order)                        # -> placed
        placed = [b for b in self._texts() if 'confirmed' in b]
        self.assertEqual(len(placed), 1)
        order.mart369_action_advance()          # -> packed
        self.assertEqual(len([b for b in self._texts() if 'packed' in b]), 1)

    def test_opted_out_hears_nothing(self):
        self.partner.mart369_notify_whatsapp = False
        order = self._place(whatsapp=True, ref='369M-TESTO')
        self._pay(order)
        self.assertFalse([b for b in self._texts() if 'confirmed' in b])

    def test_switch_off_silences_one_state(self):
        config = self.env['mart369.config'].sudo()._get()
        config.mart369_wa_on_placed = False
        order = self._opted_in_order(ref='369M-TESTS')
        self._pay(order)
        self.assertFalse([b for b in self._texts() if 'confirmed' in b])

    def test_custom_wording_is_used(self):
        config = self.env['mart369.config'].sudo()._get()
        config.mart369_wa_text_placed = 'Got it! %(ref)s is ours now. %(link)s'
        order = self._opted_in_order(ref='369M-TESTW')
        self._pay(order)
        self.assertTrue([b for b in self._texts()
                         if b.startswith('Got it!') and order.mart369_ref in b])

    def test_delivered_carries_the_invoice(self):
        order = self._opted_in_order(ref='369M-TESTI')
        self._pay(order)
        code = order.sudo().mart369_otp_code
        order.mart369_action_advance()
        order.mart369_action_advance()
        order.mart369_action_deliver(code)
        self.assertTrue(self.wa_documents)
        __, xmlid, record = self.wa_documents[-1]
        self.assertEqual(xmlid, 'mart369_order.action_report_mart369_invoice')
        self.assertEqual(record.move_type, 'out_invoice')

    def test_whatsapp_channel_orders_are_skipped(self):
        order = self._wa_order()
        result = self.env['mart369.whatsapp']._mart369_notify(order, 'placed')
        self.assertFalse(result)

    def test_settings_group_and_save(self):
        Config = self.env['mart369.config']
        groups = Config._mart369_admin_settings_groups()
        self.assertIn('whatsapp', groups)
        wa = groups['whatsapp']
        self.assertTrue(wa['sessions'])
        self.assertIn('placed', wa['texts'])
        Config._mart369_admin_save_group('whatsapp', {
            'sessionId': self.session.id,
            'invoice': False,
            'on': {'packed': False},
            'texts': {'out': 'On the way! %(link)s'},
        })
        config = Config.sudo()._get()
        self.assertEqual(config.mart369_wa_session_id, self.session)
        self.assertFalse(config.mart369_wa_send_invoice)
        self.assertFalse(config.mart369_wa_on_packed)
        self.assertEqual(config._mart369_wa_text('out'), 'On the way! %(link)s')

    def test_broken_placeholder_is_refused(self):
        with self.assertRaises(UserError):
            self.env['mart369.config']._mart369_admin_save_group(
                'whatsapp', {'texts': {'placed': 'Order %(nope)s placed'}})
