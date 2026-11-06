"""The order link pointed at a domain that does not exist.

`mart369_support.track_url` shipped as https://369mart.in/track/%s, which does
not resolve, so every track / rate / return link sent on WhatsApp went
nowhere. A database still holding that default gets the shop's real address;
any other value - one an operator chose - is left as it is.
"""

from odoo import SUPERUSER_ID, api

DEAD = 'https://369mart.in/track/%s'
LIVE = 'https://shop.369ai.biz/track/%s'


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    params = env['ir.config_parameter'].sudo()
    if (params.get_param('mart369_support.track_url') or '').strip() == DEAD:
        params.set_param('mart369_support.track_url', LIVE)
