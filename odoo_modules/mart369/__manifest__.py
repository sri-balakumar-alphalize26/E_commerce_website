{
    'name': '369 Mart',
    'version': '19.0.2.0.0',
    'category': 'Website',
    'summary': 'The foundation every 369 Mart module is built on.',
    'description': """
369 Mart
========

The base. It holds the few things the whole suite shares and nothing else:

* the **369 Mart menu** every module hangs its own screens off;
* the **settings** they all read - where images are served from, and how long
  the app may reuse an answer;
* the **JSON helpers** that turn a product into the shape the app expects, so
  the cart, the catalogue, the product page and orders all describe a product
  identically;
* the **colours** the builder screens are drawn with.

Every other 369 Mart module depends on this one and can be installed or removed
on its own. This used to be the home page's job, which meant removing the home
page took the menu - and every other module's screens - with it.

Install **369 Mart Suite** to get the whole thing in one go, or pick the pieces
you want from the Apps list.
""",
    'author': '369 Mart',
    'license': 'LGPL-3',
    # `website` because security/ir.model.access.csv grants to
    # website.group_website_designer - the group the whole suite uses for
    # "staff who may edit the storefront", named in about forty places.
    # Without it this module cannot install on a database that has no
    # website, and since everything depends on this one, nor can anything
    # else: the whole suite was uninstallable from scratch.
    'depends': ['base', 'web', 'product', 'website'],
    'data': [
        'security/ir.model.access.csv',
        'views/menus.xml',
        'views/config_views.xml',
        'views/product_template_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            # Before anything else, so it runs before the web client starts:
            # the top bar is always drawn from the server, never from a copy
            # the browser kept from before the menus were regrouped.
            'mart369/static/src/menus_fresh.js',
            # Listed first so the modules after it can use $mart-*. Never
            # @import this file: Odoo rejects local imports inside a bundle.
            'mart369/static/src/scss/_mart_vars.scss',
            # The shared UI kit - the button, the pill, the dropdown, the search
            # box, the tab strip, the toggle, the avatar and the empty state that
            # every desk and both builders draw with. Listed after _mart_vars,
            # whose $mart-* tokens it uses: a bundle compiles in the order it is
            # listed, and a local @import is not an option. Spelled out one file
            # at a time rather than globbed, so that order stays visible.
            'mart369/static/src/ui/kit.scss',
            'mart369/static/src/ui/icon.js',
            'mart369/static/src/ui/icon.xml',
            'mart369/static/src/ui/pick.js',
            'mart369/static/src/ui/pick.xml',
            'mart369/static/src/ui/switch.js',
            'mart369/static/src/ui/switch.xml',
            'mart369/static/src/ui/search.js',
            'mart369/static/src/ui/search.xml',
            'mart369/static/src/ui/tabs.js',
            'mart369/static/src/ui/tabs.xml',
            'mart369/static/src/ui/pill.js',
            'mart369/static/src/ui/pill.xml',
            'mart369/static/src/ui/avatar.js',
            'mart369/static/src/ui/avatar.xml',
            'mart369/static/src/ui/empty.js',
            'mart369/static/src/ui/empty.xml',
            'mart369/static/src/ui/confirm.js',
            'mart369/static/src/ui/confirm.xml',
            # The builder chrome - the phone frame, the panel, the buttons.
            # Both builder screens (home and product) draw with these.
            'mart369/static/src/builder/builder.scss',
        ],
    },
    'installable': True,
    # An application so it is findable in Apps, and so uninstalling it offers
    # the whole suite - everything depends on this one.
    'application': True,
    'auto_install': False,
}
