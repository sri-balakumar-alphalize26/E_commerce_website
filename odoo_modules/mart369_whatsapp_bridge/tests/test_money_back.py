"""Money back on WhatsApp orders (money_back.py)."""

from odoo.tests import tagged

from .common import Mart369BridgeCase


@tagged('post_install', '-at_install')
class TestMoneyBack(Mart369BridgeCase):

    def _cancel(self, order):
        order.with_context(disable_cancel_warning=True).action_cancel()

    def _rows(self, order):
        return self.env['loyalty.history'].sudo().search([
            ('order_model', '=', 'sale.order'), ('order_id', '=', order.id),
            ('mart369_kind', '=', 'refund')])

    def _notes(self, order):
        return order.invoice_ids.filtered(
            lambda m: m.move_type == 'out_refund' and m.state == 'posted')

    def _wallet(self, order):
        card = self.env['loyalty.card'].sudo()._mart369_wallet(order.partner_id)
        card.invalidate_recordset(['points'])
        return card

    # ------------------------------------------------------------ cancelled

    def test_a_paid_whatsapp_order_cancelled_goes_back_to_the_wallet(self):
        order = self._wa_order(phone='+917009920001')
        self.assertEqual(order.mart369_channel, 'whatsapp')
        paid = order.amount_total
        self.assertAlmostEqual(order._mart369_refundable(), paid, places=2,
                               msg='paid through the invoice counts as paid')
        self._cancel(order)

        row = self._rows(order)
        self.assertEqual(len(row), 1)
        self.assertAlmostEqual(row.issued, paid, places=2)
        self.assertEqual(row.mart369_sub, 'Order %s' % order.name,
                         'labelled with the Odoo number, not an empty 369M-')
        self.assertTrue(row.mart369_move_id, 'booked in the wallet journal')
        self.assertAlmostEqual(self._wallet(order).points, paid, places=2)

        note = self._notes(order)
        self.assertEqual(len(note), 1)
        self.assertTrue(note.currency_id.is_zero(note.amount_residual),
                        'the credit note is settled by the wallet refund')
        self.assertTrue(any('refunded to your 369 Wallet' in body
                            for __, body in self.wa_sent), 'the customer is told')

    def test_it_is_refunded_once_whatever_else_is_pressed(self):
        order = self._wa_order(phone='+917009920002')
        self._cancel(order)
        job = order.picking_ids.filtered(lambda p: p.picking_type_code == 'outgoing')[:1]
        job.sa_action_refund()
        order._mart369_wa_money_back('Again')
        self.assertEqual(len(self._rows(order)), 1)
        self.assertEqual(len(self._notes(order)), 1, 'never a second credit note')
        self.assertAlmostEqual(self._wallet(order).points, order.amount_total, places=2)

    def test_an_unpaid_whatsapp_order_cancelled_loses_its_bill(self):
        order = self._wa_order(phone='+917009920003', paid=False)
        invoice = order._create_invoices()
        invoice.action_post()
        self.assertEqual(invoice.payment_state, 'not_paid')
        self._cancel(order)
        self.assertEqual(invoice.payment_state, 'reversed', 'the bill no longer stands')
        self.assertFalse(self._rows(order), 'nothing was paid, nothing comes back')

    # ------------------------------------------------------------- returned

    def test_a_returned_parcel_is_refunded(self):
        order = self._wa_order(phone='+917009920004')
        job = self._job(order)
        self.assertTrue(job)
        job.write({'sa_delivery_state': 'returned'})
        row = self._rows(order)
        self.assertEqual(len(row), 1)
        self.assertAlmostEqual(order.mart369_returned_refund, order.amount_total, places=2)
        job.write({'sa_delivery_state': 'returned'})
        self.assertEqual(len(self._rows(order)), 1, 'once')

    # ------------------------------------------------- the Store's Refund button

    def test_the_refund_button_uses_the_wallet(self):
        order = self._wa_order(phone='+917009920005')
        job = order.picking_ids.filtered(lambda p: p.picking_type_code == 'outgoing')[:1]
        moves = job.sa_action_refund()
        self.assertEqual(len(self._rows(order)), 1)
        self.assertEqual(len(self._notes(order)), 1)
        self.assertEqual(job.sa_refund_move_id, self._notes(order))
        self.assertEqual(moves, self._notes(order))
        job.sa_action_refund()
        self.assertEqual(len(self._notes(order)), 1, 'pressed twice, credited once')

    def test_a_whatsapp_only_customer_gets_a_wallet_too(self):
        order = self._wa_order(phone='+917009920006')
        self.assertFalse(order.partner_id.user_ids, 'no website account')
        self._cancel(order)
        self.assertAlmostEqual(self._wallet(order).points, order.amount_total, places=2)
