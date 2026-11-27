{
    'name': 'WhatsApp and Email Integration',
    'version': '19.0.5.15.1',
    'category': 'Tools',
    'summary': 'Email + auto-send (Sales / Purchase / POS / Invoices) on top of the shared whatsapp_gateway session',
    'description': """
WhatsApp + Email auto-send for 369ai 19
=======================================

This module adds Email sending and cross-channel auto-send (quotations,
sale orders, purchase orders, vendor bills, customer invoices, payment
receipts, POS) on top of the WhatsApp sessions provided by the ``whatsapp_gateway`` module.
Each company sends from the number and e-mail chosen for it (its own, or one
shared by all companies).

It does NOT manage its own WhatsApp connection — it reuses the one
``whatsapp.session`` owned by ``whatsapp_gateway`` (exactly like
``whatsapp_broadcast`` does), so there is a single QR / single session
shared across every module.
    """,
    'author': 'Alphalize Technologies',
    'website': 'https://www.alphalize.com',
    'depends': [
        'whatsapp_gateway',
        'mail', 'contacts',
        'sale', 'purchase', 'account',
        # models/pos_order.py inherits pos.order. Without this the module does
        # not merely lose the POS feature - it fails to install.
        'point_of_sale',
    ],
    'data': [
        'security/whatsapp_security.xml',
        'security/ir.model.access.csv',
        'views/whatsapp_config_views.xml',
        'views/whatsapp_session_main_views.xml',
        'wizards/send_channel_wizard_views.xml',
        'wizards/session_company_wizard_views.xml',
        'views/email_session_views.xml',
        'views/sale_order_views.xml',
        'views/purchase_order_views.xml',
        'views/account_payment_send_views.xml',
        'views/account_move_views.xml',
        'views/help_document_views.xml',
        # menu.xml loads LAST so all referenced actions + parent menus exist.
        'views/menu.xml',
        'data/ir_cron.xml',
        'data/help_document_data.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'whatsapp_email/static/src/js/help_documents.js',
            'whatsapp_email/static/src/xml/help_documents.xml',
        ],
    },
    'images': ['static/description/icon.png'],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
    'post_init_hook': '_post_init_hook',
}
