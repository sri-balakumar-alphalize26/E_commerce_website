"""A pasted link keeps only the link, and a save shares one connection to the image server."""
import base64
from unittest.mock import MagicMock, patch

from odoo.tests import TransactionCase, tagged

from ..models import ir_attachment
from ..models.product_template import _onchange_needs_pictures

SERVER = 'https://images.example.test'


def marker(name):
    return base64.b64encode(b'<!--imgsrv-linked:%s/products/a/b/c/%s-->' % (SERVER.encode(), name.encode()))


@tagged('post_install', '-at_install')
class TestLinkPush(TransactionCase):

    def setUp(self):
        super().setUp()
        set_param = self.env['ir.config_parameter'].sudo().set_param
        set_param('ai369_image_server.enabled', 'True')
        set_param('ai369_image_server.url', SERVER)
        set_param('ai369_image_server.api_key', 'test-key')
        self.session = MagicMock()
        self.session.__enter__.return_value = self.session
        self.session.head.return_value = MagicMock(status_code=200, headers={
            'content-type': 'image/webp', 'content-length': '100', 'last-modified': 'today'})

    def _atts(self, *records):
        Att = self.env['ir.attachment'].sudo()
        out = Att
        for record in records:
            record.flush_recordset()
            out |= Att.search([('res_model', '=', record._name), ('res_id', '=', record.id),
                               ('res_field', '=', 'image_1920')])
        return out

    def _push(self, atts):
        with patch.object(ir_attachment.requests, 'Session', return_value=self.session) as opened, \
                patch.object(ir_attachment.requests, 'head', side_effect=AssertionError('a new connection')):
            atts._imgsrv_push()
        return opened

    def test_a_save_shares_one_connection(self):
        Product = self.env['product.template'].sudo()
        products = [Product.create({'name': 'Zz Link %s' % i, 'image_1920': marker('%s.webp' % i)})
                    for i in range(1, 4)]
        opened = self._push(self._atts(*products))
        self.assertEqual(opened.call_count, 1)
        self.assertEqual(self.session.head.call_count, 6, "The picture and its thumbnail, for each of the 3")

    def _read(self, fname, status=200, ctype='image/webp'):
        answer = MagicMock(status_code=status, content=b'from-the-address', headers={'content-type': ctype})
        client = MagicMock()
        client.return_value.get_file.return_value = b'from-the-api'
        with patch.object(ir_attachment.requests, 'get', return_value=answer), \
                patch.object(ir_attachment, 'Client', client):
            return self.env['ir.attachment'].sudo()._imgsrv_read(fname), client

    def test_a_public_file_is_read_at_its_public_address(self):
        data, client = self._read('imgsrv:m:products/a/b/c/read1.webp?v=t1')
        self.assertEqual(data, b'from-the-address')
        client.return_value.get_file.assert_not_called()

    def test_the_api_is_the_fallback(self):
        self.assertEqual(self._read('imgsrv:m:products/a/b/c/read2.webp?v=t2', status=404)[0], b'from-the-api')
        self.assertEqual(self._read('imgsrv:m:products/a/b/c/read3.webp?v=t3', ctype='text/html')[0], b'from-the-api')

    def test_an_uploaded_original_still_uses_the_api(self):
        data, client = self._read('imgsrv:p:products/a/b/c/original.webp?v=t4')
        self.assertEqual(data, b'from-the-api')
        client.return_value.get_file.assert_called_once()

    def test_a_form_refresh_downloads_only_for_a_real_picture_on_a_row(self):
        gallery = 'product_template_image_ids'
        self.assertFalse(_onchange_needs_pictures({gallery: [[1, 5, {'image_1920': marker('1.webp').decode()}]]}))
        self.assertFalse(_onchange_needs_pictures({gallery: [[1, 5, {'sequence': 20}]]}))
        self.assertFalse(_onchange_needs_pictures({gallery: [[0, 'virtual_1', {'image_1920': 'iVBORw0KGgo='}]]}))
        self.assertFalse(_onchange_needs_pictures({gallery: [[2, 5]], 'name': 'x'}))
        self.assertTrue(_onchange_needs_pictures({gallery: [[1, 5, {'image_1920': 'iVBORw0KGgo='}]]}))

    def test_a_linked_gallery_change_downloads_nothing(self):
        Product = self.env['product.template'].sudo()
        if 'product_template_image_ids' not in Product._fields:
            self.skipTest('website_sale is not installed')
        product = Product.create({'name': 'Zz Link Refresh', 'image_1920': marker('5.webp')})
        row = self.env['product.image'].sudo().create({
            'name': 'x', 'product_tmpl_id': product.id, 'image_1920': marker('6.webp')})
        self._push(self._atts(product, row))
        product.env.invalidate_all()
        spec = {'image_1920': {}, 'product_template_image_ids': {'fields': {
            'image_1920': {}, 'image_1024': {}, 'sequence': {}, 'can_image_1024_be_zoomed': {}}}}
        with patch.object(ir_attachment.IrAttachment, '_imgsrv_read', side_effect=AssertionError('a download')):
            for change in ({'sequence': 5}, {'image_1920': marker('7.webp').decode()}):
                product.onchange({'product_template_image_ids': [[1, row.id, change]]},
                                 ['product_template_image_ids'], spec)

    def test_only_the_link_is_kept(self):
        product = self.env['product.template'].sudo().create({'name': 'Zz Link Keep', 'image_1920': marker('9.webp')})
        att = self._atts(product)
        self._push(att)
        self.assertEqual(att.imgsrv_ref, 'link|products/a/b/c/9.webp')
        self.assertTrue(att.store_fname.startswith('imgsrv:m:products/a/b/c/9.webp'))
        self.assertEqual(att.imgsrv_state, 'remote')
