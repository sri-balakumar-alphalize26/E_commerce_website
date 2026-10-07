"""The live map on the order page, the rider's real name, and the bot.

What matters most, in order:

* the route answers only the order's owner - a 404 to anybody else - and
  never carries the delivery stack's tracking token or link;
* the rider's name is the job's rider record, cleaned - never a login, an
  email or a placeholder like the test rider's literal "rider";
* the position is withheld once the delivery is over.
"""

from datetime import timedelta

from odoo import fields
from odoo.tests import HttpCase, tagged

from .common import Mart369BridgeFixtures


class Mart369BridgeHttpCase(Mart369BridgeFixtures, HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # The fixtures keep the WhatsApp gateway session as `session`, which
        # is HttpCase's name for the browser's; `authenticate()` would try to
        # sign the gateway out. Moved aside under a name of its own.
        cls.wa_session, cls.session = cls.session, None


@tagged('post_install', '-at_install')
class TestOrderTrack(Mart369BridgeHttpCase):

    def _out_for_delivery(self):
        order = self._web_order()
        order._mart369_set_rider(self.rider_user)
        job = self._job(order)
        job.sa_shop_accept()
        job.sa_shop_ready()
        job.sa_set_state('accepted')
        job.sa_set_state('picked')
        job.sa_set_state('out_for_delivery')
        job.sudo().write({
            'sa_rider_lat': 10.35162,
            'sa_rider_lng': 77.98,
            'sa_rider_fix_on': fields.Datetime.now(),
        })
        return order, job

    def _track(self, order, login=('order.tester@369mart.test', 'order-tester-369')):
        self.authenticate(*login)
        response = self.url_open('/369mart/orders/%s/track' % order.mart369_ref)
        try:
            return response.status_code, response.json(), response.text
        except ValueError:
            return response.status_code, {}, response.text

    # ------------------------------------------------------------ the route

    def test_the_owner_sees_the_rider_moving(self):
        order, job = self._out_for_delivery()
        status, payload, __ = self._track(order)
        self.assertEqual(status, 200)
        track = payload['track']
        self.assertEqual(track['picking_id'], job.id)
        self.assertEqual(track['state'], 'out_for_delivery')
        self.assertTrue(track['live'])
        self.assertFalse(track['ended'])
        self.assertTrue(track['show_rider'])
        self.assertAlmostEqual(track['lat'], 10.35162)
        self.assertFalse(track['stale'])
        self.assertEqual(track['rider']['name'], 'Bridge Rider')
        self.assertEqual(track['rider']['phone'], '+96890000002')

    def test_another_customer_gets_a_404(self):
        order, __ = self._out_for_delivery()
        status, payload, text = self._track(
            order, ('someone.else@369mart.test', 'someone-else-369'))
        self.assertEqual(status, 404, 'not 403 - that would confirm it exists')
        self.assertFalse(payload.get('ok'))
        self.assertNotIn('Bridge Rider', text)

    def test_a_made_up_number_gets_a_404(self):
        self.authenticate('order.tester@369mart.test', 'order-tester-369')
        response = self.url_open('/369mart/orders/369M-NOSUCH/track')
        self.assertEqual(response.status_code, 404)

    def test_signed_out_is_sent_to_sign_in(self):
        order, __ = self._out_for_delivery()
        self.authenticate(None, None)
        response = self.url_open('/369mart/orders/%s/track' % order.mart369_ref,
                                 allow_redirects=False)
        self.assertIn(response.status_code, (301, 302, 303))
        self.assertIn('/web/login', response.headers.get('Location', ''))

    def test_the_tracking_token_never_leaves(self):
        order, job = self._out_for_delivery()
        token = job.sudo().sa_track_token
        self.assertTrue(token, 'the stack issued one, so there is one to leak')
        __, payload, text = self._track(order)
        self.assertNotIn(token, text)
        self.assertNotIn('/wa/track', text)

    def test_stale_after_two_minutes_without_a_fix(self):
        order, job = self._out_for_delivery()
        job.sudo().sa_rider_fix_on = fields.Datetime.now() - timedelta(seconds=300)
        __, payload, __ = self._track(order)
        self.assertTrue(payload['track']['stale'])

    def test_the_position_and_phone_are_withheld_once_delivered(self):
        order, job = self._out_for_delivery()
        job.sudo().write({'sa_delivery_state': 'delivered'})
        __, payload, __ = self._track(order)
        track = payload['track']
        self.assertTrue(track['ended'])
        self.assertFalse(track['live'])
        self.assertFalse(track['show_rider'])
        self.assertEqual((track['lat'], track['lng']), (0.0, 0.0))
        self.assertEqual(track['rider']['phone'], '')
        self.assertEqual(track['rider']['name'], 'Bridge Rider', 'Delivered by ...')

    def test_no_job_yet_is_null_not_an_error(self):
        order = self._web_order()
        # A paid order the delivery stack has not taken up (yet, or ever).
        self._job(order).sudo().write({'sa_delivery_state': 'none'})
        self.assertFalse(self._job(order))
        status, payload, __ = self._track(order)
        self.assertEqual(status, 200)
        self.assertIsNone(payload['track'])

    # ------------------------------------------------------- the rider name

    def test_name_is_capitalised_when_typed_in_one_case(self):
        order, job = self._out_for_delivery()
        job.sa_delivery_partner_id.sudo().name = 'bala kumar'
        self.assertEqual(order._mart369_rider_name(), 'Bala Kumar')
        job.sa_delivery_partner_id.sudo().name = 'McNeil'
        self.assertEqual(order._mart369_rider_name(), 'McNeil', 'typed on purpose')

    def test_placeholders_and_logins_are_not_names(self):
        order, job = self._out_for_delivery()
        rider = job.sa_delivery_partner_id.sudo()
        # Its linked contact is no fallback - on sparenix_test it is a
        # generated address record.
        rider.partner_id = self.env['res.partner'].sudo().create({'name': 'Addr A 1789648770'})
        for junk in ('rider', 'RIDER', 'bridge.rider@369mart.test', '96890000002',
                     'Addr A 1789648770'):
            rider.name = junk
            self.assertEqual(order._mart369_rider_name(), '', junk)

    def test_a_pencilled_in_rider_is_not_named(self):
        order = self._web_order()
        order._mart369_set_rider(self.rider_user)
        self.assertEqual(order._mart369_rider_name(), '',
                         'not until the rider has accepted the job')
        self.assertIsNone(order._mart369_serialize()['rider'])

    def test_the_order_json_carries_the_name(self):
        order, __ = self._out_for_delivery()
        self.assertEqual(order._mart369_serialize()['rider'], {'name': 'Bridge Rider'})

    # -------------------------------------------------------------- the bot

    def _ask(self, text):
        return self.env['mart369.bot']._mart369_reply(self.partner, text)['text']

    def test_the_bot_names_the_rider(self):
        order, __ = self._out_for_delivery()
        for question in ('who is my rider', 'who is my delivery person',
                         'delivery boy number?', 'who is delivering my order'):
            reply = self._ask(question)
            self.assertIn('Bridge Rider is delivering order #%s' % order.mart369_ref,
                          reply, question)
            self.assertNotIn('agent', reply.lower(), question)

    def test_track_my_order_mentions_the_rider(self):
        self._out_for_delivery()
        self.assertIn('Your rider is Bridge Rider.', self._ask('track my order'))

    def test_no_rider_yet(self):
        order = self._web_order()
        reply = self._ask('who is my rider')
        self.assertIn("A rider hasn't been assigned to order #%s yet" % order.mart369_ref, reply)

    def test_the_bot_never_names_another_customers_rider(self):
        self._out_for_delivery()
        stranger = self.env['res.users'].sudo().search(
            [('login', '=', 'someone.else@369mart.test')]).partner_id
        reply = self.env['mart369.bot']._mart369_reply(stranger, 'who is my rider')['text']
        self.assertNotIn('Bridge Rider', reply)
