"""Sub-categories are drawn in their own colours from 19.0.1.3.0.

Before, a sub-category's circle always took its main category's colours and
its own were never shown - so a sub-category made from the desk kept the field
defaults. Left alone, every such circle would turn grey-blue the day the app
starts reading them. Give those the main category's colours, which is what
the shopper has been seeing all along. Sub-categories with colours of their
own (the parts demo sets them) are not touched.
"""


def migrate(cr, version):
    cr.execute("""
        UPDATE product_public_category sub
           SET mart_tone = main.mart_tone,
               mart_accent = main.mart_accent
          FROM product_public_category main
         WHERE sub.parent_id = main.id
           AND lower(coalesce(sub.mart_tone, '#f4f6f8')) = '#f4f6f8'
           AND lower(coalesce(sub.mart_accent, '#0b4a6e')) = '#0b4a6e'
    """)
