# -*- coding: utf-8 -*-
"""Customer pages never download a picture kept on the image server (17 Nov 2026).

The order / pay page and the review page put their pictures inline, which made
Odoo download every picture from the image server before answering. A picture
kept there is now linked straight to it; a picture kept in Odoo is shown inline
exactly as before. Any download here fails the test."""
import base64
import io
from unittest.mock import patch

from PIL import Image

from odoo.tests import TransactionCase, tagged

from .test_portal_page import _Orders


def png(shade):
    out = io.BytesIO()
    Image.new('RGB', (8, 8), (shade, 30, 60)).save(out, format='PNG')
    return base64.b64encode(out.getvalue())


@tagged('post_install', '-at_install')
class TestSaPicture(TransactionCase, _Orders):

    def setUp(self):
        super().setUp()
        self.Attachment = self.env['ir.attachment'].sudo()
        if 'imgsrv_url' not in self.Attachment._fields:
            self.skipTest('ai369_image_server is not installed')
        self.env['ir.config_parameter'].sudo().set_param('ai369_image_server.enabled', 'False')
        self.order = self._make(self.env)
        self.product = self.order.order_line.product_id
        self.product.product_tmpl_id.image_1920 = png(5)

    def _on_the_image_server(self, template):
        """Every size of the template's picture, as the connector files them."""
        self.env.flush_all()    # the smaller sizes are written on flush
        for att in self.Attachment.search([('res_model', '=', template._name), ('res_id', '=', template.id),
                                           ('res_field', '!=', False)]):
            att._imgsrv_set('imgsrv:m:products/zz/%s.webp?v=1' % att.id,
                            'https://images.example.test/products/zz/%s.webp' % att.res_field,
                            'link|products/zz/%s.webp' % att.id)
        template.env.invalidate_all()

    def _no_download(self):
        return patch.object(type(self.Attachment), '_imgsrv_read', side_effect=AssertionError('a download'))

    def test_the_order_page_links_the_image_server(self):
        self._on_the_image_server(self.product.product_tmpl_id)
        with self._no_download():
            items = self.order._sa_portal_page()['items']
        self.assertEqual(items[0]['picture'], 'https://images.example.test/products/zz/image_128.webp')

    def test_a_picture_kept_in_odoo_is_shown_as_before(self):
        items = self.order._sa_portal_page()['items']
        self.assertTrue(items[0]['picture'].startswith('data:image/'), 'inline, as the page always did')

    def test_no_picture_is_no_picture(self):
        self.product.product_tmpl_id.image_1920 = False
        self.assertEqual(self.order._sa_portal_page()['items'][0]['picture'], '')

    def test_the_review_page_links_the_image_server(self):
        self._on_the_image_server(self.product.product_tmpl_id)
        with self._no_download():
            item = self.order._sa_review_items()[0]
        self.assertEqual(item['picture'], 'https://images.example.test/products/zz/image_128.webp')
        self.assertEqual(item['image'], 'https://images.example.test/products/zz/image_256.webp')

    def test_has_asks_without_downloading(self):
        self._on_the_image_server(self.product.product_tmpl_id)
        with self._no_download():
            self.assertTrue(self.env['sa.picture'].has(self.product.product_tmpl_id, 'image_128'))

    def test_connect_early_only_when_the_image_server_is_on(self):
        Picture = self.env['sa.picture']
        self.assertEqual(str(Picture.preconnect_html()), '')
        params = self.env['ir.config_parameter'].sudo()
        params.set_param('ai369_image_server.enabled', 'True')
        params.set_param('ai369_image_server.url', 'https://images.example.test/')
        html = str(Picture.preconnect_html())
        self.assertIn('<link rel="preconnect" href="https://images.example.test">', html)
        self.assertNotIn('crossorigin', html, 'plain <img> loads reuse only a plain connection')
