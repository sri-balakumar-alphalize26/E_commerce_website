"""WhatsApp sells the storefront's shelf - its tree, its price, its stock.

One shop, two doors. The selling flow used to walk Odoo's *internal* product
categories and offer anything with `sale_ok` at whatever `wa_retail_price`
said. From here the NEW ORDER menu walks the **website's own category tree**
(`product.public.category` - the same names, nesting and order the storefront
navigation shows), lists only *published* products, and opens every
negotiation from the website's `list_price`. Bargaining still works; it just
starts from the same number the website shows.

The internal category tree keeps the one job that is genuinely its own:
saying which vendors to ask when something is out of stock. That routing
reads `product.categ_id` after a product is picked and is untouched here.

A product a vendor quoted for an out-of-stock enquiry is still created - that
is the whole point of the sourcing flow - but it stays **unpublished** and is
labelled, so it turns up on the console's product screen for somebody to
price and publish properly rather than leaking onto the website at a
vendor's price plus margin.
"""

import json
import logging

from odoo import _, api, models

from odoo.addons.sales_automation_confirm.models.sa_menu_categories import NOT_LISTED

_logger = logging.getLogger(__name__)


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
        """The storefront's categories, exactly as the website orders them -
        and only the ones with something published to sell underneath."""
        Public = self.env['product.public.category'].sudo()
        Prod = self.env['product.template'].sudo()
        rows = Public.search(
            [('parent_id', '=', parent.id if parent else False)],
            order='sequence, name')
        sellable = self._mart369_sellable_domain(self._mart369_stock_company())
        return [c for c in rows if Prod.search_count(
            [('public_categ_ids', 'child_of', c.id),
             ('sale_ok', '=', True), ('is_published', '=', True)]
            + sellable) > 0]

    @api.model
    def _sa_menu_products(self, categ, page=0):
        """Only what the website also sells, page by page."""
        Prod = self.env['product.template'].sudo()
        rows = Prod.search(
            [('public_categ_ids', 'child_of', categ.id),
             ('sale_ok', '=', True), ('is_published', '=', True)]
            + self._mart369_sellable_domain(self._mart369_stock_company()),
            order='name', offset=page * self.PAGE, limit=self.PAGE + 1)
        return rows[:self.PAGE], len(rows) > self.PAGE

    def _sa_menu_show(self, level):
        """The catalogue levels, rebuilt on the website's tree.

        Level names keep the confirm module's shape - `categ`, `categ:<id>`,
        `prod:<id>[:page]` - but the ids inside them are the storefront's
        `product.public.category`. Every other level (main, orders, more...)
        belongs to the parent and passes straight through.
        """
        self.ensure_one()
        if not (level or '').startswith(('categ', 'prod:')):
            return super()._sa_menu_show(level)

        Public = self.env['product.public.category'].sudo()
        Prod = self.env['product.template'].sudo()
        opts, used = [], set()
        parent_level = 'main'

        if level == 'categ':
            body = _("\U0001F195 *New order* - what are you looking for? "
                     "Tap a category:")
            for c in self._sa_menu_categories()[:8]:
                opts.append((self._sa_menu_clean(c.name, used),
                             {'kind': 'menu', 'level': 'categ:%d' % c.id}))
        else:
            bits = level.split(':')
            cid = int(bits[1] or 0)
            page = int(bits[2]) if len(bits) > 2 and bits[2].isdigit() else 0
            categ = Public.browse(cid).exists()
            if not categ:
                # A stale poll from before a category was renamed or removed.
                return super()._sa_menu_show('main')
            parent_level = (('categ:%d' % categ.parent_id.id)
                            if categ.parent_id and level.startswith('categ:')
                            else 'categ')
            if level.startswith('categ:'):
                subs = self._sa_menu_categories(parent=categ)
                if subs:
                    body = _("*%s* - tap a type:") % categ.name
                    for c in subs[:6]:
                        opts.append((self._sa_menu_clean(c.name, used),
                                     {'kind': 'menu', 'level': 'categ:%d' % c.id}))
                    direct = Prod.search_count(
                        [('public_categ_ids', 'in', categ.id),
                         ('sale_ok', '=', True), ('is_published', '=', True)]
                        + self._mart369_sellable_domain(self._mart369_stock_company()))
                    if direct:
                        opts.append((self._sa_menu_clean(
                            _("All %s products") % categ.name, used),
                            {'kind': 'menu', 'level': 'prod:%d' % categ.id}))
                else:
                    level = 'prod:%d' % categ.id
            if level.startswith('prod:'):
                body = _("*%s* - tap the product you want:") % categ.name
                products, more = self._sa_menu_products(categ, page)
                if page and not products:
                    return self._sa_menu_show('prod:%d' % categ.id)
                for p in products:
                    opts.append((self._sa_menu_clean(p.name, used),
                                 {'kind': 'prodpick', 'target': p.id}))
                if more:
                    opts.append((_("➡️ MORE"),
                                 {'kind': 'menu',
                                  'level': 'prod:%d:%d' % (categ.id, page + 1)}))
                parent_level = (('prod:%d:%d' % (categ.id, page - 1)) if page
                                else (('categ:%d' % categ.parent_id.id)
                                      if categ.parent_id else 'categ'))

        opts.append((NOT_LISTED, {'kind': 'new'}))
        if level != 'categ':
            # The top level's "back" is the main menu itself.
            opts.append((self.MENU_BACK, {'kind': 'menu', 'level': parent_level}))
        opts.append((self.MENU_MAIN, {'kind': 'menu', 'level': 'main'}))
        menu = {}
        for label, item in opts[:10]:
            item = dict(item)
            item.setdefault('req', self.id)
            item['parent'] = level
            menu[label] = item
        self.sa_menu_json = json.dumps(menu)
        self._ask(body, [{'id': 'sa_menu_%d' % i, 'title': label}
                         for i, label in enumerate(menu)])
        return True

    # ---------------------------------------------------- search and price

    @api.model
    def _search_products_loose(self, text):
        hits = super()._search_products_loose(text)
        hits = hits.filtered(lambda p: p.is_published or p.sa_created_from_enquiry)
        # Never offer what the shop will not sell (stock_rule.py); a vendor-
        # quoted product is sourced by definition and always passes.
        sellable = hits.filtered_domain(
            self._mart369_sellable_domain(self._mart369_stock_company()))
        return hits.filtered(lambda p: p in sellable or p.sa_created_from_enquiry)[:5]

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
