{
    'name': 'WhatsApp and Email - WA Tracker link',
    'version': '19.0.1.0.0',
    'category': 'Tools',
    'summary': 'Numbers connected in WA Tracker become choosable as a company\'s main WhatsApp / e-mail',
    'description': """
Installs by itself where both WhatsApp and Email and WA Tracker are installed.

* WA Tracker > Configuration > Companies (WhatsApp and Email): every company and
  branch with its numbers; tick the main number and the main e-mail. Numbers
  WA Tracker connected already are only linked, never scanned again.
* "Connect a new number for this company" from WhatsApp and Email settings
  asks for no employee: the number belongs to the company.

Each module still works alone: whatsapp_gateway is the common base, and
WhatsApp and Email, WA Tracker and Sales Automation never need each other.
    """,
    'author': 'Alphalize Technologies',
    'website': 'https://www.alphalize.com',
    'depends': ['whatsapp_email', 'whatsapp_employee_tracker'],
    'data': [
        'views/menu.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'whatsapp_email_tracker/static/src/js/connect_company.js',
            'whatsapp_email_tracker/static/src/xml/connect_company.xml',
        ],
    },
    'images': ['static/description/icon.png'],
    'installable': True,
    'auto_install': True,
    'application': False,
    'license': 'LGPL-3',
}
