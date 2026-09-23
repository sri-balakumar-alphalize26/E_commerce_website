from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError


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

    mart_page_hidden = fields.Char(
        string='Hidden on this product', compute='_compute_mart_page_hidden',
        help='Which product columns the page will not print for this product. '
             'The form reads it to stop asking for them.')

    @api.depends('mart_page_override_ids.state', 'public_categ_ids')
    def _compute_mart_page_hidden(self):
        """The columns this product's page will not print, comma-delimited.

        So the Odoo form can stop asking for them. Until this existed, every
        product was asked for every field - a bag of rice wanted a Material and
        three Item sizes - and somebody typed values into boxes the page had
        been told not to print.

        Not a second opinion. `_visible_for` is the same ladder the shopper's
        own page runs through - the section eye first as a master switch, then
        this product's own choice, then the shop-wide default - so the form and
        the page cannot come to different conclusions. Re-deriving it here is
        how a box gets hidden while its value is on screen in the app.

        Delimited with commas at both ends, because the view tests membership
        with `',mart_item_width,' in mart_page_hidden` and a bare `in` would
        match one column name inside a longer one.

        A product being created has no category to resolve against, so nothing
        is hidden and every box is offered. Hiding them on a blank form would
        mean somebody saving a product having never been shown the box it
        needed.
        """
        Field = self.env['mart369.product.field'].sudo()
        columns = Field.search([('odoo_field', '!=', False)])

        for rec in self:
            # A record being created has a NewId, not an int. Tested that
            # way rather than against models.NewId, which Odoo 19 moved.
            if not isinstance(rec.id, int) or not rec.public_categ_ids:
                rec.mart_page_hidden = ''
                continue
            overrides = {
                (o.product_tmpl_id.id, o.field_id.id): o
                for o in self.env['mart369.product.override'].sudo().search(
                    [('product_tmpl_id', '=', rec.id)])
            }
            # A column is only hidden when every page row reading it is
            # hidden. `mart_unit_text` feeds two of them - the size tag on
            # the photo and Net quantity in the specifications - and taking
            # the box away because one of the two is off would lose the
            # value the other still prints.
            shown, off = set(), set()
            for field in columns:
                (shown if field._visible_for(rec, overrides) else off).add(
                    field.odoo_field)
            hidden = off - shown
            rec.mart_page_hidden = ',%s,' % ','.join(sorted(hidden)) if hidden else ''

    def action_mart_reset_page(self):
        """Put every field on this product back to following the defaults."""
        self.mart_page_override_ids.unlink()
        return True

    # ------------------------------------------------- the Products desk

    # Which columns the Products desk may write, in the order it draws them.
    # An allowlist rather than "write whatever arrived": this method is
    # reachable by anyone who can reach the desk, and `product.template` has
    # columns - cost, taxes, routes, `is_published` - that have no business
    # being set from a screen that does not show them.
    #
    # Labels are not repeated here. They come from the field definitions, so
    # renaming a field renames its box and the two cannot drift.
    MART_DESK_GROUPS = [
        ('Basics', ['name', 'default_code', 'public_categ_ids',
                    'list_price', 'compare_list_price']),
        ('Wording on the card', ['mart_unit_text', 'mart_per_unit',
                                 'mart_note', 'mart_home_tag']),
        ('What the page shows', ['mart_features', 'mart_in_the_box',
                                 'mart_material', 'mart_item_height',
                                 'mart_item_length', 'mart_item_width',
                                 'weight', 'description_ecommerce']),
        ('Stock and delivery', ['mart_low_stock_at', 'mart_delivery_text']),
    ]

    # Asked for on every product, whatever the product page is told to print.
    # A product with no name or no price is not a product, and
    # `public_categ_ids` decides which of the four layers even apply to it -
    # hiding that box would make the rest of the form behave unpredictably
    # with nothing on screen to explain why.
    MART_DESK_ALWAYS = ('name', 'list_price', 'public_categ_ids')

    # The few places Odoo's own word for a column is not the shop's word for
    # it. Deliberately short: every other label comes from the field itself,
    # and each entry here is a second name somebody has to keep in step.
    #
    # These are the same relabels the Odoo product form makes, so a shopkeeper
    # reads "Article ID" on both screens and on the product page rather than
    # meeting "Internal Reference" on one of the three.
    MART_DESK_LABELS = {
        'default_code': 'Article ID',
        'list_price': 'Price',
        'compare_list_price': 'MRP',
        'public_categ_ids': 'Categories',
        'weight': 'Net weight',
        'description_ecommerce': 'Description',
    }

    MART_DESK_EDITOR_GROUP = 'website.group_website_designer'

    def _mart369_desk_check(self):
        """Refused, not filtered - the same rule the admin routes use.

        Deciding what a product page shows is already
        `website.group_website_designer` in this module's access rules, so
        that is who may fill one in. No new role invented for the same
        question. `mart369_roles` grants this group to its Manager, so the
        two product screens agree on who may edit.

        Nothing below sudo's. This runs as the person signed in, so Odoo's own
        rules on `product.template` apply on their own rather than being
        re-implemented here badly - somebody who may reach this screen but may
        not write products gets Odoo's refusal, which is the true answer.
        """
        if not self.env.user.has_group(self.MART_DESK_EDITOR_GROUP):
            raise AccessError(_(
                "You do not have permission to change products. Ask an "
                "administrator for the website designer role."))

    def _mart369_desk_widget(self, field):
        if field.type in ('float', 'monetary'):
            return 'number'
        if field.type == 'integer':
            return 'integer'
        if field.type == 'html':
            return 'html'
        if field.type == 'text':
            return 'text'
        if field.type == 'many2many':
            return 'categories'
        return 'char'

    @api.model
    def mart369_desk_form(self, product_id=None):
        """The boxes the desk should draw, and what is in them.

        Built from the live field definitions rather than a second list kept
        in JavaScript, so a renamed or retyped column reaches the screen
        without anybody remembering to change it there too.

        Boxes the product page has been told not to print are left out, using
        the same `mart_page_hidden` the Odoo form reads - so the desk, the
        form and the shopper's page agree. A product being created has no
        category to resolve against, so nothing is hidden and everything is
        offered: hiding boxes on a blank screen loses values nobody was given
        the chance to enter.
        """
        self._mart369_desk_check()

        product = self.browse(int(product_id)).exists() if product_id else self.browse()
        hidden = product.mart_page_hidden or '' if product else ''

        groups, values = [], {}
        for title, names in self.MART_DESK_GROUPS:
            boxes = []
            for name in names:
                field = self._fields.get(name)
                if not field:
                    continue  # the module that supplies it is not installed
                if name not in self.MART_DESK_ALWAYS and ',%s,' % name in hidden:
                    continue
                boxes.append({
                    'name': name,
                    'label': self.MART_DESK_LABELS.get(name, field.string),
                    'help': field.help or '',
                    'widget': self._mart369_desk_widget(field),
                    'required': name == 'name',
                })
                if product:
                    raw = product[name]
                    if field.type == 'many2many':
                        values[name] = raw.ids
                    elif field.type in ('float', 'monetary', 'integer'):
                        values[name] = raw or 0
                    else:
                        values[name] = raw or ''
            if boxes:
                groups.append({'title': title, 'boxes': boxes})

        photos = []
        if product and 'product_template_image_ids' in self._fields:
            photos = [{
                'id': image.id,
                'name': image.name or '',
                'url': '/web/image/product.image/%s/image_256' % image.id,
            } for image in product.product_template_image_ids]

        return {
            'id': product.id or None,
            'groups': groups,
            'values': values,
            'photo': ('/web/image/product.template/%s/image_256?unique=%s'
                      % (product.id, product.write_date)
                      if product and product.image_1920 else ''),
            'photos': photos,
            'categories': [
                {'id': c.id, 'name': c.display_name}
                # The model's own order (sequence, then name). There is no
                # `complete_name` on this model in 19, though `display_name`
                # still reads "Parent / Child", which is what the label wants.
                for c in self.env['product.public.category'].search([])
            ],
        }

    @api.model
    def mart369_desk_save(self, values, product_id=None, photos=None):
        """Create or update a product from the desk. Returns its id."""
        self._mart369_desk_check()

        allowed = {n for _title, names in self.MART_DESK_GROUPS for n in names}
        vals = {}
        for name, value in (values or {}).items():
            if name not in allowed or name not in self._fields:
                continue  # silently dropped: see MART_DESK_GROUPS
            field = self._fields[name]
            if field.type == 'many2many':
                vals[name] = [(6, 0, [int(v) for v in (value or [])])]
            elif field.type in ('float', 'monetary'):
                vals[name] = float(value or 0)
            elif field.type == 'integer':
                vals[name] = int(value or 0)
            else:
                vals[name] = value if value not in (None, False) else ''

        if not product_id and not (vals.get('name') or '').strip():
            raise UserError(_("A product needs a name."))

        if 'image_1920' in (values or {}):
            # '' means "take the photograph away", which is not the same as
            # not mentioning it at all.
            vals['image_1920'] = values['image_1920'] or False

        if product_id:
            product = self.browse(int(product_id)).exists()
            if not product:
                raise UserError(_("That product no longer exists."))
            product.write(vals)
        else:
            # The desk's list only shows published products, so one created
            # here and left unpublished would vanish the moment it was saved.
            # Published is what the person plainly meant.
            vals.setdefault('is_published', True)
            product = self.create(vals)

        self._mart369_desk_photos(product, photos or {})
        return product.id

    def _mart369_desk_photos(self, product, photos):
        """The gallery: rows on `product.image`, added and removed one at a time.

        Kept out of the write above because they are separate records, and
        because replacing the whole set on every save would churn ids - and so
        image URLs - for photographs nobody touched.
        """
        if 'product_template_image_ids' not in self._fields:
            return  # website_sale is not installed; there is no gallery
        Image = self.env['product.image']

        remove = [int(i) for i in (photos.get('remove') or [])]
        if remove:
            product.product_template_image_ids.filtered(
                lambda r: r.id in remove).unlink()

        for added in (photos.get('add') or []):
            data = added.get('data') if isinstance(added, dict) else added
            if not data:
                continue
            name = added.get('name') if isinstance(added, dict) else ''
            Image.create({
                'name': name or product.name or 'Photograph',
                'image_1920': data,
                'product_tmpl_id': product.id,
            })

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
                # Added for the products desk's list view, which has columns to
                # fill where the picker's tiles did not. Additive on purpose:
                # the builder's own picker reads what it always read.
                'price': p.list_price,
                'categories': p.public_categ_ids.mapped('name'),
            } for p in found],
            'total': total,
            'limit': limit,
        }
