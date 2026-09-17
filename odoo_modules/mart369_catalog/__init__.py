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
