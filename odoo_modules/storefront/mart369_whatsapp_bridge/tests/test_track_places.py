"""The customer's map always has something to show, its WhatsApp button always
opens a chat, and the office's live map reads what is already known.

17 Nov 2026: an order being packed on the Dubai server had no shop pin and no
customer pin, so the WhatsApp tracking page said "The map appears when your
parcel's pins are known" and nothing else, and its "Message us on WhatsApp"
linked to "#" and opened the same page again.

No network here: the address lookup is replaced, and a call to the internet
fails the test.
"""

import json
from unittest.mock import patch

from odoo.tests import tagged

from .test_order_track import Mart369BridgeHttpCase

NO_INTERNET = patch('requests.get', side_effect=AssertionError('the internet was called'))


@tagged('post_install', '-at_install')
class TestTrackPlaces(Mart369BridgeHttpCase):

    def setUp(self):
        super().setUp()
        self.Geo = type(self.env['sa.geocode.cache'])

    def _unpinned_job(self):
        """A job whose shop, warehouse, company and customer carry no pin."""
        order = self._web_order()
        job = self._job(order).sudo()
        job.sa_shop_id = False
        for warehouse in (job.picking_type_id.warehouse_id | order.warehouse_id):
            warehouse.write({'mart369_lat': 0.0, 'mart369_lng': 0.0})
            warehouse.partner_id.write({'partner_latitude': 0.0, 'partner_longitude': 0.0})
        job.company_id.partner_id.write({'partner_latitude': 0.0, 'partner_longitude': 0.0})
        job.partner_id.write({'partner_latitude': 0.0, 'partner_longitude': 0.0,
                              'street': 'Zz Street 1', 'city': 'Zz Town'})
        if 'sa_drop_lat' in job._fields:
            job.write({'sa_drop_lat': 0.0, 'sa_drop_lng': 0.0})
        return order, job

    # ------------------------------------------------------------ the pins

    def test_the_branch_pin_is_the_shop(self):
        order, job = self._unpinned_job()
        job.picking_type_id.warehouse_id.write({'mart369_lat': 25.11, 'mart369_lng': 55.21})
        with patch.object(self.Geo, 'sa_forward', return_value=(None, None)), NO_INTERNET:
            shop = job.sa_track_payload()['shop']
            self.assertEqual((shop['latitude'], shop['longitude']), (25.11, 55.21))
            self.assertFalse(shop['approximate'])
            # display only: dispatch, pay and the route still see no shop pin
            self.assertEqual(job.sa_shop_position(), (None, None))

    def test_the_order_address_pin_is_the_customer(self):
        order, job = self._unpinned_job()
        door = self.env['res.partner'].sudo().create({
            'name': 'Zz Door', 'type': 'delivery', 'parent_id': job.partner_id.id,
            'partner_latitude': 25.2, 'partner_longitude': 55.3})
        order.sudo().partner_shipping_id = door
        self.assertNotEqual(job.partner_id, door)
        with patch.object(self.Geo, 'sa_forward', return_value=(None, None)), NO_INTERNET:
            drop = job.sa_track_payload()['dropoff']
            self.assertEqual((drop['latitude'], drop['longitude']), (25.2, 55.3))
            self.assertEqual(job._sa_customer_position(), (None, None))

    def test_a_typed_address_is_an_approximate_pin_never_saved(self):
        order, job = self._unpinned_job()

        def lookup(model, text):
            return (25.3, 55.4) if 'Zz Street' in (text or '') else (None, None)

        with patch.object(self.Geo, 'sa_forward', lookup), NO_INTERNET:
            drop = job.sa_track_payload()['dropoff']
        self.assertEqual((drop['latitude'], drop['longitude']), (25.3, 55.4))
        self.assertTrue(drop['approximate'])
        self.assertFalse(job.partner_id.partner_latitude, 'never written onto the contact')

    def test_nothing_pinned_still_centres_on_the_town(self):
        order, job = self._unpinned_job()

        def lookup(model, text):
            return (23.6, 58.5) if (text or '').startswith('Zz Town') else (None, None)

        with patch.object(self.Geo, 'sa_forward', lookup), NO_INTERNET:
            payload = job.sa_track_payload()
        self.assertIsNone(payload['shop']['latitude'])
        self.assertIsNone(payload['dropoff']['latitude'])
        self.assertEqual(payload['center'], {'latitude': 23.6, 'longitude': 58.5})

    def test_the_poll_keeps_both_spellings(self):
        order, job = self._unpinned_job()
        job.picking_type_id.warehouse_id.write({'mart369_lat': 25.11, 'mart369_lng': 55.21})
        with patch.object(self.Geo, 'sa_forward', return_value=(None, None)):
            response = self.url_open('/wa/track/%s/pos?token=%s' % (job.id, job.sa_track_token))
        self.assertEqual(response.status_code, 200)
        shop = response.json()['shop']
        # `latitude` is what the page reads; it used to be dropped here
        self.assertEqual((shop['latitude'], shop['lat']), (25.11, 25.11))
        self.assertIn('center', response.json())

    def test_a_miss_is_remembered(self):
        Geo = self.env['sa.geocode.cache'].sudo()
        with patch.object(type(Geo), '_nominatim', return_value=[]) as asked:
            self.assertEqual(Geo.sa_forward('Zz Nowhere 999'), (None, None))
            self.assertEqual(Geo.sa_forward('Zz Nowhere 999'), (None, None))
        self.assertEqual(asked.call_count, 1, 'the second view does not ask again')

    # ---------------------------------------------- "Message us on WhatsApp"

    def _page(self, job):
        response = self.url_open('/wa/track/%s?token=%s' % (job.id, job.sa_track_token))
        self.assertEqual(response.status_code, 200)
        return response.text

    def test_no_shop_phone_uses_the_whatsapp_number(self):
        order, job = self._unpinned_job()
        self.wa_session.sudo().write({'phone_number': '+968 9000 1234'})
        session_id = self.wa_session.id
        with patch.object(type(job), '_sa_session',
                          lambda rec: rec.env['whatsapp.session'].sudo().browse(session_id)), \
                patch.object(self.Geo, 'sa_forward', return_value=(None, None)):
            html = self._page(job)
        self.assertIn('wa.me/96890001234', html)
        self.assertNotIn('href="#"', html)

    def test_no_number_at_all_hides_the_button(self):
        order, job = self._unpinned_job()
        with patch.object(type(job), '_sa_help_number', return_value=''), \
                patch.object(self.Geo, 'sa_forward', return_value=(None, None)):
            html = self._page(job)
        self.assertNotIn('Message us on WhatsApp</a>', html)
        self.assertNotIn('href="#"', html)

    def test_the_button_quotes_the_order_the_page_shows(self):
        order, job = self._unpinned_job()
        job.sa_shop_id = self.shop          # phone 96890000001
        with patch.object(self.Geo, 'sa_forward', return_value=(None, None)):
            html = self._page(job)
        self.assertIn('wa.me/96890000001?text=', html)

    # ---------------------------------------------------- the office's map

    def test_the_live_map_reads_known_places_only(self):
        order, job = self._unpinned_job()
        job.write({'sa_delivery_state': 'ready'})
        Geo = self.env['sa.geocode.cache'].sudo()
        texts = job._sa_address_texts(job.partner_id)
        Geo.create({'key': 'f:' + texts[0].lower()[:180], 'lat': 25.4, 'lng': 55.5})
        branch = self.env['stock.warehouse'].sudo().create({
            'name': 'Zz Branch', 'code': 'ZZBR', 'mart369_lat': 25.6, 'mart369_lng': 55.7})
        with NO_INTERNET:
            snapshot = self.env['stock.picking'].sa_fleet_snapshot()
        waiting = [w for w in snapshot['waiting'] if w['job_id'] == job.id]
        self.assertEqual((waiting[0]['latitude'], waiting[0]['longitude']), (25.4, 55.5))
        self.assertTrue(waiting[0]['approximate'])
        extra = [s for s in snapshot['shops'] if s.get('extra') and s['name'] == 'Zz Branch']
        self.assertEqual((extra[0]['latitude'], extra[0]['longitude']), (25.6, 55.7))
        self.assertEqual(extra[0]['id'], -branch.id)
        for rider in snapshot['riders']:
            self.assertIn('heading', rider)
        json.dumps(snapshot)    # the screen gets it as JSON
