{
    'name': '369 Mart Catalog',
    'version': '19.0.1.0.0',
    'category': 'Website',
    'summary': 'Categories, browsing and search for the 369 Mart app.',
    'description': """
369 Mart Catalog
================

The app's category pages and its search box.

Odoo already knows the products; this module decides how they are grouped for
the app - which categories exist, what they are called, the colour behind each
one, and which products sit under them. It also answers the search box, and
remembers what people looked for so "Trending" is real rather than a guess.

Three values the app used to invent for itself now come from Odoo: a product's
rating, how popular it is, and its brand. The app was deriving all three from
a hash of the product id, which meant "sort by customer rating" sorted by
nothing at all.

The app reads it from ``/369mart/catalog``, ``/369mart/browse/<category>`` and
``/369mart/search``.
""",
    'author': '369 Mart',
    'license': 'LGPL-3',
    'depends': [
        'mart369','mart369_product'],
    'data': [
        'security/ir.model.access.csv',
        # Seeds once and guards itself, so it is safe on every upgrade - see
        # the file's own comment.
        'data/search_demo.xml',
        'views/category_views.xml',
        'views/search_views.xml',
        'views/search_desk_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            # The shared chrome (.mart-builder, .mart-btn, the error bar and
            # the loading line) comes from mart369's builder.scss, which is
            # already in the bundle because mart369 is a dependency. Never
            # @import it: one local @import breaks the whole backend bundle.
            'mart369_catalog/static/src/desk/**/*',
        ],
    },
    'images': [
        'static/description/catalog_board.png',
        'static/description/catalog_list.png',
        'static/description/category_form.png',
        # The searches desk: the demand list, with what found nothing marked.
        'static/description/search_desk.png',
        'static/description/searches.png',
    ],
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
    'auto_install': False,
}
