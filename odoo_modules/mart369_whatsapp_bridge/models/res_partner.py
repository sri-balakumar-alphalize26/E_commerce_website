"""The customer's own contact address follows the storefront's default.

The website keeps every address as a child of the customer and never writes
the customer record itself; the WhatsApp stack reads the customer record
(street, postcode, country) for its pincode rules, its "current address"
line and its MY DETAILS fallback. Left apart, a customer who tapped a
different saved address was still judged by the old one.

So whenever the default changes - from either door, through the storefront's
own `_mart369_set_default` - or the default is edited in place, its lines are
copied onto the customer. Only the lines: the customer's name and phone are
the identity the bridge matches a WhatsApp number on, and the book keeps
every address, so nothing is lost.
"""

from odoo import models

# The lines a parcel is addressed with. Not name / phone / landmark: those
# belong to the address, and the customer's own name and phone are the
# account, not the doorstep.
SYNCED_FIELDS = ('street', 'street2', 'city', 'zip', 'state_id', 'country_id')


class ResPartner(models.Model):
    _inherit = 'res.partner'

    def _mart369_sync_contact_address(self):
        """Copy this default address's lines onto its customer."""
        for address in self:
            customer = address.parent_id
            if not customer or customer.parent_id or customer.type != 'contact':
                continue
            values = {}
            for field in SYNCED_FIELDS:
                value = address[field]
                if not value:
                    continue
                value = value.id if hasattr(value, 'id') else value
                current = customer[field]
                current = current.id if hasattr(current, 'id') else current
                if current != value:
                    values[field] = value
            if values:
                customer.sudo().with_context(mart369_contact_sync=True).write(values)

    def _mart369_set_default(self):
        super()._mart369_set_default()
        self._mart369_sync_contact_address()

    def write(self, vals):
        res = super().write(vals)
        if (not self.env.context.get('mart369_contact_sync')
                and any(f in vals for f in SYNCED_FIELDS)):
            # An edit of the default in place (the storefront's revise path,
            # the desks' edit forms) must reach the customer too.
            self.filtered('mart369_default')._mart369_sync_contact_address()
        return res
