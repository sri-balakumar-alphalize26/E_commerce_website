"""The install-time sample coupons are archived - unless the shop made them its own."""

import importlib.util
import os

from odoo.tests import TransactionCase, tagged


def _migration():
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                        'migrations', '19.0.1.7.0', 'post-migrate.py')
    spec = importlib.util.spec_from_file_location('cart_1_7_0', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@tagged('post_install', '-at_install')
class TestSampleCoupons(TransactionCase):

    def _sample(self, xmlid):
        coupon = self.env.ref(xmlid, raise_if_not_found=False)
        if not coupon:
            self.skipTest('%s was never installed on this database' % xmlid)
        values = _migration().SAMPLES[xmlid]
        coupon.sudo().write(dict(values, active=True, used_count=0))
        return coupon

    def test_an_untouched_sample_is_archived(self):
        coupon = self._sample('mart369_cart.coupon_freedel')
        _migration().migrate(self.env.cr, '19.0.1.6.0')
        self.assertFalse(coupon.active)

    def test_an_edited_sample_stays(self):
        coupon = self._sample('mart369_cart.coupon_welcome50')
        coupon.sudo().min_spend = 299.0
        _migration().migrate(self.env.cr, '19.0.1.6.0')
        self.assertTrue(coupon.active)

    def test_a_used_sample_stays(self):
        coupon = self._sample('mart369_cart.coupon_quick20')
        coupon.sudo().used_count = 3
        _migration().migrate(self.env.cr, '19.0.1.6.0')
        self.assertTrue(coupon.active)
