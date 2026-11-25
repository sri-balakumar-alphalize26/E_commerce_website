{
    'name': 'WhatsApp & Email Connector',
    'version': '19.0.3.1.15',
    'category': 'Tools',
    'summary': 'Send and receive WhatsApp through an Evolution API gateway',
    'description': """
        WhatsApp for 369ai 19, via an Evolution API gateway
        ===================================================

        WhatsApp no longer runs inside 369ai. A separate gateway holds the
        connection; 369ai sends HTTP requests to it and receives incoming
        messages back on a webhook.

        What that changes
        -----------------
        * The QR is scanned once, on the gateway - not per database, and never
          again after a restart.
        * Any 369ai worker can send. There is no client to own, so there is no
          ownership election, no heartbeat, and no "WhatsApp is not connected"
          from a worker that simply was not the one holding the socket.
        * No Python WhatsApp library is needed on the 369ai server at all.

        Protecting a shared number
        --------------------------
        One number can serve several tenants. Because a ban would take all of
        them down at once, this module enforces an opt-out list, a per-database
        daily cap, duplicate suppression, and a deliberate switch before bulk
        sending is allowed.

        Setup
        -----
        Point the session at the gateway URL, paste its API key, name the
        instance, then press Test Connection and Register Webhook.
    """,
    'author': 'Alphalize Technologies',
    'website': 'https://www.alphalize.com',
    # No point_of_sale. It was here for one file, and it meant every client
    # installing the connector to send WhatsApp and email also got Point of
    # Sale, with stock and accounting behind it. POS notifications live in
    # whatsapp_gateway_pos now.
    'depends': ['base', 'mail', 'contacts'],
    'data': [
        'security/whatsapp_security.xml',
        'security/ir.model.access.csv',
        'views/whatsapp_session_views.xml',
        'views/whatsapp_number_off_views.xml',
        'views/whatsapp_connect_try_views.xml',
        'views/whatsapp_optout_views.xml',
        'views/whatsapp_message_views.xml',
        'views/whatsapp_config_views.xml',
        'wizards/send_message_wizard_views.xml',
        'views/res_partner_views.xml',
        'views/menu.xml',
        'data/ir_cron.xml',
    ],
    # No external_dependencies. `requests` ships with Odoo, and neonize,
    # qrcode and Pillow are no longer used - the gateway owns all of that.
    'assets': {
        'web.assets_backend': [
            'whatsapp_gateway/static/src/phone/phone_data.js',
            'whatsapp_gateway/static/src/phone/phone_field.scss',
            'whatsapp_gateway/static/src/phone/phone_field.xml',
            'whatsapp_gateway/static/src/phone/phone_field.js',
            'whatsapp_gateway/static/src/connect/connect.scss',
            'whatsapp_gateway/static/src/connect/connect.xml',
            'whatsapp_gateway/static/src/connect/connect.js',
        ],
    },
    'images': ['static/description/icon.png'],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
    'post_init_hook': '_post_init_hook',
}
