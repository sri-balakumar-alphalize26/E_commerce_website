"""Give the modes that predate saved pages a home.

Before this version there was one Quick and one Express and that was the home
page. Now every saved page owns its own pair, so the existing pair has to be
adopted by the everyday page - otherwise they belong to nobody, the live page
has no modes, and the app is served an empty home page.

The seed data cannot do this: it is `noupdate`, which is right (it must never
overwrite banners somebody has edited), and that also means it will not fill
in a new field on records that already exist.
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    env = api.Environment(cr, SUPERUSER_ID, {})
    orphans = env['mart369.home.mode'].sudo().search([('version_id', '=', False)])
    if not orphans:
        return

    Version = env['mart369.home.version'].sudo()
    everyday = (Version.search([('is_current', '=', True)], limit=1)
                or Version.search([], limit=1))
    if not everyday:
        everyday = Version.create({
            'name': 'Everyday',
            'note': 'The page the app shows when nothing is scheduled.',
            'is_current': True,
        })

    orphans.write({'version_id': everyday.id})
    _logger.info(
        '369 Mart: adopted %s mode(s) into the saved page %r',
        len(orphans), everyday.name)
