"""The WhatsApp page shows the shop's pictures, up to 13, and never searches the internet."""
import base64
import io
from unittest.mock import patch

from PIL import Image

from odoo.tests import TransactionCase, tagged


def png(shade):
    """A small picture of its own, so no two count as a repeat."""
    out = io.BytesIO()
    Image.new('RGB', (4, 4), (shade, 40, 90)).save(out, format='PNG')
    return base64.b64encode(out.getvalue())


@tagged('post_install', '-at_install')
class TestConfirmPictures(TransactionCase):

    def setUp(self):
        super().setUp()
        self.env['ir.config_parameter'].sudo().set_param('ai369_image_server.enabled', 'False')
        session = self.env['whatsapp.session'].sudo().create({
            'name': 'Pictures Test Session', 'gateway_api_key': 'pictures-test-key'})
        self.group = self.env['sa.sales.group'].sudo().create({
            'name': 'Pictures Test Group', 'group_jid': 'pictures-test@g.us',
            'session_id': session.id, 'group_type': 'customer'})
        self.Product = self.env['product.template'].sudo()
        self.Image = self.env['product.image'].sudo()
        if 'product_template_image_ids' not in self.Product._fields:
            self.skipTest('website_sale is not installed')

    def _link(self, product, variant=None):
        request = self.env['sa.group.request'].sudo().create({
            'group_id': self.group.id, 'requester_phone': '+96890000077',
            'raw_text': product.name, 'product_id': product.id})
        if variant:
            request.sa_variant_id = variant
        return self.env['sa.confirm.link'].sudo().create({'request_id': request.id, 'kind': 'customer'})

    def _gallery(self, product, *shades):
        for shade in shades:
            self.Image.create({'name': 'Shot', 'image_1920': png(shade), 'product_tmpl_id': product.id})

    def test_card_picture_first_then_gallery_up_to_13(self):
        product = self.Product.create({'name': 'Zz Pictures Many', 'image_1920': png(1)})
        self._gallery(product, *range(10, 25))
        pictures = self._link(product)._picture_items()
        self.assertEqual(len(pictures), 13)
        self.assertEqual(pictures[0], base64.b64decode(product.image_1920))

    def test_a_picture_on_the_image_server_is_only_its_address(self):
        Attachment = self.env['ir.attachment'].sudo()
        if 'imgsrv_url' not in Attachment._fields:
            self.skipTest('ai369_image_server is not installed')
        product = self.Product.create({'name': 'Zz Pictures Linked', 'image_1920': png(30)})
        self._gallery(product, 31)
        row = product.product_template_image_ids
        url = 'https://images.example.test/products/a/b/c/1.webp'
        for record in (product, row):
            attachment = Attachment.search([('res_model', '=', record._name), ('res_id', '=', record.id),
                                            ('res_field', '=', 'image_1920')])
            attachment._imgsrv_set('imgsrv:m:products/a/b/c/%s.webp?v=1' % record.id, url + '?v=%s' % record.id,
                                   'link|products/a/b/c/1.webp', checksum='sum%s' % record.id)
        record_type = type(Attachment)
        with patch.object(record_type, '_imgsrv_read', side_effect=AssertionError('a download')):
            items = self._link(product)._picture_items()
        self.assertEqual(items, [url + '?v=%s' % product.id, url + '?v=%s' % row.id])

    def test_the_website_card_downloads_nothing(self):
        Attachment = self.env['ir.attachment'].sudo()
        helper = self.env.get('mart369.serializable')
        if 'imgsrv_url' not in Attachment._fields or helper is None:
            self.skipTest('the image server or the shop is not installed')
        product = self.Product.create({'name': 'Zz Pictures Card', 'image_1920': png(32)})
        self._gallery(product, 33)
        for record in (product, product.product_template_image_ids):
            for attachment in Attachment.search([('res_model', '=', record._name), ('res_id', '=', record.id),
                                                 ('res_field', '!=', False)]):
                attachment._imgsrv_set('imgsrv:m:products/a/b/c/%s.webp?v=1' % attachment.id,
                                       'https://images.example.test/products/a/b/c/%s.webp' % attachment.id,
                                       'link|products/a/b/c/%s.webp' % attachment.id)
        product.env.invalidate_all()
        helper = helper.sudo()
        with patch.object(type(Attachment), '_imgsrv_read', side_effect=AssertionError('a download')):
            self.assertEqual(len(helper._mart369_variant_media(product.product_variant_id)), 2)
            card = helper._serialize_product(product, None, helper._price_context_for(product), 'quick')
        self.assertEqual(len(card['images']), 2)

    def test_one_photo_stays_one_photo(self):
        product = self.Product.create({'name': 'Zz Pictures One', 'image_1920': png(2)})
        self.env['sa.confirm.picture'].sudo().create({
            'product_tmpl_id': product.id, 'image': png(3), 'source': 'internet'})
        self.assertEqual(len(self._link(product)._picture_items()), 1)

    def test_a_colour_with_photos_shows_only_its_own(self):
        colour = self.env['product.attribute'].sudo().create({
            'name': 'Zz Pictures Colour', 'create_variant': 'always',
            'value_ids': [(0, 0, {'name': 'Red'}), (0, 0, {'name': 'Blue'})]})
        product = self.Product.create({
            'name': 'Zz Pictures Laptop', 'image_1920': png(4),
            'attribute_line_ids': [(0, 0, {'attribute_id': colour.id,
                                           'value_ids': [(6, 0, colour.value_ids.ids)]})]})
        self._gallery(product, 5, 6)
        variant = {v.product_template_attribute_value_ids.name: v for v in product.product_variant_ids}
        red_shot = self.Image.create({'name': 'Red', 'image_1920': png(7),
                                      'product_variant_id': variant['Red'].id})
        self.assertEqual(self._link(product, variant['Red'])._picture_items(),
                         [base64.b64decode(red_shot.image_1920)])
        self.assertEqual(len(self._link(product, variant['Blue'])._picture_items()), 3)

    def test_no_photo_makes_no_search(self):
        product = self.Product.create({'name': 'Zz Pictures None'})
        link = self._link(product)
        with patch('requests.get', side_effect=AssertionError('internet search')), \
                patch('requests.post', side_effect=AssertionError('internet search')):
            raw, source = link.request_id._sa_confirm_picture(fetch=True)
        self.assertEqual((raw, source), (b'', 'none'), 'nothing is drawn either (23 Nov 2026)')
        self.assertFalse(product.image_1920)

    def test_the_search_is_gone(self):
        for name in ('_sa_search_pictures', '_sa_fetch_picture_from_internet', '_sa_picture_candidates'):
            self.assertFalse(hasattr(self.Product, name), name)
        self.assertFalse(hasattr(self.env['sa.confirm.link'], '_ensure_pictures'))

    def test_a_product_the_finder_picked_shows_its_photo_before_accept(self):
        """A word like "laptop" picks one of the shop's products as the
        candidate; the page shows it, photo and all, before ACCEPT."""
        product = self.Product.create({'name': 'Zz Pictures Finder Pick', 'image_1920': png(60)})
        request = self.env['sa.group.request'].sudo().create({
            'group_id': self.group.id, 'requester_phone': '+96890000078', 'raw_text': 'laptop',
            'finder_kind': 'ours', 'finder_model': product.name,
            'candidate_product_ids': [(6, 0, [product.id])]})
        self.assertFalse(request.product_id)
        link = self.env['sa.confirm.link'].sudo().create({'request_id': request.id, 'kind': 'customer'})
        self.assertEqual(link._product(), product)
        self.assertEqual(link._picture_items()[0], base64.b64decode(product.image_1920))
        labels = [row[0] for row in link._details_rows()]
        self.assertNotIn('Asked for', labels)
        self.assertEqual(link._details_rows()[0][2], product.name)

    def test_a_market_pick_still_has_no_product(self):
        request = self.env['sa.group.request'].sudo().create({
            'group_id': self.group.id, 'requester_phone': '+96890000079', 'raw_text': 'laptop',
            'finder_kind': 'market', 'finder_model': 'Some Market Laptop'})
        link = self.env['sa.confirm.link'].sudo().create({'request_id': request.id, 'kind': 'customer'})
        self.assertFalse(link._product())
