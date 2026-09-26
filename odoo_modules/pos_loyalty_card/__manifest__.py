{
    'name': 'POS Loyalty Card',
    'version': '19.0.1.78.0',
    'category': 'Point of Sale',
    'summary': 'Simple loyalty card system with points redemption & WhatsApp Neonize integration',
    'description': """
        Custom Loyalty Card System for POS
        - Search/Create loyalty cards by phone
        - Earn points on purchases
        - Redeem points as discount
        - WhatsApp integration via Neonize (pure Python, no Node.js)
        - Welcome message with card image on new card creation
        - Receipt message on every purchase
        - Print loyalty card (configurable size)
    """,
    'author': 'Alphalize',
    'depends': ['point_of_sale', 'mail', 'contacts'],
    'external_dependencies': {'python': ['PIL', 'barcode']},
    'post_init_hook': '_post_init_hook',
    'data': [
        'security/whatsapp_security.xml',
        'security/ir.model.access.csv',
        'data/sequence_data.xml',
        'data/loyalty_product_data.xml',
        'data/default_rule.xml',
        # === Report files (integrated from File 2 for WhatsApp/Print UI) ===
        'report/loyalty_card_report.xml',
        'report/loyalty_card_template.xml',
        # === Wizard ===
        'wizard/loyalty_delete_confirm_wizard_views.xml',
        'views/customer_details_views.xml',
        'views/loyalty_card_views.xml',
        'views/loyalty_history_views.xml',
        'views/loyalty_rule_views.xml',
        'views/pos_config_views.xml',
        'views/menu_views.xml',
        'views/whatsapp_session_views.xml',
        'views/whatsapp_config_views.xml',
        'views/whatsapp_message_views.xml',
        'views/whatsapp_res_partner_views.xml',
        'views/whatsapp_send_message_wizard_views.xml',
        'views/whatsapp_menu.xml',
        'views/whatsapp_campaign_views.xml',
        # Card print settings (menu references menu_loyalty_root from menu_views.xml)
        'views/loyalty_card_settings_views.xml',
        # === Card image gallery / download / retention ===
        'views/pos_loyalty_card_image_views.xml',
        'wizard/loyalty_card_image_download_wizard_views.xml',
        'data/ir_cron_card_image.xml',
        'data/whatsapp_cron.xml',
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
        'point_of_sale._assets_pos': [
            'pos_loyalty_card/static/src/css/loyalty.css',
            'pos_loyalty_card/static/src/css/loyalty_redemption.css',
            'pos_loyalty_card/static/src/js/loyalty.js',
            'pos_loyalty_card/static/src/js/loyalty_redemption.js',
            'pos_loyalty_card/static/src/js/loyalty_receipt.js',
            'pos_loyalty_card/static/src/js/loyalty_return_filter.js',
            'pos_loyalty_card/static/src/xml/loyalty.xml',
            'pos_loyalty_card/static/src/xml/loyalty_redemption.xml',
            'pos_loyalty_card/static/src/xml/loyalty_receipt.xml',
            # Hide LOYALTY_DISCOUNT marker from orderline display
            'pos_loyalty_card/static/src/xml/loyalty_orderline.xml',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
