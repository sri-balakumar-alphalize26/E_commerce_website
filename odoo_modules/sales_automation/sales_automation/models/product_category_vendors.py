"""Which vendors to ask for a price, kept on the product category.

The mapping lives here rather than on the vendor because this is the form
somebody already opens when they set a category up, and one entry covers every
product underneath it - add "Electronics" once and every charger, cable and
power bank in it is sourced from those vendors without another click.

Categories are walked upwards when sourcing, so a vendor listed on a parent
answers for all its children. A child that lists its own vendors overrides the
parent, which is how one specialist supplier is used for a single sub-range
without disturbing the rest.

The field belongs to this module: installing it adds the column, uninstalling
removes it, and nothing in the standard product category is altered.
"""

import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class ProductCategory(models.Model):
    _inherit = 'product.category'

    sa_vendor_ids = fields.Many2many(
        'res.partner', 'sa_product_category_vendor_rel',
        'category_id', 'partner_id', string='Vendors',
        domain="[('supplier_rank', '>', 0)]",
        help="Suppliers asked to quote for products in this category. Each one "
             "is messaged privately and their reply becomes a quote, so the "
             "cheapest can be offered to the customer.\n\n"
             "Leave empty to fall back to the vendors already listed on the "
             "product's own Purchase tab.",
    )
    # The same relation `sa.sales.group.product_category_ids` already
    # declares, seen from the side people work from. One table, editable from
    # either form. Every group is listed, whatever its type: a picker that
    # silently hides the group somebody is looking for is how "why is it not
    # in the list?" happens.
    sa_vendor_group_ids = fields.Many2many(
        'sa.sales.group', 'sa_sales_group_product_category_rel',
        'category_id', 'group_id', string='Vendor Groups',
        help="WhatsApp groups asked to quote for products in this category - "
             "one post instead of a message each, for the groups where "
             "several suppliers sit together.\n\n"
             "Attaching a group marks it as a Vendor Group, so replies in it "
             "are read as prices. A group cannot be a customer enquiry group "
             "and a supplier group at the same time.")
    sa_vendor_count = fields.Integer(compute='_compute_sa_vendor_count')

    def _compute_sa_vendor_count(self):
        for rec in self:
            rec.sa_vendor_count = len(rec.sa_vendor_ids)

    @api.model_create_multi
    def create(self, vals_list):
        categories = super().create(vals_list)
        categories._sa_mark_vendor_groups()
        return categories

    def write(self, vals):
        result = super().write(vals)
        if 'sa_vendor_group_ids' in vals:
            self._sa_mark_vendor_groups()
        return result

    def _sa_mark_vendor_groups(self):
        """A group attached to a category is a supplier group, not a shop one.

        Done on write rather than left to the user: the whole point of the
        field is that replies in that group become prices, and that only
        happens for `group_type == 'vendor'` (`_on_group_message` routes on
        it). A group left as `customer` would have its suppliers' prices read
        as customer enquiries instead - answered, classified, and quoted back
        at them.
        """
        groups = self.mapped('sa_vendor_group_ids').filtered(
            lambda g: g.group_type != 'vendor')
        if not groups:
            return
        groups.sudo().write({'group_type': 'vendor'})
        _logger.info("Sales Automation: %s now read as vendor group(s) - "
                     "attached to a category", ', '.join(groups.mapped('name')))

    def _sa_vendor_groups_for_sourcing(self):
        """Groups covering this category, walking up to the parents.

        The same rule as the vendor walk: the nearest category that names
        anyone wins, so a leaf can override its parent without repeating it.
        """
        self.ensure_one()
        category = self
        while category:
            live = category.sa_vendor_group_ids.filtered(
                lambda g: g.enabled and g.group_jid)
            if live:
                return live
            category = category.parent_id
        return self.env['sa.sales.group']

    def _sa_vendors_for_sourcing(self):
        """Vendors covering this category, walking up to the parents.

        The nearest category that names anyone wins. Without the walk, every
        leaf category would have to repeat its parent's supplier list, and the
        first one somebody forgot would silently source from nobody.
        """
        self.ensure_one()
        category = self
        while category:
            if category.sa_vendor_ids:
                return category.sa_vendor_ids
            category = category.parent_id
        return self.env['res.partner']
