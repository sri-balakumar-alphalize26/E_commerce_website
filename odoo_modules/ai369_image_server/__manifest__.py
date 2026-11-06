{
    "name": "369ai Image Server Connector",
    "version": "19.0.1.5.4",
    "summary": "Keep every image (products, gallery, employees, any module) on the 369ai image server — "
               "the database keeps only the link, screens load images straight from the image server.",
    "description": """
Images are stored on the image server instead of the local filestore:

* every image field of every module (installed now or later) is handled automatically
* product images use the image server folders: products/<category>/<brand>/<reference>/main.webp
* backend, POS and website load images directly from the image server URL (no image bytes through the ERP)
* existing images can be moved in the background, and brought back at any time
* if the image server is unreachable the image is kept locally and uploaded later automatically
""",
    "author": "Alphalize Technologies",
    "website": "https://369ai.biz",
    "category": "Productivity",
    "license": "LGPL-3",
    "depends": ["base_setup", "product"],
    "external_dependencies": {"python": ["requests"]},
    "data": [
        "security/ir.model.access.csv",
        "data/ir_cron.xml",
        "views/res_config_settings_views.xml",
        "views/ir_attachment_views.xml",
        "views/product_template_views.xml",
        "wizard/imgsrv_migration_views.xml",
        "views/menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "ai369_image_server/static/src/js/image_field_direct.js",
            "ai369_image_server/static/src/xml/image_field_direct.xml",
            "ai369_image_server/static/src/scss/image_field_direct.scss",
        ],
    },
    "installable": True,
    "application": True,
    "uninstall_hook": "uninstall_hook",
}
