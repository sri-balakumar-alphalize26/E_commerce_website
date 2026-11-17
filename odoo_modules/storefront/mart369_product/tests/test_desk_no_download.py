"""The product desk opens without downloading pictures (17 Nov 2026).

With the image server connector, reading a picture field downloads the file,
so "is there a photo?" asked by reading it downloaded the product's picture -
and every variant's - each time the desk opened. It is asked by size now; the
desk shows the same photos as before."""
import base64
import io
from unittest.mock import patch

from PIL import Image

from odoo.tests import TransactionCase, tagged


def png(shade):
    out = io.BytesIO()
    Image.new('RGB', (8, 8), (shade, 80, 40)).save(out, format='PNG')
    return base64.b64encode(out.getvalue())


@tagged('post_install', '-at_install')
class TestDeskNoDownload(TransactionCase):

    def test_the_desk_does_not_download_pictures(self):
        Attachment = self.env['ir.attachment'].sudo()
        if 'imgsrv_url' not in Attachment._fields:
            self.skipTest('ai369_image_server is not installed')
        self.env['ir.config_parameter'].sudo().set_param('ai369_image_server.enabled', 'False')
        colour = self.env['product.attribute'].sudo().create({
            'name': 'Zz Desk Colour', 'create_variant': 'always',
            'value_ids': [(0, 0, {'name': 'Red'}), (0, 0, {'name': 'Blue'})]})
        product = self.env['product.template'].sudo().create({
            'name': 'Zz Desk Pictures', 'image_1920': png(1),
            'attribute_line_ids': [(0, 0, {'attribute_id': colour.id,
                                           'value_ids': [(6, 0, colour.value_ids.ids)]})]})
        product.product_variant_ids[:1].image_variant_1920 = png(2)
        self.env.flush_all()    # the smaller sizes are written on flush
        for record in (product, product.product_variant_ids):
            for att in Attachment.search([('res_model', '=', record._name), ('res_id', 'in', record.ids),
                                          ('res_field', '!=', False)]):
                att._imgsrv_set('imgsrv:m:products/zz/%s.webp?v=1' % att.id,
                                'https://images.example.test/zz/%s.webp' % att.id, 'link|products/zz/%s.webp' % att.id)
        self.env.invalidate_all()
        Product = self.env['product.template']
        with patch.object(type(Attachment), '_imgsrv_read', side_effect=AssertionError('a download')):
            form = Product.mart369_desk_form(product_id=product.id)
            rows = Product._mart369_desk_variants(product)['rows']
        self.assertTrue(form['photo'], 'the product still shows its photo')
        self.assertEqual(sum(1 for row in rows if row['image']), 1, 'only the variant with its own photo')

        # A variant's image_* is computed and would download: asked by size.
        Helper = self.env['mart369.serializable']
        own, inherits = product.product_variant_ids[:1], product.product_variant_ids[1:2]
        bare = self.env['product.template'].sudo().create({'name': 'Zz Desk Bare'}).product_variant_id
        with patch.object(type(Attachment), '_imgsrv_read', side_effect=AssertionError('a download')):
            self.assertTrue(Helper._mart369_has_picture(own, 'image_256'))
            self.assertTrue(Helper._mart369_has_picture(inherits, 'image_256'), "the product's photo")
            self.assertFalse(Helper._mart369_has_picture(bare, 'image_256'))
