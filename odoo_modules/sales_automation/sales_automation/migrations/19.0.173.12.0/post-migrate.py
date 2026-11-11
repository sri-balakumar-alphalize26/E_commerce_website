"""Orders placed from a group's YES had no WhatsApp Group: only the enquiry
pointed at the order. `sa_group_id` now reads either direction; fill it in
for the orders already there (the newest enquiry wins, as in the compute)."""


def migrate(cr, version):
    cr.execute("""
        UPDATE sale_order so
           SET sa_group_id = r.group_id
          FROM (SELECT DISTINCT ON (order_id) order_id, group_id
                  FROM sa_group_request
                 WHERE order_id IS NOT NULL
                 ORDER BY order_id, id DESC) r
         WHERE r.order_id = so.id
           AND so.sa_group_request_id IS NULL
           AND so.sa_group_id IS DISTINCT FROM r.group_id
    """)
