{
    'name': '369 Mart Pages',
    'version': '19.0.1.1.0',
    'summary': 'The shop footer\'s pages - Terms, Privacy, About, Help, Contact - edited in Odoo',
    'description': """
Every page the shop's footer links to, kept in Odoo and drawn by the shop in
its own look: Terms of use, Privacy, Shipping, Cancellations & returns,
Grievance redressal, About, Careers, Sell on 369 Mart, Press, Contact us,
FAQs and Delivery areas.

369 Mart > Page building > Info pages: write each one with Odoo's own editor
(bullets, headings, bold, links), see the real shop page beside it, and
choose which footer column it sits in. FAQs are questions and answers; the
Contact page adds the shop's phone, email and address; Delivery areas lists
the pincodes the shop serves.
""",
    'author': 'Alphalize',
    'license': 'LGPL-3',
    'category': 'Website',
    'depends': ['mart369', 'mart369_product', 'mart369_catalog', 'html_editor'],
    'data': [
        'security/ir.model.access.csv',
        'views/info_page_views.xml',
        'views/footer_views.xml',
        'data/info_pages.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'mart369_pages/static/src/**/*',
        ],
    },
    'installable': True,
}
