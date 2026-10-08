"""The chat's own lines were filed as internal Notes.

`_mart369_say` posted without a subtype, Odoo files that as a Note, and the
transcript hides Notes - so a ticket's conversation reached nobody. Lines now
carry `mart369_chat`. Here the ones already saved get it: what the customer
said and what the bot said. A staff line is left as it is, because a reply
from the console and a real Log note look the same, and a note must never
reach the customer.
"""


def migrate(cr, version):
    cr.execute("""
        UPDATE mail_message m
           SET mart369_chat = TRUE
          FROM mart369_ticket t
         WHERE m.model = 'mart369.ticket'
           AND m.res_id = t.id
           AND m.message_type = 'comment'
           AND (m.author_id = t.partner_id
                OR m.author_id = (SELECT res_id FROM ir_model_data
                                   WHERE module = 'base' AND name = 'partner_root'))
    """)
