"""Direct Image Server links, small pictures and the search box.

The tests that matter most:

* test_kept_in_odoo_keeps_its_usual_address - most shops have pictures still in
  Odoo. They must keep the address that works.
* test_on_image_server_gets_a_direct_link - and the version must be on it, or a
  replaced picture hides behind the old copy for 30 days.
* test_suggest_is_a_thin_card - the row must not carry `images`: the app merges
  it over any full card it holds, and would cut that card's gallery to one photo.
"""

import base64
import io
import json

from PIL import Image

from odoo.tests import tagged
from odoo.tests.common import HttpCase

HEADERS = {'Content-Type': 'application/json'}


def picture():
    out = io.BytesIO()
    Image.new('RGB', (600, 600), (200, 30, 30)).save(out, format='PNG')
    return base64.b64encode(out.getvalue())


@tagged('post_install', '-at_install')
class TestFastPicturesSearch(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.helper = cls.env['mart369.serializable'].sudo()
        cls.Template = cls.env['product.template'].sudo()
        cls.switch = cls.Template.create({
            'name': 'Zqx Gigabit Switch', 'is_published': True, 'list_price': 100,
            'image_1920': picture(), 'mart_brand': 'Zqxlink',
        })

    def _on_image_server(self, record, field):
        """Point one of a record's picture files at the Image Server, as the
        connector does."""
        if 'imgsrv_url' not in self.env['ir.attachment']._fields:
            self.skipTest('The Image Server connector is not installed.')
        attachment = self.env['ir.attachment'].sudo().search([
            ('res_model', '=', record._name), ('res_id', '=', record.id), ('res_field', '=', field),
        ], limit=1)
        self.assertTrue(attachment, 'The picture should have a file of its own.')
        url = 'https://images.example.com/%s/%s.webp' % (record.id, field)
        attachment.flush_recordset()
        self.env.cr.execute(
            "UPDATE ir_attachment SET store_fname=%s, imgsrv_url=%s, imgsrv_state='remote' WHERE id=%s",
            ('imgsrv:m:media/x.webp?v=abc123#512', url, attachment.id))
        attachment.invalidate_recordset()
        return url

    def _get(self, url):
        response = self.url_open(url, headers=HEADERS)
        self.assertEqual(response.status_code, 200)
        return json.loads(response.text)

    # --------------------------------------------------------- the pictures

    def test_kept_in_odoo_keeps_its_usual_address(self):
        url = self.helper._image_url('image_512', '512x512', record=self.switch)
        self.assertTrue(url.startswith('/web/image/product.template/%d/image_512/' % self.switch.id), url)
        self.assertIn('unique=', url)

    def test_on_image_server_gets_a_direct_link(self):
        direct = self._on_image_server(self.switch, 'image_512')
        self.assertEqual(self.helper._image_url('image_512', '512x512', record=self.switch),
                         direct + '?v=abc123')

    def test_small_version_is_looked_up_on_its_own(self):
        direct = self._on_image_server(self.switch, 'image_256')
        self.assertEqual(self.helper._mart369_thumb_url(self.switch), direct + '?v=abc123')
        # The full size has not moved, so it keeps the usual address.
        self.assertIn('/web/image/', self.helper._image_url('image_512', '512x512', record=self.switch))

    def test_a_card_lists_small_pictures_in_the_same_order(self):
        extra = self.env['product.image'].sudo().create({
            'name': 'Back', 'product_tmpl_id': self.switch.id, 'image_1920': picture(),
        })
        card = self.helper._serialize_product(self.switch, None, {})
        self.assertEqual(len(card['images']), 2)
        self.assertEqual(len(card['thumbs']), 2)
        self.assertIn('/product.template/%d/image_256/' % self.switch.id, card['thumbs'][0])
        self.assertIn('/product.image/%d/image_256/' % extra.id, card['thumbs'][1])

    def test_a_variant_gallery_item_carries_its_small_picture(self):
        media = self.helper._mart369_variant_media(self.switch.product_variant_id)
        full, small = self.helper._mart369_media_pictures(media)
        self.assertEqual(full, [media[0]['src']])
        self.assertEqual(small, [media[0]['thumb']])
        self.assertIn('image_256', small[0])

    def test_the_image_address_setting_still_applies(self):
        config = self.env['mart369.config'].sudo()._get()
        config.image_base_url = 'https://shop.example.com'
        url = self.helper._image_url('image_512', '512x512', record=self.switch)
        self.assertTrue(url.startswith('https://shop.example.com/web/image/'), url)
        config.image_base_url = False
        url = self.helper._image_url('image_512', '512x512', record=self.switch)
        self.assertTrue(url.startswith('/web/image/'), url)

    # ------------------------------------------------------------ the search

    def test_suggest_is_a_thin_card(self):
        row = self._get('/369mart/search/suggest?q=zqx')['items'][0]
        self.assertEqual(row['id'], str(self.switch.id))
        self.assertEqual(row['price'], 100)
        self.assertIn('thumb', row)
        self.assertIn('image', row)
        for full_card_only in ('images', 'thumbs', 'facets', 'popularity', 'rating'):
            self.assertNotIn(full_card_only, row)

    def test_words_match_in_any_order_and_across_fields(self):
        for q in ('switch zqx', 'gigabit zqx', 'zqxlink switch'):
            ids = [i['id'] for i in self._get('/369mart/search/suggest?q=%s' % q.replace(' ', '%20'))['items']]
            self.assertIn(str(self.switch.id), ids, q)
        ids = [i['id'] for i in self._get('/369mart/search/suggest?q=zqx%20nothingelse')['items']]
        self.assertNotIn(str(self.switch.id), ids)

    def test_a_name_starting_with_the_word_comes_first(self):
        # Alphabetically "Aaa ..." would lead, and cut off, the better match.
        self.Template.create({'name': 'Aaa Cable for Wqzt', 'is_published': True})
        leader = self.Template.create({'name': 'Wqzt Router', 'is_published': True})
        items = self._get('/369mart/search/suggest?q=wqzt')['items']
        self.assertEqual(items[0]['id'], str(leader.id))

    def test_the_full_results_page_keeps_the_full_card(self):
        card = self._get('/369mart/search?q=zqx')['items'][0]
        self.assertIn('images', card)
        self.assertIn('thumbs', card)
        self.assertIn('popularity', card)
