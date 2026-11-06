"""Free /odoo/mart-product before the data files claim it.

The page editor takes over the front door and the phone builder moves to
/odoo/mart-product-advanced. Both changes are in the data files, but the write
that moves the builder is not flushed before the create that adds the editor
action - so the create hits `ir_act_client_path_unique` on a path the builder
still holds, and the whole upgrade rolls back.

Doing it here, in SQL, before any of that runs, means there is never a moment
when two actions want the same path. The home page's builder made exactly this
move in mart369_home/migrations/19.0.1.3.0.
"""


def migrate(cr, version):
    cr.execute("""
        UPDATE ir_act_client
           SET path = 'mart-product-advanced'
         WHERE path = 'mart-product'
    """)
