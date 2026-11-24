{
    'name': 'Sales Automation (WhatsApp Groups)',
    'version': '19.0.173.53.0',
    'category': 'Sales',
    'summary': 'Turn WhatsApp group enquiries into sale orders',
    'description': """
        Sales Automation for WhatsApp Groups
        ====================================

        whatsapp_employee_tracker already sells one-to-one: it searches the
        catalog, quotes, bargains, takes a quantity, creates the sale order,
        collects an address, takes payment and sends the invoice. All of it
        only ever runs in a direct chat.

        This module extends that reach to groups.

        A company number sits in many groups. Sync them, tick the ones that
        are sales groups, and every message posted there is classified: is
        this a product enquiry, or ordinary chatter? An enquiry is looked up
        in the catalog, checked against stock, and - when stock is out -
        priced from the vendors already registered on the product.

        The group only ever sees an acknowledgement. Price, bargaining,
        quantity, delivery address and payment all move to a private chat
        with the person who asked, so no member sees another member's deal.

        From that first direct message onwards the tracker's own engine owns
        the conversation. Nothing about the selling flow is reimplemented
        here.
    """,
    'author': 'Alphalize Technologies',
    'website': 'https://www.alphalize.com',
    # whatsapp_employee_tracker brings whatsapp_gateway, hr, sale_management,
    # sale_stock, stock, account and payment with it. product.supplierinfo and
    # product_template.seller_ids live in `product`, which sale_management
    # already depends on - `purchase` is not needed and would drag a whole
    # application in for two read-only fields.
    'depends': ['whatsapp_employee_tracker'],
    'data': [
        'security/sales_automation_security.xml',
        'security/ir.model.access.csv',
        'views/product_category_views.xml',
        'views/sales_group_views.xml',
        'views/sa_group_request_views.xml',
        'views/sa_vendor_quote_views.xml',
        'views/sa_brand_layout.xml',
        'views/quote_entry_templates.xml',
        'views/sa_portal_brand.xml',
        'views/sa_payment_brand.xml',
        'views/sa_review_page.xml',
        'views/sa_pay_link_views.xml',
        'views/sa_group_picker_views.xml',
        'views/sa_ai_settings_views.xml',
        # menu.xml before the settings sections: they hang under menu_sa_config
        'views/menu.xml',
        'views/sa_settings_section_views.xml',
        'views/sa_address_link_views.xml',
        'views/product_template_views.xml',
        'views/whatsapp_session_views.xml',
        'data/ir_cron.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'sales_automation/static/src/preview/preview_text.js',
            'sales_automation/static/src/preview/live_preview.js',
            'sales_automation/static/src/preview/live_preview.xml',
            'sales_automation/static/src/preview/live_preview.scss',
        ],
        # the customer's order page (views/sa_portal_brand.xml); every rule
        # sits under .sa-page, so the rest of the website is untouched
        'web.assets_frontend': [
            'sales_automation/static/src/css/sa_portal.css',
            'sales_automation/static/src/js/sa_portal_order.js',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
