"""Sample catalogue hooks.

The data files do the bulk of the work. Three things they cannot do on their
own happen here:

  * **Adopt.** Seven of the categories this shop wants already exist in the
    database, put there by hand. Their slugs are taken, and a slug is unique,
    so a second "Storage" would be saved as `storage-2` and every link
    pointing at `storage` would miss it. Before the data loads we stamp our
    own external id onto the record that is already there, and the XML then
    updates it instead of creating a rival.

  * **Hide.** The grocery categories left over from the old sample data are
    switched off rather than deleted, so nothing that references them breaks
    and a tick brings any of them back.

  * **Stand down the old home page.** mart369_home ships a grocery home page
    with its own tabs, tiles, banners and rows. Ours are additions, not
    replacements, so without this the customer would see fourteen tabs.

    Archiving them is not enough. Tabs, tiles and banners each carry a
    `unique (mode_id, key)` constraint, and a SQL constraint does not care
    whether a row is archived - the old `home` tab would still collide with
    ours. So their keys are moved aside as well, and moved back on uninstall.
"""

import logging

_logger = logging.getLogger(__name__)

MODULE = 'mart369_parts_demo'

# Categories already in the database that this catalogue takes over.
ADOPT = [
    ('categ_storage', 'storage'),
    ('categ_peripherals', 'peripherals'),
    ('categ_networking', 'networking'),
    ('categ_computers', 'computers'),
    ('categ_laptops', 'laptops'),
    ('categ_accessories', 'accessories'),
    ('categ_chargers', 'chargers'),
]

# Grocery leftovers: hidden from the app, kept in Odoo.
HIDE = [
    'fresh-fruits', 'daily-essentials', 'home-kitchen',
    'office-stationery', 'electronics', 'test-gear',
]

# The old home page, switched off while this catalogue is installed. The first
# three are keyed and unique per mode, so their keys move aside too.
OLD_HOME_KEYED = ['mart369.home.tab', 'mart369.home.tile', 'mart369.home.banner']
OLD_HOME = OLD_HOME_KEYED + ['mart369.home.section']

# What a moved-aside key is prefixed with. Long enough not to collide with
# anything an operator would type.
PARKED = 'parked-grocery-'


def _old_home_records(env):
    """Everything mart369_home's own data file put on the home page."""
    for model in OLD_HOME:
        data = env['ir.model.data'].sudo().search([
            ('module', '=', 'mart369_home'), ('model', '=', model),
        ])
        if not data:
            continue
        records = env[model].sudo().with_context(active_test=False) \
            .browse(data.mapped('res_id')).exists()
        if records:
            yield records


def _stand_down_old_home(env):
    """Archive the grocery home page and move its keys out of the way."""
    for records in _old_home_records(env):
        live = records.filtered('active')
        if live:
            live.write({'active': False})
        if records._name not in OLD_HOME_KEYED:
            continue
        for record in records:
            if record.key and not record.key.startswith(PARKED):
                record.write({'key': PARKED + record.key})
        _logger.info('369 Mart parts: stood down %s %s', len(records), records._name)


def _restore_old_home(env):
    """Put the grocery home page back exactly as it was."""
    for records in _old_home_records(env):
        if records._name in OLD_HOME_KEYED:
            for record in records:
                if record.key and record.key.startswith(PARKED):
                    record.write({'key': record.key[len(PARKED):]})
        dead = records.filtered(lambda r: not r.active)
        if dead:
            dead.write({'active': True})


def pre_init_hook(env):
    """Give the categories that already exist our external ids.

    Runs before the data files load, which is the whole point: by the time
    `parts_categories.xml` names `categ_storage`, that id already resolves to
    the Storage category sitting in the database, so the record is updated
    rather than duplicated.
    """
    Category = env['product.public.category'].sudo()
    Data = env['ir.model.data'].sudo()
    for xmlid, slug in ADOPT:
        existing = Category.with_context(active_test=False).search(
            [('mart_slug', '=', slug)], limit=1)
        if not existing:
            continue  # a fresh database: the data file simply creates it
        if Data.search_count([('module', '=', MODULE), ('name', '=', xmlid)]):
            continue  # already adopted, nothing to do
        Data.create({
            'module': MODULE,
            'name': xmlid,
            'model': 'product.public.category',
            'res_id': existing.id,
            'noupdate': False,
        })
        _logger.info('369 Mart parts: adopted category %r (id %s)', slug, existing.id)

    # Must happen here, not in post_init: our tabs, tiles and banners are
    # inserted while the data file loads, and they collide with the grocery
    # ones on `unique (mode_id, key)` long before post_init would run.
    _stand_down_old_home(env)


def post_init_hook(env):
    """Hide the grocery categories, now that the parts ones have replaced them."""
    Category = env['product.public.category'].sudo()
    stale = Category.with_context(active_test=False).search(
        [('mart_slug', 'in', HIDE), ('mart_in_app', '=', True)])
    if stale:
        stale.write({'mart_in_app': False})
        _logger.info('369 Mart parts: hid %s grocery categories', len(stale))


def uninstall_hook(env):
    """Put back everything the two install hooks switched off."""
    Category = env['product.public.category'].sudo()
    hidden = Category.with_context(active_test=False).search(
        [('mart_slug', 'in', HIDE), ('mart_in_app', '=', False)])
    if hidden:
        hidden.write({'mart_in_app': True})
    _restore_old_home(env)
