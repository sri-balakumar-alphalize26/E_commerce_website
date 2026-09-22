from odoo import api, fields, models


class ProductTemplate(models.Model):
    """The handful of product-page values that live on the product itself.

    Everything repeated across a category - sold by, manufacturer, return
    policy, shelf life - is set once in 369 Mart > Product Page instead.
    """

    _inherit = 'product.template'

    mart_features = fields.Text(
        string='Key features',
        help='One per line. Shown as the ticked bullet list on the product '
             'page. Leave empty to use the category or shop default.')
    mart_in_the_box = fields.Char(
        string='In the box',
        help="e.g. Product, cable, user manual.")
    mart_material = fields.Char(
        string='Material',
        help='e.g. Stainless steel, Cotton.')
    mart_item_height = fields.Char(string='Item height', help='e.g. 12 cm')
    mart_item_length = fields.Char(string='Item length', help='e.g. 8 cm')
    mart_item_width = fields.Char(string='Item width', help='e.g. 6 cm')

    mart_page_override_ids = fields.One2many(
        'mart369.product.override', 'product_tmpl_id',
        string='Product page settings')
    mart_page_differs = fields.Integer(
        string='Differs from default', compute='_compute_mart_page_differs',
        help='How many product-page fields this product was deliberately set '
             'to show or hide, against the shop-wide default.')

    def _compute_mart_page_differs(self):
        Override = self.env['mart369.product.override']
        counts = dict(Override._read_group(
            [('product_tmpl_id', 'in', self.ids), ('state', '!=', 'follow')],
            groupby=['product_tmpl_id'], aggregates=['__count']))
        for rec in self:
            rec.mart_page_differs = counts.get(rec, 0)

    def action_mart_reset_page(self):
        """Put every field on this product back to following the defaults."""
        self.mart_page_override_ids.unlink()
        return True

    # ------------------------------------------------------------ the picker

    @api.model
    def mart369_page_picker(self, categ_id=None, q='', only_edited=False,
                            limit=300):
        """Everything the "one product" picker draws, in one call.

        The editors used to offer a search box and nothing else, so you had to
        know a product's name before you could edit its page. This answers the
        other question - "what is in the shop?" - with the shop's own
        categories, so somebody can work through a category instead of
        guessing at spellings.

        Only published products: this edits the page a shopper sees, and an
        unpublished product does not have one.

        Deliberately built on plain `product.public.category` fields rather
        than mart369_catalog's `_mart369_product_domain()` and `mart_in_app`.
        That module is not in this one's `depends`, every 369 Mart module is
        meant to install on its own, and taking a dependency to reuse a
        four-line domain is the wrong trade. The cost is that the rail lists
        categories the storefront's nav hides - which is right here, because
        this groups products so you can find one rather than mirroring the
        app's navigation.
        """
        Category = self.env['product.public.category']
        published = [('is_published', '=', True)]

        # ---- the tree, and how many products sit under each branch.
        #
        # One read of every product's categories, then the counts roll up
        # through `parent_path`. Counting per category would be one query
        # each, and - worse - a parent would read 0 while clicking it showed
        # dozens: `child_of` matches descendants, so the count has to too.
        categories = Category.search([], order='sequence, name')
        by_id = {c.id: c for c in categories}
        counts = dict.fromkeys(by_id, 0)
        uncategorised = 0

        for row in self.search_read(published, ['public_categ_ids']):
            ids = row['public_categ_ids']
            if not ids:
                uncategorised += 1
                continue
            # A product filed under both "Laptops" and "Computers" must not
            # count twice against "Computers", so collect the ancestry as a
            # set before adding anything.
            branch = set()
            for cid in ids:
                categ = by_id.get(cid)
                if not categ:
                    continue
                for part in (categ.parent_path or '').strip('/').split('/'):
                    if part:
                        branch.add(int(part))
            for cid in branch:
                if cid in counts:
                    counts[cid] += 1

        # ---- the products themselves
        domain = list(published)
        if categ_id == 0:
            # The bucket for products filed nowhere. Without it the three
            # products in this shop with no category are unreachable.
            domain.append(('public_categ_ids', '=', False))
        elif categ_id:
            domain.append(('public_categ_ids', 'child_of', int(categ_id)))
        term = (q or '').strip()
        if term:
            domain += ['|', ('name', 'ilike', term),
                       ('default_code', 'ilike', term)]
        if only_edited:
            domain.append(('mart_page_override_ids', '!=', False))

        total = self.search_count(domain)
        found = self.search(domain, limit=limit, order='name')
        # The compute behind this is a single batched _read_group. Reading it
        # off the recordset keeps it that way; touching it per product inside
        # the loop below would be one query each.
        found.mapped('mart_page_differs')

        return {
            # The unfiltered total, for the rail's 'All products' row. It
            # cannot be added up from the branches: a product filed under two
            # top-level categories would be counted twice.
            'all_count': self.search_count(published),
            'categories': [{
                'id': c.id,
                'name': c.name,
                'parent_id': c.parent_id.id or None,
                'count': counts.get(c.id, 0),
            } for c in categories],
            'uncategorised': uncategorised,
            'products': [{
                'id': p.id,
                'name': p.display_name,
                'code': p.default_code or '',
                # A plain relative URL. serializers.py's absolute _api_base()
                # exists to give the phone app a host it can reach, and is the
                # wrong tool for a screen drawn inside the backend.
                'image': '/web/image/product.template/%s/image_128' % p.id,
                'differs': p.mart_page_differs,
            } for p in found],
            'total': total,
            'limit': limit,
        }
