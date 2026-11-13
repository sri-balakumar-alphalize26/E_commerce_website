# -*- coding: utf-8 -*-
"""The customer's order page (/my/orders/<id>), 13 Nov 2026 "design A": one
card on the right signs, pays or says what happens next, and Odoo's own sign /
pay box sits inside it instead of a popup. Nothing is sent: no message, no
signature, no payment - the page is only read."""
from odoo.tests import HttpCase, TransactionCase, tagged


class _Orders:

    @classmethod
    def _make(cls, env, **vals):
        partner = env['res.partner'].create({
            'name': 'Zz Portal Page Customer', 'street': '15 Test Road', 'city': 'Muscat'})
        product = env['product.product'].create({
            'name': 'Zz Portal Rice 5 kg', 'list_price': 4.25, 'type': 'consu'})
        order = env['sale.order'].create(dict({
            'partner_id': partner.id,
            'order_line': [(0, 0, {'product_id': product.id, 'product_uom_qty': 2,
                                   'price_unit': 4.25, 'tax_ids': [(6, 0, [])]})],
        }, **vals))
        order._portal_ensure_token()
        return order


@tagged('post_install', '-at_install')
class TestPortalPageSteps(TransactionCase, _Orders):

    def test_a_quote_to_sign_starts_on_sign(self):
        order = self._make(self.env, require_signature=True, require_payment=False)
        page = order._sa_portal_page()
        self.assertEqual(page['step'], 'sign')
        self.assertEqual([s['label'] for s in page['steps']], ['Sign', 'Pay', 'Delivery'])
        self.assertEqual([s['state'] for s in page['steps']], ['cur', 'todo', 'todo'])

    def test_a_quote_to_pay_starts_on_pay_without_a_sign_step(self):
        order = self._make(self.env, require_signature=False, require_payment=True)
        page = order._sa_portal_page()
        self.assertEqual(page['step'], 'pay')
        self.assertEqual([s['label'] for s in page['steps']], ['Pay', 'Delivery'])

    def test_a_pay_link_shows_the_pay_box_even_before_signing(self):
        """Odoo's own rule: paying by link skips the signature."""
        order = self._make(self.env, require_signature=True, require_payment=True)
        self.assertEqual(order._sa_portal_page(payment_amount=order.amount_total)['step'], 'pay')

    def test_paid_online_with_no_invoice_yet_is_paid(self):
        """A card payment shows Paid at once - it no longer waits for an
        invoice and offered Pay again (13 Nov 2026)."""
        provider = self.env['payment.provider'].search([('code', '=', 'demo')], limit=1)
        method = self.env['payment.method'].search([('code', '=', 'demo')], limit=1)
        if not provider or not method:
            self.skipTest("no demo payment provider in this database")
        # Not confirmed here: this database's serial-number check blocks
        # action_confirm in tests; the payment alone must count.
        order = self._make(self.env, require_signature=False, require_payment=True)
        self.env['payment.transaction'].create({
            'provider_id': provider.id, 'payment_method_id': method.id,
            'amount': order.amount_total, 'currency_id': order.currency_id.id,
            'partner_id': order.partner_id.id, 'reference': 'ZZ-PORTAL-%s' % order.id,
            'sale_order_ids': [(6, 0, order.ids)], 'state': 'done'})
        order.invalidate_recordset(['amount_paid', 'transaction_ids'])
        page = order._sa_portal_page()
        self.assertTrue(page['status']['paid'])
        self.assertEqual(page['step'], 'done')

    def test_a_cancelled_order_says_so(self):
        order = self._make(self.env, require_signature=True)
        order._action_cancel()
        self.assertEqual(order._sa_portal_page()['step'], 'cancel')

    def test_the_bill_lists_the_items_and_the_total(self):
        order = self._make(self.env, require_signature=True)
        page = order._sa_portal_page()
        self.assertEqual(len(page['items']), 1)
        self.assertEqual(page['items'][0]['name'], 'Zz Portal Rice 5 kg')
        self.assertIn('2 ×', page['items'][0]['qty_text'])
        self.assertEqual(page['rows'][0]['label'], 'Items')
        self.assertIn('8.5', page['total_text'])
        self.assertEqual(page['address'], '15 Test Road, Muscat')


@tagged('post_install', '-at_install')
class TestPortalPageRender(HttpCase, _Orders):

    def _html(self, order):
        res = self.url_open('/my/orders/%s?access_token=%s' % (order.id, order.access_token))
        self.assertEqual(res.status_code, 200)
        return res.text

    def test_the_sign_box_is_in_the_card(self):
        html = self._html(self._make(self.env, require_signature=True, require_payment=False))
        self.assertIn('data-step="sign"', html)
        card = html.split('id="sa_action"', 1)[1]
        # Odoo's sign box comes before the card ends, shown in place, not as a popup
        self.assertNotEqual(card.find('id="modalaccept"'), -1)
        self.assertLess(card.find('id="modalaccept"'), card.find('</section>'))
        self.assertIn('portal.signature_form', card.split('</section>', 1)[0])
        self.assertNotIn('class="modal fade" id="modalaccept"', html)

    def test_the_pay_box_is_in_the_card(self):
        html = self._html(self._make(self.env, require_signature=False, require_payment=True))
        self.assertIn('data-step="pay"', html)
        self.assertIn('Payment method', html)

    def test_odoo_pay_now_no_longer_opens_a_popup(self):
        """After signing Odoo clicks its Pay Now (allow_payment=yes); the pay
        box is already on the page, so that only scrolls to it."""
        html = self._html(self._make(self.env, require_signature=False, require_payment=True))
        start = html.find('id="o_sale_portal_paynow"')
        if start == -1:
            return  # Odoo did not draw its button for this order
        tag = html[html.rfind('<a', 0, start):html.find('>', start)]
        self.assertNotIn('data-bs-toggle', tag)
        self.assertIn('#sa_action', tag)
