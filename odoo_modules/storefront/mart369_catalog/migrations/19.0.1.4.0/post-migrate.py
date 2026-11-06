"""Categories carry their own logo from 19.0.1.4.0.

Until now the logo a shopper saw was chosen on the home page, not on the
category: the pill in the top bar had an icon of its own, and each tile a
drawing of its own. Hand each category the logo it has been shown with, so
nothing changes on screen the day the app starts reading the category's:

- a category's built-in mark comes from the pill that opens it;
- its drawing comes from the tile linked to it;
- and a tile that was drawing a picture of its own now wears its category's,
  so changing the logo in Catalogue > Categories changes the tile too.

A category that already has a logo keeps it. Each tile keeps its own drawing
as the fallback for a category with none.
"""


def migrate(cr, version):
    cr.execute("""
        UPDATE product_public_category c
           SET mart_icon = t.icon
          FROM mart369_home_tab t
         WHERE t.route_view = 'category'
           AND t.icon IS NOT NULL
           AND c.mart_icon IS NULL
           AND c.mart_slug = regexp_replace(
                   trim(both '/' from coalesce(t.route_param, '')), '^.*/', '')
    """)
    cr.execute("""
        UPDATE product_public_category c
           SET mart_art = tl.art
          FROM mart369_home_tile tl
         WHERE tl.public_categ_id = c.id
           AND tl.art IS NOT NULL
           AND c.mart_art IS NULL
    """)
    cr.execute("""
        UPDATE mart369_home_tile
           SET image_source = 'category'
         WHERE image_source = 'art'
           AND public_categ_id IS NOT NULL
    """)
