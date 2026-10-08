"""The storefront lists a variant's specs the way the WhatsApp page does.

sales_automation_confirm gives every variant a *Variant specs* table
(`_sa_spec_rows()`). The storefront's cards (mart369.serializable) only know
plain Odoo - the variant's attribute values - and this is where they learn the
senior's table, so the website and the chat list the same rows.

The pictures used to come from here too, from the senior's *Variant images* tab
(`sa_variant_picture_ids`). That tab is being retired: the storefront now reads
Odoo's own Extra Variant Media (mart369 `_mart369_variant_media`).
"""

from odoo import api, models


class Mart369SerializableVariantMedia(models.AbstractModel):
    _inherit = 'mart369.serializable'

    @api.model
    def _mart369_variant_spec_rows(self, variant):
        """The Variant specs table - the exact rows the WhatsApp page lists:
        attribute lines by default, edited lines win, extra lines appended."""
        return variant._sa_spec_rows()
