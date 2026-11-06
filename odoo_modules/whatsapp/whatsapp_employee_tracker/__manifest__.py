{
    'name': 'Employee Tracker & Sales Agent',
    'version': '19.0.1.3.0',
    'category': 'Human Resources',
    'summary': 'Track & monitor employee WhatsApp communications on company numbers',
    'description': """
        WhatsApp Employee Communication Tracker
        =========================================

        Monitor and analyze employee WhatsApp usage on company-provided numbers.
    """,
    'author': 'Alphalize Technologies',
    'website': 'https://www.alphalize.com',
    'depends': ['whatsapp_gateway', 'hr', 'sale_management', 'sale_stock', 'stock', 'account', 'payment'],
    'data': [
        'security/ir.model.access.csv',
        'security/tracker_security.xml',
        'data/alert_keywords_data.xml',
        'data/ir_cron.xml',
        'views/employee_session_views.xml',
        'views/communication_log_views.xml',
        'views/conversation_views.xml',
        'views/chat_views.xml',
        'views/keyword_alert_views.xml',
        'views/quality_score_views.xml',
        'views/auto_reply_views.xml',
        'views/message_tone_views.xml',
        'views/tone_report_views.xml',
        'views/response_time_views.xml',
        'views/voice_config_views.xml',
        'views/voice_test_views.xml',
        'views/product_template_views.xml',
        'views/dashboard_views.xml',
        'views/menu.xml',
        'views/help_views.xml',
        'views/payment_sim_templates.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
    'assets': {
        'web.assets_backend': [
            'whatsapp_employee_tracker/static/src/css/wa_chat_style.css',
            'whatsapp_employee_tracker/static/src/js/chat_view.js',
            'whatsapp_employee_tracker/static/src/xml/chat_view.xml',
        ],
    },
}