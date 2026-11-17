"""The product link's pictures come small and stay cached (17 Nov 2026).

The page used to send every picture, thumbnails too, at full size, and to
decode every full-size photo for the page and again for each picture asked
for - slow on a phone. Now: 1024 px on the page, 256 px in the strip, the
original only for the full-screen view, one picture read per request, and an
address that carries the picture's checksum so it is kept for a year."""
import base64
import io
import re
from unittest.mock import patch

from PIL import Image

from odoo.tests import HttpCase, tagged


def big_png(shade, side=1500):
    out = io.BytesIO()
    Image.new('RGB', (side, side), (shade, 60, 120)).save(out, format='PNG')
    return base64.b64encode(out.getvalue())


@tagged('post_install', '-at_install')
class TestConfirmPictureSizes(HttpCase):

    def setUp(self):
        super().setUp()
        self.env['ir.config_parameter'].sudo().set_param('ai369_image_server.enabled', 'False')
        session = self.env['whatsapp.session'].sudo().create({
            'name': 'Sizes Test Session', 'gateway_api_key': 'sizes-test-key'})
        group = self.env['sa.sales.group'].sudo().create({
            'name': 'Sizes Test Group', 'group_jid': 'sizes-test@g.us',
            'session_id': session.id, 'group_type': 'customer'})
        Product = self.env['product.template'].sudo()
        if 'product_template_image_ids' not in Product._fields:
            self.skipTest('website_sale is not installed')
        self.product = Product.create({'name': 'Zz Sizes Kettle', 'image_1920': big_png(10)})
        self.env['product.image'].sudo().create({
            'name': 'Side', 'image_1920': big_png(20), 'product_tmpl_id': self.product.id})
        request = self.env['sa.group.request'].sudo().create({
            'group_id': group.id, 'requester_phone': '+96890000078',
            'raw_text': self.product.name, 'product_id': self.product.id})
        self.link = self.env['sa.confirm.link'].sudo().create({'request_id': request.id, 'kind': 'customer'})

    def _width(self, response):
        return Image.open(io.BytesIO(response.content)).size[0]

    def test_nothing_is_decoded_to_build_the_page(self):
        module = 'odoo.addons.sales_automation_confirm.models.sa_confirm_link.base64.b64decode'
        with patch(module, side_effect=AssertionError('a picture was decoded')):
            entries = self.link._picture_entries()
        self.assertEqual(len(entries), 2)

    def test_the_page_asks_for_small_pictures(self):
        html = self.url_open('/wa/confirm/%s' % self.link.token).text
        self.assertIn('/image/0.jpg?s=1024&amp;v=', html)
        self.assertIn('/image/1.jpg?s=256&amp;v=', html)
        self.assertIn('fetchpriority="high"', html)
        self.assertIn('loading="lazy"', html)

    def test_each_size_is_its_size_and_kept_for_a_year(self):
        version = self.link._picture_entries()[0]['version']
        base = '/wa/confirm/%s/image/0.jpg' % self.link.token
        small = self.url_open('%s?s=256&v=%s' % (base, version))
        self.assertEqual(small.status_code, 200)
        self.assertLessEqual(self._width(small), 256)
        self.assertIn('max-age=31536000', small.headers.get('Cache-Control', ''))
        self.assertIn('public', small.headers.get('Cache-Control', ''))
        page = self.url_open('%s?s=1024&v=%s' % (base, version))
        self.assertLessEqual(self._width(page), 1024)
        self.assertGreater(len(self.url_open(base).content), len(page.content), 'the original is the big one')

    def test_an_address_without_the_checksum_is_kept_briefly(self):
        response = self.url_open('/wa/confirm/%s/image/0?s=256' % self.link.token)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('31536000', response.headers.get('Cache-Control', ''))

    def test_the_old_addresses_still_answer(self):
        for path in ('/image', '/image/0', '/image/1'):
            response = self.url_open('/wa/confirm/%s%s' % (self.link.token, path))
            self.assertEqual(response.status_code, 200, path)
        self.assertEqual(self.url_open('/wa/confirm/%s/image/7' % self.link.token).status_code, 404)

    def test_image_server_pictures_are_linked_straight(self):
        """No stop at this server first: the image server's own addresses,
        its thumbnail in the strip - and nothing downloaded to build the page."""
        Attachment = self.env['ir.attachment'].sudo()
        if 'imgsrv_url' not in Attachment._fields:
            self.skipTest('ai369_image_server is not installed')
        self.env.flush_all()    # the smaller sizes are written on flush
        for record in (self.product, self.product.product_template_image_ids):
            for att in Attachment.search([('res_model', '=', record._name), ('res_id', '=', record.id),
                                          ('res_field', '!=', False)]):
                att._imgsrv_set('imgsrv:m:products/zz/%s.webp?v=1' % att.id,
                                'https://images.example.test/p/%s/%s/%s.webp' % (record._name, record.id, att.res_field),
                                'link|products/zz/%s.webp' % att.id, checksum='sum%s' % att.id)
        self.env.invalidate_all()
        with patch.object(type(Attachment), '_imgsrv_read', side_effect=AssertionError('a download')):
            html = self.url_open('/wa/confirm/%s' % self.link.token).text
        main = 'https://images.example.test/p/product.template/%s/image_1920.webp' % self.product.id
        side = self.product.product_template_image_ids
        self.assertIn('src="%s"' % main, html)
        self.assertIn('https://images.example.test/p/product.image/%s/image_256.webp' % side.id, html)
        self.assertNotIn('/wa/confirm/%s/image/' % self.link.token, html)

    def test_the_strip_shows_and_swaps_the_right_sizes(self):
        html = self.url_open('/wa/confirm/%s' % self.link.token).text
        thumbs = re.findall(r'<img src="[^"]*s=256[^"]*" data-big="([^"]*)" data-full="([^"]*)"', html)
        self.assertEqual(len(thumbs), 2)
        for big, full in thumbs:
            self.assertIn('s=1024', big)
            self.assertNotIn('s=', full)
