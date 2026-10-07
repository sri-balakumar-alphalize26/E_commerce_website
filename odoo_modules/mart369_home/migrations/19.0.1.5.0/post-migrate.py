"""Replace the grocery starter page with one arranged from the catalogue.

A shop that never replaced the page this module installs shows customers
"Fruits picked this morning" and "Atta & staples" - on the Dubai shop, which
sells laptop parts and CCTV. That page is swapped for one built from the
shop's own biggest categories (models/home_starter.py), switched on, and the
grocery page is kept, renamed as an example, so switching back is one click.

**Only when nobody has rearranged it.** The test is the grocery page still
being live and its "Groceries" tab still standing as installed: a shop that
renamed or removed that tab has started making the page its own, and is left
exactly as it is.
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Version = env['mart369.home.version']
    grocery = env.ref('mart369_home.home_version_everyday', raise_if_not_found=False)
    tab = env.ref('mart369_home.tab_q_grocery', raise_if_not_found=False)
    if not grocery or Version._mart369_live() != grocery:
        _logger.info('mart369_home: the grocery starter page is not live - left as it is')
        return
    if (not tab or not tab.active or tab.deleted_at or tab.name != 'Groceries'
            or tab.mode_id.version_id != grocery):
        _logger.info('mart369_home: the starter page has been rearranged - left as it is')
        return
    page = Version._mart369_build_starter()
    grocery.write({
        'name': 'Example - grocery layout (not shown)',
        'note': 'The sample page this module used to start with. '
                'Customers never see it unless you switch it on.',
    })
    _logger.info('mart369_home: home page %s built from the catalogue and switched on; '
                 'the grocery page is kept as an example', page.id)
