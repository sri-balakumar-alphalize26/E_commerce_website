"""Fixtures for the bridge tests.

Everything network-shaped is mocked: the WhatsApp gateway (no server runs on
this machine - and a test that needs one is a test nobody runs), and the
outbox guard, whose real implementation commits on its *own* database
connection and would leave rows behind a rolled-back test.

The order fixtures are mart369_order's own, reused - the bridge's whole point
is that both stacks keep working, so its tests should order the way the
website really orders.
"""

from unittest.mock import patch

from odoo.tests import TransactionCase

from odoo.addons.mart369_order.tests.common import Mart369OrderFixtures


class Mart369BridgeFixtures(Mart369OrderFixtures):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        env = cls.env

        # ------------------------------------------------ the mocked gateway
        cls.wa_sent = []          # (phone, body) of every text "sent"
        cls.wa_documents = []     # (phone, xmlid, record) of every PDF

        Session = env.registry['whatsapp.session']

        def send_message(self, phone, message):
            cls.wa_sent.append((phone, message))
            return True

        def send_odoo_report(self, phone, report_xmlid, record, caption=''):
            cls.wa_documents.append((phone, report_xmlid, record))
            return True

        def send_text_mentioning(self, phone, message, mention=''):
            # The group flow's `_say` takes this door when it can @-mention.
            cls.wa_sent.append((phone, message))
            return True

        cls._wa_patchers = [
            patch.object(Session, 'send_message', send_message),
            patch.object(Session, 'sa_send_text_mentioning',
                         send_text_mentioning),
            patch.object(Session, 'send_odoo_report', send_odoo_report),
            patch.object(Session, 'send_document',
                         lambda self, *a, **kw: True),
            # Polls, buttons and anything else all leave through here.
            patch.object(Session, '_send_payload',
                         lambda self, *a, **kw: True),
            patch.object(Session, '_gateway_call',
                         lambda self, *a, **kw: {}),
            patch.object(Session, '_refresh_state',
                         lambda self, force=False: True),
            # The real guard commits on its own connection; a test must not.
            patch.object(env.registry['sa.outbox.guard'], 'claim',
                         lambda self, key, seconds=60: True),
            patch.object(env.registry['sa.outbox.guard'], 'release',
                         lambda self, key: True),
        ]
        for patcher in cls._wa_patchers:
            patcher.start()
            cls.addClassCleanup(patcher.stop)

        cls.session = env['whatsapp.session'].sudo().create({
            'name': 'Bridge Test Session',
            'gateway_api_key': 'bridge-test-key',
        })
        cls.session.sudo().write({'status': 'connected'})

        # ------------------------------------------------- the WhatsApp side
        cls.wa_group = env['sa.sales.group'].sudo().create({
            'name': 'Bridge Test Shop Group',
            'group_jid': 'bridge-test@g.us',
            'session_id': cls.session.id,
            'group_type': 'customer',
        })
        cls.shop = env['sa.delivery.shop'].sudo().create({
            'name': 'Bridge Test Counter',
            'phone': '96890000001',
            'warehouse_id': env['stock.warehouse'].search(
                [('company_id', '=', env.company.id)], limit=1).id,
        })

        # The counter takes every order first, as it does on the live shop.
        env['sa.delivery.settings'].sudo().get_settings().shop_confirms = True

        # A console rider: a user with the Rider role and a phone.
        cls.rider_user = env['res.users'].sudo().create({
            'name': 'Bridge Rider',
            'login': 'bridge.rider@369mart.test',
            'email': 'bridge.rider@369mart.test',
            'group_ids': [(4, env.ref('mart369_roles.group_rider').id),
                          (4, env.ref('base.group_user').id)],
        })
        cls.rider_user.partner_id.phone = '+96890000002'

    def setUp(self):
        super().setUp()
        self.wa_sent.clear()
        self.wa_documents.clear()

    # -------------------------------------------------------------- helpers

    @classmethod
    def _wa_order(cls, product=None, qty=2, confirm=True, paid=True,
                  phone='+919876500001'):
        """A sale order the way the WhatsApp flow leaves one: linked to a
        group enquiry, no mart369_ref, confirmed (which makes the job) and
        paid (which is what lets the counter's Ready button through)."""
        env = cls.env
        product = product or cls.quick_product
        partner = env['res.partner'].sudo().create({
            'name': 'WA Customer %s' % phone[-4:],
            'phone': phone,
        })
        request = env['sa.group.request'].sudo().create({
            'group_id': cls.wa_group.id,
            'requester_phone': phone,
            'requester_name': partner.name,
            'raw_text': product.name,
        })
        order = env['sale.order'].sudo().create({
            'partner_id': partner.id,
            'sa_group_request_id': request.id,
            'order_line': [(0, 0, {
                'product_id': product.product_variant_id.id,
                'product_uom_qty': qty,
            })],
        })
        if confirm:
            order.action_confirm()
        if confirm and paid:
            invoice = order._create_invoices()
            invoice.action_post()
            env['account.payment.register'].with_context(
                active_model='account.move', active_ids=invoice.ids,
            ).create({}).action_create_payments()
        return order

    def _web_order(self, cash=False, **overrides):
        """A paid website order, jobs and all."""
        order = self._place(**overrides)
        if cash:
            self._cash(order)
        else:
            self._pay(order)
        return order

    @staticmethod
    def _job(order):
        return order._mart369_bridge_job()


class Mart369BridgeCase(Mart369BridgeFixtures, TransactionCase):
    pass
