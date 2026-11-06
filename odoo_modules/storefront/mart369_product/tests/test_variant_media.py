"""Each colour shows its own pictures (mart369 `_mart369_variant_media`).

Picking Red used to show the product's main picture whatever was saved on
Red: Odoo's own Extra Variant Media was never read. The rule now is the
variant's own picture and media first, the product's only when the variant has
none - so one colour never shows another colour's photo.
"""

from odoo.tests import TransactionCase, tagged

RED_PX = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC'
BLUE_PX = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGNgYPgPAAEDAQAIicLsAAAAAElFTkSuQmCC'


@tagged('post_install', '-at_install')
class TestVariantMedia(TransactionCase):

    def setUp(self):
        super().setUp()
        colour = self.env['product.attribute'].create({
            'name': 'Zz Media Colour', 'create_variant': 'always', 'display_type': 'color',
            'value_ids': [(0, 0, {'name': 'White', 'html_color': '#FFFFFF'}),
                          (0, 0, {'name': 'Red', 'html_color': '#E53935'}),
                          (0, 0, {'name': 'Blue', 'html_color': '#1E88E5'})]})
        self.tmpl = self.env['product.template'].create({
            'name': 'Zz Media Apple', 'is_published': True, 'list_price': 500,
            'image_1920': BLUE_PX,
            'attribute_line_ids': [(0, 0, {'attribute_id': colour.id,
                                           'value_ids': [(6, 0, colour.value_ids.ids)]})],
        })
        self.Image = self.env['product.image']
        self.tmpl_extra = self.Image.create({
            'name': 'Box', 'image_1920': BLUE_PX, 'product_tmpl_id': self.tmpl.id})

        def variant(name):
            return self.tmpl.product_variant_ids.filtered(
                lambda v: v.product_template_attribute_value_ids.name == name)
        self.white, self.red, self.blue = variant('White'), variant('Red'), variant('Blue')

        # White: its own main picture and one more. Red: no main picture of
        # its own, but a photo and a video in its Extra Variant Media.
        self.white.image_variant_1920 = RED_PX
        self.white_extra = self.Image.create({
            'name': 'White back', 'image_1920': RED_PX, 'product_variant_id': self.white.id})
        self.red_photo = self.Image.create({
            'name': 'Red front', 'image_1920': RED_PX, 'product_variant_id': self.red.id, 'sequence': 1})
        self.red_video = self.Image.create({
            'name': 'Red video', 'image_1920': RED_PX, 'product_variant_id': self.red.id, 'sequence': 2,
            'video_url': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'})
        self.helper = self.env['mart369.serializable'].sudo()

    def _media(self, variant):
        return self.helper._mart369_variant_media(variant)

    def _from_the_product(self, src):
        return ('/product.template/%d/' % self.tmpl.id in src
                or '/product.image/%d/' % self.tmpl_extra.id in src)

    def test_a_colour_with_its_own_pictures_shows_only_those(self):
        media = self._media(self.white)
        self.assertEqual([m['type'] for m in media], ['photo', 'photo'])
        self.assertIn('/product.product/%d/' % self.white.id, media[0]['src'])
        self.assertIn('/product.image/%d/' % self.white_extra.id, media[1]['src'])
        self.assertFalse([m for m in media if self._from_the_product(m['src'])],
                         "the product's own pictures are not mixed in")

    def test_another_colour_never_shows_them(self):
        srcs = [m['src'] for m in self._media(self.red)]
        self.assertFalse([s for s in srcs if '/product.product/%d/' % self.white.id in s
                          or '/product.image/%d/' % self.white_extra.id in s])

    def test_a_video_plays_in_the_gallery_with_its_picture_as_poster(self):
        media = self._media(self.red)
        self.assertEqual([m['type'] for m in media], ['photo', 'video'])
        video = media[1]
        self.assertTrue(video['src'].startswith('https://www.youtube.com/embed/dQw4w9WgXcQ'))
        self.assertIn('/product.image/%d/' % self.red_video.id, video['poster'])

    def test_the_card_images_are_photos_only(self):
        images = self.helper._mart369_variant_images(self.red)
        self.assertEqual(len(images), 2, 'the photo, and the video by its poster')
        self.assertFalse([i for i in images if 'youtube' in i])

    def test_a_colour_with_nothing_of_its_own_shows_the_products(self):
        media = self._media(self.blue)
        self.assertTrue(media)
        self.assertTrue(all(self._from_the_product(m['src']) for m in media))

    def test_the_page_sends_each_variant_its_own_media(self):
        payload = self.env['mart369.product.page'].payload(self.tmpl, self.red)
        by_id = {v['id']: v for v in payload['variants']}
        key = self.helper._mart369_variant_key
        self.assertEqual(payload['p']['id'], key(self.red))
        self.assertEqual([m['type'] for m in payload['p']['media']], ['photo', 'video'])
        self.assertEqual(len(by_id[key(self.white)]['media']), 2)
        self.assertEqual({a['display'] for a in payload['attrs']}, {'color'})
        self.assertEqual({v['name']: v.get('color') for v in payload['attrs'][0]['values']},
                         {'White': '#FFFFFF', 'Red': '#E53935', 'Blue': '#1E88E5'})

    def test_the_option_buttons_icon_is_never_used(self):
        ptav = self.red.product_template_attribute_value_ids
        ptav.product_attribute_value_id.image = BLUE_PX
        srcs = [m['src'] for m in self._media(self.red)]
        self.assertFalse([s for s in srcs if 'product.attribute.value' in s
                          or 'product.template.attribute.value' in s])
