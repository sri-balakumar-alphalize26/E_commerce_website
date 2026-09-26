"""WhatsApp sells the storefront's shelf, at the storefront's price.

One shop, two doors. The selling flow offered anything with `sale_ok` at
whatever `wa_retail_price` said; the website sells what is *published*, at
`list_price`. From here the WhatsApp menu shows the published catalogue and
opens every negotiation from the website's price - bargaining still works,
it just starts from the same number the website shows.

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

    @api.model
    def _sa_menu_categories(self, parent=None):
        """Categories worth showing: with *published* products below them."""
        categories = super()._sa_menu_categories(parent=parent)
        Prod = self.env['product.template'].sudo()
        kept = [c for c in categories if Prod.search_count(
            [('categ_id', 'child_of', c.id), ('sale_ok', '=', True),
             ('is_published', '=', True)]) > 0
            or bool(getattr(c, 'sa_vendor_ids', False))]
        if parent is not None:
            return kept
        # Top level: the storefront's own ordering, where a category's
        # products say which shop shelf they sit on. The WhatsApp menu order
        # (sa_menu_sequence) still wins when somebody set it.
        Public = self.env['product.public.category'].sudo()

        def shelf(categ):
            rows = Prod.search(
                [('categ_id', 'child_of', categ.id),
                 ('is_published', '=', True),
                 ('public_categ_ids', '!=', False)], limit=20)
            sequences = [p.sequence for p in rows.mapped('public_categ_ids')]
            return min(sequences) if sequences else 10 ** 6

        return sorted(kept, key=lambda c: (c.sa_menu_sequence, shelf(c),
                                           c.name or ''))

    @api.model
    def _sa_menu_products(self, categ, page=0):
        """Only what the website also sells."""
        Prod = self.env['product.template'].sudo()
        rows = Prod.search(
            [('categ_id', 'child_of', categ.id), ('sale_ok', '=', True),
             ('is_published', '=', True)],
            order='name', offset=page * self.PAGE, limit=self.PAGE + 1)
        return rows[:self.PAGE], len(rows) > self.PAGE

    @api.model
    def _search_products_loose(self, text):
        hits = super()._search_products_loose(text)
        return hits.filtered(
            lambda p: p.is_published or p.sa_created_from_enquiry)[:5]

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
