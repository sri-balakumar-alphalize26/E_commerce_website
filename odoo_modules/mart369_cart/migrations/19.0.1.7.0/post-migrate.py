"""The install-time sample coupons go: QUICK20, WELCOME50, FREEDEL.

They were demo offers made by this module's data, live on every shop that
installed it. Each one is archived - not deleted, so an order that used it
still names it - unless somebody since changed it on the coupon desk or a
customer used it: then it is the shop's own coupon now, and it stays.
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

# What the data file made, field for field. A coupon that still reads like
# this was never touched by anyone.
SAMPLES = {
    'mart369_cart.coupon_quick20': {
        'code': 'QUICK20', 'kind': 'percent', 'value': 20.0, 'max_off': 60.0,
        'min_spend': 199.0, 'group': 'quick'},
    'mart369_cart.coupon_welcome50': {
        'code': 'WELCOME50', 'kind': 'flat', 'value': 50.0, 'max_off': 0.0,
        'min_spend': 499.0},
    'mart369_cart.coupon_freedel': {
        'code': 'FREEDEL', 'kind': 'free_delivery', 'value': 0.0, 'max_off': 0.0,
        'min_spend': 299.0},
}


def _used(cr, coupon):
    if coupon.used_count:
        return True
    cr.execute("""SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'sale_order' AND column_name = 'mart369_coupon_id'""")
    if not cr.fetchone():
        return False
    cr.execute('SELECT 1 FROM sale_order WHERE mart369_coupon_id = %s LIMIT 1', (coupon.id,))
    return bool(cr.fetchone())


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for xmlid, sample in SAMPLES.items():
        coupon = env.ref(xmlid, raise_if_not_found=False)
        if not coupon or not coupon.active:
            continue
        edited = any(
            (coupon[field] or False) != (value or False) for field, value in sample.items())
        if edited or _used(cr, coupon):
            _logger.info('mart369_cart: keeping coupon %s (edited or used)', coupon.code)
            continue
        coupon.active = False
        _logger.info('mart369_cart: archived the sample coupon %s', coupon.code)
