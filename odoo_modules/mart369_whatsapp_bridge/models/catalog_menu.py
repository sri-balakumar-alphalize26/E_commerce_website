"""WhatsApp sells the storefront's shelf - its products, its price, its stock.

One shop, two doors, one category tree. The NEW ORDER menu is the WhatsApp
package's own: its **Product Categories** in *WhatsApp menu order*, Hide
skipped. The website draws the same categories - each Product Category has a
website twin (mart369_catalog, product_category.py; category_mirror.py here
keeps the menu order and Hide in step) - so both doors list the same names
in the same order.

What the bridge still changes: the menu lists only *published* products,
and every negotiation opens from the website's `list_price`. Bargaining
still works; it just starts from the same number the website shows.

A product a vendor quoted for an out-of-stock enquiry is still created - that
is the whole point of the sourcing flow - but it stays **unpublished** and is
labelled, so it turns up on the console's product screen for somebody to
price and publish properly rather than leaking onto the website at a
vendor's price plus margin.
"""

from odoo import api, models


class SaGroupRequestCatalog(models.Model):
    _inherit = 'sa.group.request'

    # A product the sourcing flow itself created is still offerable on
    # WhatsApp before anyone publishes it - otherwise every re-ask would
    # create a duplicate.
    _MART369_MENU_DOMAIN = ['|', ('is_published', '=', True),
                            ('sa_created_from_enquiry', '=', True)]

    # ------------------------------------------------------------- the tree

    @api.model
    def _sa_menu_categories(self, parent=None):
        """The package's own list (menu order, Hide skipped), less any
        category with nothing published under it and no vendors to ask."""
        Prod = self.env['product.template'].sudo()
        sellable = self._sa_unsellable_domain()
        return [c for c in super()._sa_menu_categories(parent=parent)
                if getattr(c, 'sa_vendor_ids', False) or Prod.search_count(
                    [('categ_id', 'child_of', c.id), ('sale_ok', '=', True),
                     ('is_published', '=', True)] + sellable, limit=1)]

    @api.model
    def _sa_menu_products(self, categ, page=0):
        """Only what the website also sells, page by page."""
        Prod = self.env['product.template'].sudo()
        rows = Prod.search(
            [('categ_id', 'child_of', categ.id),
             ('sale_ok', '=', True), ('is_published', '=', True)]
            + self._sa_unsellable_domain(),
            order='name', offset=page * self.PAGE, limit=self.PAGE + 1)
        return rows[:self.PAGE], len(rows) > self.PAGE

    # ---------------------------------------------------- search and price

    @api.model
    def _search_products_loose(self, text):
        # The core already leaves out what may not be sold short with none free.
        hits = super()._search_products_loose(text)
        return hits.filtered(lambda p: p.is_published or p.sa_created_from_enquiry)[:5]

    @api.model
    def _sa_catalog_vocabulary(self):
        """Spelling is corrected toward words the shop actually sells."""
        found = set()
        for name in self.env['product.template'].sudo().search_read(
                self._MART369_MENU_DOMAIN + [('sale_ok', '=', True)],
                ['name'], limit=2000):
            for word in self._sa_words(name.get('name') or ''):
                if len(word) >= 4:
                    found.add(word)
        return found or super()._sa_catalog_vocabulary()

    @api.model
    def _catalog_price(self, product, is_existing_contact):
        """A published product opens at the website's price for everyone.

        `wa_retail_price` stays what it is for the unpublished rest - the
        sourcing flow's own creations price themselves from vendor quotes.
        """
        if product.is_published:
            return product.list_price
        return super()._catalog_price(product, is_existing_contact)

    def _create_product_from_enquiry(self):
        product = super()._create_product_from_enquiry()
        if product and product.sa_created_from_enquiry:
            product.sudo().write({
                'is_published': False,
                'description_sale': (product.description_sale or '') or
                    'From a WhatsApp vendor quote - price and publish it '
                    'before it goes on the website.',
            })
        return product
