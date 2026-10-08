"""Which line a reply answers.

A team reply in the chat carries the customer's question above it, the way
WhatsApp quotes a message, and tapping that takes the customer back up to it.

Not `parent_id`: a ticket is a flat thread, so Odoo links every message posted
without a parent to the thread's first one (`_message_compute_parent_id`), and
"the parent" ends up meaning "the ticket" rather than "the question".
"""

from odoo import fields, models


class MailMessage(models.Model):
    _inherit = 'mail.message'

    # Odoo files a message posted without a subtype as an internal Note, and
    # the transcript hides Notes - they are staff writing to each other. Every
    # line the chat itself posts was a Note, so the customer saw none of them,
    # the team's replies included. This says "a line of the conversation".
    mart369_chat = fields.Boolean(
        string='Said in the chat', copy=False,
        help="A line of a 369 Mart support conversation, shown to the customer "
             "although Odoo filed it as a note.")
    mart369_reply_to_id = fields.Many2one(
        'mail.message', string='Answers', ondelete='set null', copy=False,
        help="The customer's line this one answers, on a 369 Mart support "
             "ticket. A customer line nobody has answered yet is what the next "
             "team reply is tagged to.")
