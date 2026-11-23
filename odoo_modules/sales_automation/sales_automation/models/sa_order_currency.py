# -*- coding: utf-8 -*-
"""Everything of a WhatsApp order is in the order company's currency (owner,
23 Nov 2026). Test 2 sells for NEW COMPANY (AED), but its enquiries picked from
the menu took the currency of the server user's company and its orders the
currency of NEW COMPANY's price list (both OMR)."""
from odoo import api, models


class SaGroupRequestCurrency(models.Model):
    _inherit = 'sa.group.request'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('currency_id') and vals.get('group_id'):
                company = self._company_for(self.env['sa.sales.group'].sudo().browse(vals['group_id']))
                vals['currency_id'] = company.currency_id.id
        return super().create(vals_list)

    def _sa_priced(self, product):
        """`product` as the order's company prices it. The company whose shelf
        it comes from prices it only when both use the same currency."""
        self.ensure_one()
        company = self._company_for(self.group_id)
        shelf = self.finder_company_id
        if shelf and shelf.currency_id == company.currency_id:
            company = shelf
        return product.with_company(company)


class SaleOrderCurrency(models.Model):
    _inherit = 'sale.order'

    def _sa_follows_company(self):
        """An order WhatsApp raised (a website or desk order keeps its price list)."""
        self.ensure_one()
        return bool(self.env.context.get('sa_order_company_id') or self.sa_group_request_id
                    or self.sa_enquiry_ids or (self.origin or '').startswith('WhatsApp Auto-Reply'))

    def _compute_pricelist_id(self):
        """A price list in another currency would turn the whole order into it:
        left out, the order is in its company's currency. Its prices are the
        agreed ones either way."""
        super()._compute_pricelist_id()
        for order in self:
            if order.state == 'draft' and order.pricelist_id \
                    and order.pricelist_id.currency_id != order.company_id.currency_id \
                    and order._sa_follows_company():
                order.pricelist_id = False
