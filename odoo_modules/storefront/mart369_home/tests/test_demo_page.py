"""The permanent Demo page, and the Shop now switch on a banner.

The tests that matter most:

* test_it_is_never_served - a page of "Banner 1" and "Category 1" must never
  reach a customer, even as the last resort when no other page is left.
* test_a_copy_is_an_ordinary_page - copying is the whole point of it, so the
  lock must not travel with the copy.
"""

import base64
import io
import json

from PIL import Image

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import HttpCase, TransactionCase

from odoo.addons.mart369_home.controllers.admin_api import EDITOR_GROUP


def picture():
    out = io.BytesIO()
    Image.new('RGB', (300, 120), (20, 90, 160)).save(out, format='PNG')
    return base64.b64encode(out.getvalue())


@tagged('post_install', '-at_install')
class TestDemoPage(TransactionCase):

    def setUp(self):
        super().setUp()
        self.Version = self.env['mart369.home.version'].sudo()
        self.demo = self.Version._mart369_ensure_demo()
        self.quick = self.demo.mode_ids.filtered(lambda m: m.key == 'quick')

    def _real_pages(self):
        return self.Version.search([('is_demo', '=', False)])

    def _only_this_page_left(self, page):
        (self._real_pages() - page).with_context(mart369_settling=True).write({
            'deleted_at': fields.Datetime.now(), 'is_current': False,
            'starts_on': False, 'ends_on': False,
        })

    # ----------------------------------------------------------- what it holds

    def test_it_is_made_once(self):
        self.assertEqual(self.Version._mart369_ensure_demo(), self.demo)
        self.assertEqual(self.Version.search_count([('is_demo', '=', True)]), 1)
        self.assertEqual(self.demo.name, 'Demo')

    def test_it_is_only_the_structure(self):
        self.assertEqual(set(self.demo.mode_ids.mapped('key')), {'quick', 'all'})
        for mode in self.demo.mode_ids:
            self.assertEqual(len(mode.tab_ids), 1)
            self.assertEqual(len(mode.banner_ids), 4)
            self.assertEqual(len(mode.tile_ids), 8)
            self.assertFalse(mode.section_ids, 'No product rows on the Demo page.')

    def test_nothing_on_it_has_a_picture_or_a_drawing(self):
        for banner in self.quick.banner_ids:
            row = banner._serialize()
            self.assertEqual(row['art'], [])
            self.assertNotIn('image', row)
        for tile in self.quick.tile_ids:
            row = tile._serialize()
            self.assertEqual(row['art'], '')
            self.assertEqual(row['image'], '')
            self.assertEqual(tile._builder_vals()['art'], '')

    # --------------------------------------------------------------- the lock

    def test_the_page_cannot_be_removed(self):
        with self.assertRaises(UserError):
            self.demo.action_trash()
        with self.assertRaises(UserError):
            self.demo.unlink()
        self.assertTrue(self.demo.exists())
        self.assertFalse(self.demo.deleted_at)

    def test_the_page_cannot_be_changed(self):
        for vals in ({'name': 'Mine'}, {'is_current': True},
                     {'starts_on': fields.Datetime.now()}, {'is_demo': False},
                     {'deleted_at': fields.Datetime.now()}):
            with self.assertRaises(UserError, msg=str(vals)):
                self.demo.write(vals)
        with self.assertRaises(UserError):
            self.demo.action_mart369_make_current()

    def test_another_page_cannot_become_the_demo(self):
        page = self._real_pages()[:1]
        with self.assertRaises(UserError):
            page.write({'is_demo': True})
        with self.assertRaises(UserError):
            self.Version.create({'name': 'Second', 'is_demo': True})

    def test_what_is_on_it_cannot_be_changed(self):
        for band in (self.quick.banner_ids[:1], self.quick.tile_ids[:1], self.quick.tab_ids[:1]):
            with self.assertRaises(UserError, msg=band._name):
                band.write({'name': 'Changed'})
            with self.assertRaises(UserError, msg=band._name):
                band.action_trash()
            with self.assertRaises(UserError, msg=band._name):
                band.unlink()
        with self.assertRaises(UserError):
            self.quick.write({'tagline': 'Changed'})
        with self.assertRaises(UserError):
            self.quick.unlink()

    def test_nothing_can_be_added_to_it(self):
        env = self.env
        with self.assertRaises(UserError):
            env['mart369.home.banner'].create({'mode_id': self.quick.id, 'key': 'new', 'name': 'New'})
        with self.assertRaises(UserError):
            env['mart369.home.tile'].create({'mode_id': self.quick.id, 'key': 'new', 'name': 'New'})
        with self.assertRaises(UserError):
            env['mart369.home.tab'].create({'mode_id': self.quick.id, 'key': 'new', 'name': 'New'})
        with self.assertRaises(UserError):
            env['mart369.home.section'].create({'mode_id': self.quick.id, 'key': 'new', 'name': 'New'})

    # -------------------------------------------------------- never to shoppers

    def test_it_is_never_served(self):
        self.assertNotEqual(self.Version._mart369_live(), self.demo)
        self._only_this_page_left(self.Version.browse())
        self.assertFalse(self.Version._mart369_live(),
                         'With nothing else left, Demo must still not be chosen.')

    def test_it_does_not_count_as_a_real_page(self):
        """Otherwise someone could remove their last real page because Demo was
        still there, and customers would have nothing."""
        everyday = self.Version.search(
            [('is_current', '=', True), ('deleted_at', '=', False)], limit=1)
        self._only_this_page_left(everyday)
        everyday.with_context(mart369_settling=True).write({'is_current': False})
        with self.assertRaisesRegex(UserError, 'only saved home page'):
            everyday.action_trash()

    # ------------------------------------------------------------- the screens

    def test_the_screens_are_told(self):
        cards = {c['id']: c for c in self.Version.pages_load()['pages']}
        self.assertTrue(cards[str(self.demo.id)]['isDemo'])
        others = [c for i, c in cards.items() if i != str(self.demo.id)]
        self.assertFalse(any(c['isDemo'] for c in others))
        self.assertEqual(self.demo.state, 'off')

    # ------------------------------------------------------------ copying it

    def test_a_copy_is_an_ordinary_page(self):
        copy = self.demo.copy({'name': 'Mine'})
        self.assertFalse(copy.is_demo)
        mode = copy.mode_ids.filtered(lambda m: m.key == 'quick')
        self.assertEqual(len(mode.banner_ids), 4)
        self.assertEqual(len(mode.tile_ids), 8)
        mode.banner_ids[0].name = 'Summer sale'
        self.assertEqual(mode.banner_ids[0].name, 'Summer sale')
        copy.action_trash()
        self.assertTrue(copy.deleted_at)
        self.assertFalse(self.Version.search([
            ('is_demo', '=', True), ('id', '!=', self.demo.id)]))


@tagged('post_install', '-at_install')
class TestShopNowSwitch(TransactionCase):

    def setUp(self):
        super().setUp()
        # A real picture here must not try to reach the Image Server.
        self.env['ir.config_parameter'].sudo().set_param('ai369_image_server.enabled', 'False')
        page = self.env['mart369.home.version'].sudo().search(
            [('is_demo', '=', False), ('deleted_at', '=', False)], limit=1)
        self.banner = self.env['mart369.home.banner'].sudo().create({
            'mode_id': page.mode_ids[0].id, 'key': 'shop-switch-test', 'name': 'Sale',
        })

    def test_it_is_on_by_default(self):
        self.assertTrue(self.banner._serialize()['showShop'])
        self.assertTrue(self.banner._builder_vals()['show_shop_now'])

    def test_it_can_be_turned_off(self):
        self.banner.show_shop_now = False
        self.assertFalse(self.banner._serialize()['showShop'])

    def test_it_is_separate_from_the_text_switch(self):
        self.banner.write({'image_1920': picture(), 'text_on_image': False})
        row = self.banner._serialize()
        self.assertTrue(row['image'])
        self.assertTrue(row['showShop'], 'A picture must not hide the button by itself.')
        self.assertNotIn('textOnImage', row)
        self.banner.show_shop_now = False
        self.assertFalse(self.banner._serialize()['showShop'])


@tagged('post_install', '-at_install')
class TestRenamingAPage(HttpCase):
    """Any home page can be renamed, the live one too. Only Demo cannot."""

    def setUp(self):
        super().setUp()
        self.Version = self.env['mart369.home.version'].sudo()
        self.demo = self.Version._mart369_ensure_demo()
        self.page = self.demo.copy({'name': 'Demo (copy)'})
        self.env['res.users'].create({
            'name': 'A Designer',
            'login': 'mart369_test_rename',
            'password': 'mart369_test_rename',
            'group_ids': [(6, 0, [self.env.ref('base.group_user').id,
                                  self.env.ref(EDITOR_GROUP).id])],
        })
        self.authenticate('mart369_test_rename', 'mart369_test_rename')

    def _rename(self, page, name):
        return self.url_open(
            '/369mart/admin/home/pages/%d' % page.id, data=json.dumps({'name': name}),
            headers={'Content-Type': 'application/json'}, method='PATCH')

    def test_a_copy_of_demo_can_be_renamed(self):
        response = self._rename(self.page, 'Summer sale')
        self.assertEqual(response.status_code, 200)
        self.page.invalidate_recordset()
        self.assertEqual(self.page.name, 'Summer sale')

    def test_the_live_page_can_be_renamed(self):
        live = self.Version._mart369_live()
        self.assertEqual(self._rename(live, 'Everyday').status_code, 200)
        live.invalidate_recordset()
        self.assertEqual(live.name, 'Everyday')
        self.assertEqual(self.Version._mart369_live(), live)

    def test_an_empty_name_is_refused(self):
        for name in ('', '   '):
            self.assertNotEqual(self._rename(self.page, name).status_code, 200, repr(name))
        self.page.invalidate_recordset()
        self.assertEqual(self.page.name, 'Demo (copy)')

    def test_demo_cannot_be_renamed_through_the_console(self):
        self.assertNotEqual(self._rename(self.demo, 'Mine').status_code, 200)
        self.demo.invalidate_recordset()
        self.assertEqual(self.demo.name, 'Demo')


@tagged('post_install', '-at_install')
class TestPageNames(HttpCase):
    """Two pages cannot share a name, and automatic names must never be refused."""

    def setUp(self):
        super().setUp()
        self.Version = self.env['mart369.home.version'].sudo()
        self.demo = self.Version._mart369_ensure_demo()
        self.first = self.demo.copy({'name': 'Diwali Sale'})
        self.second = self.demo.copy({'name': 'Summer Sale'})

    def test_a_typed_name_already_in_use_is_refused(self):
        with self.assertRaisesRegex(UserError, 'already exists'):
            self.second.write({'name': 'Diwali Sale'})
        with self.assertRaisesRegex(UserError, 'already exists'):
            self.demo.copy({'name': 'Diwali Sale'})

    def test_case_and_spaces_do_not_make_it_different(self):
        for name in ('diwali sale', '  DIWALI SALE '):
            with self.assertRaisesRegex(UserError, 'already exists', msg=name):
                self.second.write({'name': name})

    def test_demo_counts_as_taken(self):
        with self.assertRaisesRegex(UserError, 'already exists'):
            self.second.write({'name': 'demo'})

    def test_keeping_its_own_name_is_fine(self):
        self.second.write({'name': 'SUMMER SALE'})
        self.assertEqual(self.second.name, 'SUMMER SALE')

    def test_duplicating_twice_numbers_the_copies(self):
        one = self.first.copy()
        two = self.first.copy()
        three = self.first.copy()
        self.assertEqual(len({one.name, two.name, three.name}), 3)
        self.assertTrue(two.name.endswith(' 2'), two.name)

    def test_rebuilding_twice_is_not_refused(self):
        one = self.Version._mart369_build_starter(make_current=False)
        two = self.Version._mart369_build_starter(make_current=False)
        self.assertNotEqual(one.name, two.name)

    def test_a_trashed_page_gives_its_name_up_and_asks_for_it_back(self):
        self.first.action_trash()
        self.second.write({'name': 'Diwali Sale'})
        with self.assertRaisesRegex(UserError, 'already exists'):
            self.first.action_restore()

    def test_the_console_says_why(self):
        self.env['res.users'].create({
            'name': 'A Designer', 'login': 'mart369_test_names', 'password': 'mart369_test_names',
            'group_ids': [(6, 0, [self.env.ref('base.group_user').id, self.env.ref(EDITOR_GROUP).id])],
        })
        self.authenticate('mart369_test_names', 'mart369_test_names')
        response = self.url_open(
            '/369mart/admin/home/pages/%d' % self.second.id,
            data=json.dumps({'name': 'Diwali Sale'}),
            headers={'Content-Type': 'application/json'}, method='PATCH')
        self.assertNotEqual(response.status_code, 200)
        self.assertIn('already exists', response.text)
