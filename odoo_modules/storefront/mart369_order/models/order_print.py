"""What the packing slip and the picklist print (report/order_print_report.xml).

Both are printed from the Orders screens for the orders ticked there. The
picklist is every item across those orders, counted once per product and
grouped by the shop's category, so one person walks the store once instead of
once per order. The store has no shelf numbers yet, so the category is the
nearest thing to an aisle.
"""

from odoo import models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _mart369_print_lines(self):
        """The lines that go in the bag: products, not notes or sections,
        and not a line taken out because it ran out."""
        self.ensure_one()
        return self.order_line.filtered(
            lambda l: not l.display_type and l.product_id and l.product_uom_qty > 0
            and not l.is_delivery)

    def _mart369_print_payment(self):
        """('collect', amount) for cash on delivery, else ('paid', amount)."""
        self.ensure_one()
        if (self.mart369_method or '') == 'cod':
            return 'collect', self.amount_total
        return 'paid', self.amount_total

    def _mart369_print_address(self):
        """The delivery address as the lines a rider reads, top to bottom."""
        self.ensure_one()
        a = self.partner_shipping_id
        town = ' '.join(p for p in (a.city, a.zip) if p)
        lines = [a.street, a.street2,
                 ('Near %s' % a.mart369_landmark) if 'mart369_landmark' in a._fields and a.mart369_landmark else '',
                 ', '.join(p for p in (town, a.state_id.name) if p)]
        return [line for line in lines if line]

    def _mart369_picklist(self):
        """[{category, items: [{name, qty, refs}]}], categories A-Z, products
        A-Z inside each."""
        found = {}
        for order in self:
            for line in order._mart369_print_lines():
                product = line.product_id
                categ = product.product_tmpl_id.public_categ_ids[:1]
                group = found.setdefault(categ.display_name or 'Other', {})
                item = group.setdefault(product.id, {
                    'name': product.display_name, 'qty': 0.0, 'refs': []})
                item['qty'] += line.product_uom_qty
                if order.mart369_ref not in item['refs']:
                    item['refs'].append(order.mart369_ref)
        return [
            {'category': name,
             'items': sorted(items.values(), key=lambda i: i['name'].lower())}
            for name, items in sorted(found.items(), key=lambda kv: kv[0].lower())
        ]
