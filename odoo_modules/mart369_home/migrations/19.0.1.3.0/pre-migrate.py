"""Free /odoo/mart-home before the data files claim it.

The pages list takes over the front door and the phone builder moves to
/odoo/mart-home-advanced. Both changes are in the data files, but the write
that moves the builder is not flushed before the create that adds the pages
action - so the create hits `ir_act_client_path_unique` on a path the builder
still holds, and the whole upgrade rolls back.

Doing it here, in SQL, before any of that runs, means there is never a moment
when two actions want the same path.
"""


def migrate(cr, version):
    cr.execute("""
        UPDATE ir_act_client
           SET path = 'mart-home-advanced'
         WHERE path = 'mart-home'
    """)
