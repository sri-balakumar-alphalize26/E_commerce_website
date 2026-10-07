"""The order link points at the shop's real site."""

import importlib.util
import os

from odoo.tests import TransactionCase, tagged

from odoo.addons.mart369_support.models.whatsapp import DEFAULT_LINK

PARAM = 'mart369_support.track_url'


def _migration():
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                        'migrations', '19.0.1.4.0', 'post-migrate.py')
    spec = importlib.util.spec_from_file_location('support_1_4_0', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@tagged('post_install', '-at_install')
class TestTrackLink(TransactionCase):

    def test_the_default_is_a_real_site(self):
        self.assertEqual(DEFAULT_LINK, 'https://shop.369ai.biz/track/%s')

    def test_the_dead_default_is_replaced(self):
        params = self.env['ir.config_parameter'].sudo()
        params.set_param(PARAM, 'https://369mart.in/track/%s')
        _migration().migrate(self.env.cr, '19.0.1.3.0')
        self.assertEqual(params.get_param(PARAM), 'https://shop.369ai.biz/track/%s')

    def test_a_link_the_shop_chose_is_kept(self):
        params = self.env['ir.config_parameter'].sudo()
        params.set_param(PARAM, 'https://mystore.example/o/%s')
        _migration().migrate(self.env.cr, '19.0.1.3.0')
        self.assertEqual(params.get_param(PARAM), 'https://mystore.example/o/%s')
