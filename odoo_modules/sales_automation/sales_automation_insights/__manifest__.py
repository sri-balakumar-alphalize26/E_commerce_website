# -*- coding: utf-8 -*-
{
    'name': 'Sales Automation - Insights',
    'summary': 'Star ratings for customers and suppliers, with one-page '
               'dashboards and side-by-side comparison',
    'version': '19.0.3.5.0',
    'category': 'Sales',
    'license': 'LGPL-3',
    'author': 'Alphalize',
    # The store module carries the delivery, supply and enquiry-desk fields
    # this reads, and `sa_enquiry_detail`, which the profile page reuses.
    'depends': ['sales_automation_store'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron.xml',
        'views/insight_entity_views.xml',
        'views/conduct_remark_views.xml',
        'views/sa_ai_settings_conduct.xml',
        'views/insights_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'sales_automation_insights/static/src/insights_screen.scss',
            'sales_automation_insights/static/src/components/*.js',
            'sales_automation_insights/static/src/components/*.xml',
            'sales_automation_insights/static/src/insights_screen.js',
            'sales_automation_insights/static/src/insights_screen.xml',
        ],
    },
    'installable': True,
    'application': True,
}
