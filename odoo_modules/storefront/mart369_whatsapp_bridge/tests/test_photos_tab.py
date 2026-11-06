"""The Confirmation pictures tab is the Photographs box: one list of pictures."""

from odoo.tests import TransactionCase, tagged

from ..hooks import COPIED, copy_confirmation_pictures, copy_variant_pictures

RED_PX = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC'
BLUE_PX = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGNgYPgPAAEDAQAIicLsAAAAAElFTkSuQmCC'


@tagged('post_install', '-at_install')
class TestPhotosTab(TransactionCase):

    def setUp(self):
        super().setUp()
        self.env['ir.config_parameter'].sudo().set_param('ai369_image_server.enabled', 'False')
        self.Product = self.env['product.template'].sudo()
        self.Picture = self.env['sa.confirm.picture'].sudo()

    def test_the_tab_draws_the_photographs_box(self):
        arch = self.Product.get_view(view_type='form')['arch']
        self.assertIn('mart369_photos_box', arch)
        self.assertNotIn('sa_extra_picture_ids', arch)

    def test_the_variant_tab_draws_the_photographs_box(self):
        arch = self.env['product.product'].sudo().get_view(view_type='form')['arch']
        self.assertIn('mart369_photos_box', arch)
        self.assertIn('product_variant_image_ids', arch)
        self.assertNotIn('sa_variant_picture_ids', arch)

    def test_variant_pictures_move_once_and_the_page_shows_them_once(self):
        product = self.Product.create({'name': 'Zz Tab Variant'})
        variant = product.product_variant_id
        self.Picture.create({'product_id': variant.id, 'image': RED_PX, 'name': 'Front'})
        copy_variant_pictures(self.env)
        copy_variant_pictures(self.env)
        self.assertEqual(len(variant.product_variant_image_ids), 1)
        self.assertEqual(variant.sa_variant_picture_ids.source, COPIED)
        self.assertEqual(len(variant._sa_own_pictures()), 1)

    def test_hand_added_picture_goes_on_the_card_when_there_is_none(self):
        product = self.Product.create({'name': 'Zz Tab No Card'})
        picture = self.Picture.create({'product_tmpl_id': product.id, 'image': RED_PX})
        copy_confirmation_pictures(self.env)
        self.assertTrue(product.image_1920)
        self.assertFalse(product.product_template_image_ids)
        self.assertEqual(picture.source, COPIED)

    def test_hand_added_picture_joins_the_gallery_when_there_is_a_card(self):
        product = self.Product.create({'name': 'Zz Tab Card', 'image_1920': BLUE_PX})
        self.Picture.create({'product_tmpl_id': product.id, 'image': RED_PX})
        copy_confirmation_pictures(self.env)
        self.assertEqual(len(product.product_template_image_ids), 1)

    def test_copied_once_and_internet_pictures_left_alone(self):
        product = self.Product.create({'name': 'Zz Tab Once', 'image_1920': BLUE_PX})
        self.Picture.create({'product_tmpl_id': product.id, 'image': RED_PX})
        internet = self.Picture.create({'product_tmpl_id': product.id, 'image': RED_PX, 'source': 'internet'})
        copy_confirmation_pictures(self.env)
        copy_confirmation_pictures(self.env)
        self.assertEqual(len(product.product_template_image_ids), 1)
        self.assertEqual(internet.source, 'internet')

    def test_link_tile_follows_the_image_server_switch(self):
        Product = self.env['product.template']
        self.assertFalse(Product.mart369_desk_form()['imageLink'])
        self.env['ir.config_parameter'].sudo().set_param('ai369_image_server.enabled', 'True')
        self.assertEqual(Product.mart369_desk_form()['imageLink'], 'imgsrv_image_url' in Product._fields)
