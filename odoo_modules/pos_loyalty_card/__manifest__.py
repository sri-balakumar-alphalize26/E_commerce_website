{
    'name': 'Loyalty Card',
    'version': '19.0.2.0.0',
    'category': 'Sales',
    'summary': 'Loyalty cards keyed by mobile number, a points rule and a points history',
    'description': """
        Custom Loyalty Card System
        - Search/Create loyalty cards by phone
        - A points rule: spend so much, earn so many; so many points to the rupee
        - Points history per card
        - Print loyalty card (configurable size), card images, email the card

        19.0.2.0.0: no longer needs Point of Sale, and no longer carries its
        own WhatsApp. Earning and spending are done by whichever module sells -
        369 Mart's orders do it through mart369_loyalty - and WhatsApp belongs
        to the shop's WhatsApp connector. The technical name and the
        pos.loyalty.* models are kept so existing cards and history carry over.
    """,
    'author': 'Alphalize',
    'depends': ['mail', 'contacts'],
    'external_dependencies': {'python': ['PIL', 'barcode']},
    'data': [
        'security/loyalty_security.xml',
        'security/ir.model.access.csv',
        'data/sequence_data.xml',
        'data/default_rule.xml',
        'report/loyalty_card_report.xml',
        'report/loyalty_card_template.xml',
        'wizard/loyalty_delete_confirm_wizard_views.xml',
        'views/customer_details_views.xml',
        'views/loyalty_card_views.xml',
        'views/loyalty_history_views.xml',
        'views/loyalty_rule_views.xml',
        'views/menu_views.xml',
        # Card print settings (menu references menu_loyalty_root from menu_views.xml)
        'views/loyalty_card_settings_views.xml',
        # === Card image gallery / download / retention ===
        'views/pos_loyalty_card_image_views.xml',
        'wizard/loyalty_card_image_download_wizard_views.xml',
        'data/ir_cron_card_image.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'pos_loyalty_card/static/src/views/loyalty_card_list_controller.js',
            'pos_loyalty_card/static/src/js/loyalty_card_preview.js',
            'pos_loyalty_card/static/src/xml/loyalty_card_preview.xml',
            'pos_loyalty_card/static/src/js/loyalty_card_number_preview.js',
            'pos_loyalty_card/static/src/xml/loyalty_card_number_preview.xml',
            'pos_loyalty_card/static/src/js/loyalty_active_toggle.js',
            'pos_loyalty_card/static/src/xml/loyalty_active_toggle.xml',
            'pos_loyalty_card/static/src/js/loyalty_mobile_field.js',
            'pos_loyalty_card/static/src/xml/loyalty_mobile_field.xml',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
