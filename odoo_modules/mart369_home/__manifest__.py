{
    'name': '369 Mart Home Page',
    'version': '19.0.1.0.0',
    'category': 'Website',
    'summary': 'Configure the 369 Mart app home page - banners, sections and tiles - without touching code.',
    'description': """
369 Mart Home Page
==================

The 369 Mart phone app gets its whole home page from this module.

An operator decides, from Odoo:

* which promo banners show, what they say and in which order;
* which product rows ("Fresh fruits", "Daily essentials", ...) appear,
  what each is called, and where the products come from;
* where a banner strip sits between those rows;
* the round category tiles and the top tab row;
* the free-delivery nudge amount.

Nothing here needs a developer. Drag a row, flip a switch, and the app
picks the change up on its next load.

The app reads it all from ``/369mart/home`` as JSON.
""",
    'author': '369 Mart',
    'license': 'LGPL-3',
    'depends': [
        'mart369','website_sale'],
    'data': [
        'security/ir.model.access.csv',
        'views/home_banner_views.xml',
        'views/home_tile_views.xml',
        'views/home_tab_views.xml',
        'views/home_section_views.xml',
        'views/home_mode_views.xml',
        'views/home_config_views.xml',
        'views/product_template_views.xml',
        'views/builder_views.xml',
        'views/menus.xml',
        'data/home_default_data.xml',
        'data/trash_cron.xml',
    ],
    'assets': {
        # Backend only. storefront.scss is the app's own stylesheet, copied
        # verbatim, so the builder's phone mock looks exactly like the app.
        'web.assets_backend': [
            # the shared palette must come first - siblings import it too
            'mart369_home/static/src/scss/home_preview.scss',
            'mart369_home/static/src/scss/storefront.scss',
            'mart369_home/static/src/builder/**/*',
        ],
        'web.assets_tests': [
            'mart369_home/static/tests/tours/**/*',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
