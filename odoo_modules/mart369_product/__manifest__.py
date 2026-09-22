{
    'name': '369 Mart Product Page',
    'version': '19.0.1.5.0',
    'category': 'Website',
    'summary': 'Decide what the 369 Mart app shows on a product page - for '
               'every product at once, or one product at a time.',
    'description': """
369 Mart Product Page
=====================

The product page in the app shows about fifty things: the price and photos,
a key-features list, the product-information table, specifications, the
description, the return policy, ratings and reviews.

This module decides **which of them a customer actually sees**, and where the
wording comes from:

* a switch per field that applies to the whole shop;
* the same switch per product - *follow the shop*, *always show*, or
  *always hide* - so one product can differ without drifting from the rest;
* wording set once for the shop, refined per category, and overridden on a
  single product only where it really differs.

Edit it all in **369 Mart > Product Page**: the real page, wide, with a
switch on every part of it. "More settings" opens the same page in a phone
frame with every field listed. The app reads the result from
``/369mart/product/<id>``.
""",
    'author': '369 Mart',
    'license': 'LGPL-3',
    # mart369_home is real, not incidental: both product screens import Icon,
    # useSaveQueue and the SaveChip template from it. The chrome itself now
    # lives in mart369's builder.scss, next to the home page's, so this is the
    # only cross-module dependency left to keep in mind.
    'depends': [
        'mart369', 'mart369_home', 'website_sale', 'rating', 'portal_rating'],
    'data': [
        'security/ir.model.access.csv',
        'views/registry_views.xml',
        'views/product_template_views.xml',
        'views/product_builder_views.xml',
        'views/menus.xml',
        'data/sections.xml',
        'data/fields.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'mart369_product/static/src/scss/storefront_pdp.scss',
            'mart369_product/static/src/builder/**/*',
        ],
        'web.assets_tests': [
            'mart369_product/static/tests/tours/**/*',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
