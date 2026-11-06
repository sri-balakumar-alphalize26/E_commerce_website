"""Products the assistant created on its own, kept visible.

A product raised from a WhatsApp enquiry is named from whatever the customer
typed, by way of the AI. "Iphone 15 Screen", "iphone15 screen glass" and
"IPhone Screen 15" are all plausible outcomes of three people asking for the
same thing. That is acceptable - the alternative is losing the sale - but only
because somebody can find them afterwards and tidy them up.

Without the flag they would be indistinguishable from products a human entered,
and the catalog would drift without anyone noticing which half was drifting.
"""

from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    sa_created_from_enquiry = fields.Boolean(
        'Created from a WhatsApp Enquiry', readonly=True, copy=False,
        help="Raised automatically when a customer asked for this and a vendor "
             "priced it. The name came from the customer's own words, so it is "
             "worth checking.",
    )
    sa_enquiry_id = fields.Many2one(
        'sa.group.request', string='Source Enquiry',
        readonly=True, copy=False, ondelete='set null',
        help="The WhatsApp enquiry that caused this product to be created.",
    )
