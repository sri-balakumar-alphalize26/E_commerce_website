"""Generate data/fields.xml - the catalogue of everything the product page
can show.

Run from the module root:  python tools/gen_fields_xml.py

Editing the table below and re-running is the way to add a field; the seeded
record then appears in 369 Mart > Product Page with its own switch.
"""
import io
import pathlib
from xml.etree import ElementTree
from xml.sax.saxutils import escape

HERE = pathlib.Path(__file__).resolve().parent.parent
OUT = HERE / 'data' / 'fields.xml'

DISCLAIMER = ("While we work to ensure product information is correct, "
              "packaging and ingredients may be updated by the manufacturer. "
              "Always read the label before use.")
RETURN_TEXT = ("7-day replacement for damaged or wrong items. Keep the "
               "original packaging.")

# key, label, section, source, odoo_field, default, kind, per_product, note
FIELDS = [
    # -- photos --
    ('images', 'Photos', 'gallery', 'computed', '', '', 'text', 1,
     'Every picture on the product.'),
    ('unit_tag', 'Size tag on the photo', 'gallery', 'odoo', 'mart_unit_text', '', 'text', 1,
     'e.g. 1 kg, shown over the image.'),

    # -- buy box --
    ('brand', 'Brand', 'buy', 'text', '', '369 Mart Select', 'text', 1,
     'The link above the product name.'),
    ('name', 'Product name', 'buy', 'odoo', 'name', '', 'text', 0,
     'Always shown - a page without a name would be useless.'),
    ('rating_summary', 'Star rating', 'buy', 'computed', '', '', 'text', 1,
     'The 4.3 and the stars under the name.'),
    ('price', 'Price', 'buy', 'odoo', 'list_price', '', 'text', 0,
     'Always shown.'),
    ('mrp', 'MRP and discount', 'buy', 'odoo', 'compare_list_price', '', 'text', 1,
     'The struck-through price and the per-cent-off pill.'),
    ('per_unit', 'Price per unit', 'buy', 'computed', '', '', 'text', 1,
     'e.g. 17.25 per 250 g.'),
    ('low_stock', 'Only-N-left warning', 'buy', 'computed', '', '', 'text', 1,
     'Nudges the customer when stock runs low.'),
    ('pack_sizes', 'Pack sizes', 'buy', 'computed', '', '', 'text', 1,
     'The 1 kg / 5 kg / 10 kg chooser.'),
    ('delivery_mode', 'Delivery speed badge', 'buy', 'computed', '', '', 'text', 1,
     'Quick in 10-20 mins, or Express with the number of days.'),
    ('wishlist', 'Save-to-list button', 'buy', 'computed', '', '', 'bool', 0,
     'The heart button.'),
    ('share', 'Share button', 'buy', 'computed', '', '', 'bool', 0, ''),

    # -- key features --
    ('features', 'Key features', 'features', 'odoo', 'mart_features', '', 'lines', 1,
     'One per line. Falls back to the category default.'),

    # -- product information --
    ('info_brand', 'Brand', 'info', 'text', '', '369 Mart Select', 'text', 1, ''),
    ('sold_by', 'Sold by', 'info', 'text', '', '369 Mart Retail', 'text', 1,
     'Who the customer is buying from.'),
    ('country_of_origin', 'Country of origin', 'info', 'text', '', 'India', 'text', 1,
     'Required on most marketplaces.'),
    ('manufacturer_name', 'Manufacturer name', 'info', 'text', '', '', 'text', 1,
     'Legally required for packaged goods in India.'),
    ('manufacturer_address', 'Manufacturer address', 'info', 'text', '', '', 'text', 1,
     'Legally required for packaged goods in India.'),
    ('article_id', 'Article ID', 'info', 'odoo', 'default_code', '', 'text', 1,
     'The internal reference.'),
    ('veg', 'Vegetarian mark', 'info', 'odoo', 'mart_is_veg', '', 'bool', 1,
     'The green square. Food products only.'),
    ('item_height', 'Item height', 'info', 'odoo', 'mart_item_height', '', 'text', 1, ''),
    ('item_length', 'Item length', 'info', 'odoo', 'mart_item_length', '', 'text', 1, ''),
    ('item_width', 'Item width', 'info', 'odoo', 'mart_item_width', '', 'text', 1, ''),
    ('net_weight', 'Net weight', 'info', 'odoo', 'weight', '', 'text', 1,
     'Taken from the weight on the product.'),

    # -- specifications --
    ('net_quantity', 'Net quantity', 'specs', 'odoo', 'mart_unit_text', '', 'text', 1, ''),
    ('spec_brand', 'Brand', 'specs', 'text', '', '369 Mart Select', 'text', 1, ''),
    ('warranty', 'Warranty', 'specs', 'text', '', '', 'text', 1,
     'e.g. 1 year manufacturer warranty. Usually set per category.'),
    ('in_the_box', 'In the box', 'specs', 'odoo', 'mart_in_the_box', '', 'text', 1, ''),
    ('material', 'Material', 'specs', 'odoo', 'mart_material', '', 'text', 1, ''),
    ('product_type', 'Product type', 'specs', 'computed', '', '', 'text', 1,
     'The category the product sits in.'),
    ('shelf_life', 'Shelf life', 'specs', 'text', '', '', 'text', 1,
     'e.g. 3-5 days, refrigerated. Usually set per category.'),

    # -- description --
    ('description', 'Description', 'description', 'odoo', 'description_ecommerce', '',
     'html', 1, 'The long text. Falls back to the sales description.'),
    ('disclaimer', 'Disclaimer', 'description', 'text', '', DISCLAIMER, 'text', 1,
     'Shown under the description.'),

    # -- returns --
    ('returnable', 'Returnable', 'returns', 'text', '', 'yes', 'bool', 1,
     'Whether this can be returned at all.'),
    ('return_text', 'Return policy wording', 'returns', 'text', '', RETURN_TEXT, 'text', 1,
     'Usually set per category.'),
    ('policy_link', 'View-policy link', 'returns', 'text', '', '/cancellation-policy',
     'text', 1, 'Where the link goes. That page must exist on the storefront.'),

    # -- reviews --
    ('rating', 'Average rating', 'reviews', 'computed', '', '', 'text', 1,
     'Worked out from real customer reviews.'),
    ('rating_count', 'Number of ratings', 'reviews', 'computed', '', '', 'text', 1, ''),
    ('rating_bars', 'Star breakdown', 'reviews', 'computed', '', '', 'text', 1,
     'The five-star to one-star bars.'),
    ('reviews', 'Customer reviews', 'reviews', 'computed', '', '', 'text', 1,
     'Written by customers who bought the product.'),
    ('review_empty', 'Be-the-first-to-review line', 'reviews', 'text', '',
     'Be the first to review this product', 'text', 1,
     'Shown instead of the block when there are no reviews yet.'),

    # -- delivery --
    ('address', 'Delivery address', 'delivery', 'computed', '', '', 'text', 0,
     "The customer's own address."),
    ('explore_category', 'Explore-more link', 'delivery', 'computed', '', '', 'text', 1, ''),

    # -- bundle and similar --
    ('bundle_items', 'Frequently bought together', 'bundle', 'computed', '', '', 'text', 1,
     'Uses the accessories set on the product, or picks them automatically.'),
    ('similar_items', 'Similar products', 'similar', 'computed', '', '', 'text', 1,
     'Uses the alternative products set on the product, or the same category.'),
    ('related_items', 'Others you may also like', 'similar', 'computed', '', '', 'text', 1, ''),
    ('recently_viewed', 'Recently viewed', 'similar', 'computed', '', '', 'text', 1, ''),
]


def build():
    rows = []
    for i, (key, label, sec, source, odoo_field, default, kind, per_product, note) in \
            enumerate(FIELDS, start=1):
        out = [
            '        <record id="f_%s" model="mart369.product.field">' % key,
            '            <field name="key">%s</field>' % key,
            '            <field name="name">%s</field>' % escape(label),
            '            <field name="section_id" ref="sec_%s"/>' % sec,
            '            <field name="sequence">%d</field>' % (i * 10),
            '            <field name="source">%s</field>' % source,
            '            <field name="value_kind">%s</field>' % kind,
        ]
        if odoo_field:
            out.append('            <field name="odoo_field">%s</field>' % odoo_field)
        if default:
            out.append('            <field name="default_value">%s</field>' % escape(default))
        if not per_product:
            out.append('            <field name="per_product" eval="False"/>')
        if note:
            out.append('            <field name="note">%s</field>' % escape(note))
        out.append('        </record>')
        rows.append('\n'.join(out))

    return (
        '<?xml version="1.0" encoding="utf-8"?>\n<odoo>\n'
        '    <!-- Everything the product page can show. Generated by\n'
        '         tools/gen_fields_xml.py - edit the table there and re-run.\n'
        '         noupdate="1" so an upgrade never switches back on something\n'
        '         the shop deliberately switched off. -->\n'
        '    <data noupdate="1">\n\n' + '\n\n'.join(rows) + '\n\n    </data>\n</odoo>\n')


if __name__ == '__main__':
    keys = [f[0] for f in FIELDS]
    assert len(keys) == len(set(keys)), 'duplicate field key'
    OUT.write_text(build(), encoding='utf-8', newline='\n')
    ElementTree.parse(OUT)
    print('wrote %s - %d fields across %d sections'
          % (OUT, len(FIELDS), len({f[2] for f in FIELDS})))
