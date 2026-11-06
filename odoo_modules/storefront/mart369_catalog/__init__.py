from . import models
from . import controllers


def post_init_hook(env):
    """Give every category that already existed an app address.

    The slug is filled in on create and on write, which covers everything made
    from now on - but a database installing this module already has categories,
    and without a slug the app cannot address them at all: /369mart/catalog
    would list them with an empty slug and every /369mart/browse would 404.

    Idempotent, so re-running an upgrade is harmless, and it never touches a
    category that already has one.
    """
    Category = env['product.public.category'].sudo().with_context(active_test=False)
    for category in Category.search([('mart_slug', 'in', [False, ''])], order='id'):
        category.mart_slug = Category._mart369_free_slug(category.name, ignore=category.id)
    hide_sample_categories(env)


# The five categories mart369_home installs for its grocery example page.
SAMPLE_CATEGORIES = ('categ_fruits', 'categ_staples', 'categ_tech',
                     'categ_home', 'categ_office')


def hide_sample_categories(env):
    """Keep the example page's categories out of the app while they are empty.

    "Fresh Fruits" and "Daily Essentials" led the category list of a shop
    that sells laptop parts. Hidden, not deleted: one a shop has put products
    into is left showing, and switching one back on is a tick in Catalogue >
    Categories.
    """
    Template = env['product.template'].sudo()
    for xmlid in SAMPLE_CATEGORIES:
        category = env.ref('mart369_home.%s' % xmlid, raise_if_not_found=False)
        if not category or not category.mart_in_app:
            continue
        if Template.search_count(category._mart369_product_domain(), limit=1):
            continue
        category.mart_in_app = False
