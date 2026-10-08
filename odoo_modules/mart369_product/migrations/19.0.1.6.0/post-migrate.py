"""About this item becomes a Word-style box (mart_about_html).

A product that already had its points typed one per line (mart_features)
gets them as a bulleted list in the new box, each "Bold phrase — the rest"
with the phrase in bold, so nothing typed before is lost. The lines stay
where they were, as the page's fallback.
"""

from markupsafe import escape

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Product = env['product.template'].with_context(active_test=False)
    Page = env['mart369.product.page']
    for product in Product.search([('mart_features', '!=', False)]):
        if product.mart_about_html and str(product.mart_about_html).strip():
            continue
        points = Page.about(product)
        if not points:
            continue
        items = ''.join(
            '<li>%s%s</li>' % (('<b>%s</b> — ' % escape(p['lead'])) if p['lead'] else '', escape(p['text']))
            for p in points)
        product.mart_about_html = '<ul>%s</ul>' % items
