"""Repair About this item and Description saved as code.

The Word-style box (19.0.1.6.0) opened a saved text as plain characters, so
saving again stored the formatting itself as words: "<div><strong>Display
</strong> - ...</div>" printed on the form and on the shop. Such a field's
plain text is itself HTML; it is written back as the HTML it spells. A field
saved correctly has no tags in its plain text and is left alone, so running
this twice changes nothing.
"""

import re

from odoo import SUPERUSER_ID, api
from odoo.tools import html2plaintext

TAGS = re.compile(r'<\s*/?\s*(div|p|strong|b|ul|ol|li|br|em|i|u|span|h[1-6])\b', re.I)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Product = env['product.template'].with_context(active_test=False)
    for name in ('mart_about_html', 'description_ecommerce'):
        if name not in Product._fields:
            continue
        for product in Product.search([(name, '!=', False)]):
            value = str(product[name] or '')
            text = html2plaintext(value)
            if TAGS.search(text):
                product[name] = text
