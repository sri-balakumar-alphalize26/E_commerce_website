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
        # `mart_brand` is mart369_catalog's; skipped when it is not installed.
        ('Basics', ['name', 'mart_brand', 'default_code', 'public_categ_ids',
                    'list_price', 'compare_list_price', 'standard_price']),
        ('Wording on the card', ['mart_unit_text', 'mart_per_unit',
                                 'mart_note', 'mart_home_tag']),
        ('What the page shows', ['mart_features', 'mart_in_the_box',
                                 'mart_material', 'mart_item_height',
                                 'mart_item_length', 'mart_item_width',
                                 'weight', 'description_ecommerce']),
        ('Stock and delivery', ['mart_low_stock_at', 'mart_delivery_text']),
        # Odoo's own product fields, so a product can be set up completely from
        # the desk. `mart_on_hand` is not a column: stock is counted, not
        # stored, and mart369_catalog books it (see _mart369_desk_on_hand_box).
        ('Stock, tax and company', ['type', 'is_storable', 'mart_on_hand',
                                    'barcode', 'categ_id', 'taxes_id',
                                    'supplier_taxes_id', 'company_id']),
    ]

    # Groups drawn on the desk only. Inside Odoo's own product form these
    # fields are already on the page, just above the editor.
    MART_DESK_DESK_ONLY = ('Stock, tax and company',)

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
        'standard_price': 'Cost',
        'public_categ_ids': 'Categories',
        'weight': 'Net weight',
        'description_ecommerce': 'Description',
    }

    # Boxes drawn as more than one plain text box. Storage does not change:
    # each is still one text column the app prints as-is, so the desk splits
    # it on load ("250 g" -> 250, g) and joins it back before saving. The
    # lists live here, once, so a new unit is a one-line change.
    _WEIGHTS = ['kg', 'g', 'mg', 'L', 'ml', 'pcs', 'pack', 'dozen']
    _LENGTHS = ['mm', 'cm', 'm', 'in', 'ft']
    MART_DESK_KINDS = {
        'mart_unit_text': {'kind': 'measure', 'units': _WEIGHTS},
        'mart_per_unit': {'kind': 'per_unit', 'units': _WEIGHTS},
        'mart_home_tag': {'kind': 'choice', 'options': [
            'New', 'Bestseller', 'Sale', 'Limited', 'Old stock', 'Organic',
            'Imported']},
        'mart_features': {'kind': 'points'},
        # The same one-box-per-item entry, kept as the comma list the page
        # has always printed: "Product, cable, user manual".
        'mart_in_the_box': {'kind': 'points', 'sep': ', '},
        'mart_material': {'kind': 'choice', 'options': [
            'Plastic', 'Metal', 'Stainless steel', 'Aluminium', 'Glass', 'Wood',
            'Cotton', 'Leather', 'Rubber', 'Silicone', 'Paper']},
        'mart_item_height': {'kind': 'measure', 'units': _LENGTHS},
        'mart_item_length': {'kind': 'measure', 'units': _LENGTHS},
        'mart_item_width': {'kind': 'measure', 'units': _LENGTHS},
        # A range ("3-5 days") is how delivery times are written.
        'mart_delivery_text': {'kind': 'measure', 'range': True,
                               'units': ['days', 'weeks', 'months']},
        # A number column, not text: Odoo keeps weight in kg, so a value typed
        # in g is converted before it is saved.
        'weight': {'kind': 'measure', 'numeric': True, 'units': ['kg', 'g']},
        # EAN-13, UPC-A, EAN-8 and GTIN-14 are all digits - kept as text so a
        # leading zero survives.
        'barcode': {'kind': 'digits', 'max': 14},
    }

    # Help in the shop's words where Odoo's own help is about its website.
    MART_DESK_HELP = {
        'compare_list_price': 'The old price, shown struck through beside the '
                              'price. Leave empty when there is no discount.',
        'standard_price': 'What one costs you. Not shown to shoppers - Odoo '
                          'uses it for margins and the value of your stock.',
        'is_storable': 'Count this product in stock. Off for services and '
                       'things you never run out of.',
        'categ_id': "Odoo's own accounting and stock category - not the aisles "
                    "the app shows, which are Categories above.",
        'company_id': 'Which company sells it. Empty means every company.',
    }

    def _mart369_desk_taxes_for(self, name, product):
        """The taxes a tax box offers: the product's company's own (or the
        current company's, for a new product) - one "5%", not one per company
        - plus any the product already has, so nothing set disappears."""
        use = 'purchase' if name == 'supplier_taxes_id' else 'sale'
        company = (product.company_id if product else False) or self.env.company
        taxes = self.env['account.tax'].search([
            ('type_tax_use', '=', use), ('company_id', '=', company.id)])
        if product:
            taxes |= product[name]
        return taxes

    def _mart369_desk_kind_for(self, name, field, product=None):
        """Box kinds worked out from the field itself: its choices, its
        records. Built each time the form is read, so a new tax or company
        shows up without anybody editing a list."""
        if name == 'public_categ_ids':
            return {}
        if field.type == 'selection':
            return {'kind': 'select', 'options': [
                [key, label] for key, label in field._description_selection(self.env)]}
        if field.type == 'boolean':
            return {'kind': 'bool'}
        if field.type == 'many2one':
            Model = self.env[field.comodel_name]
            if field.comodel_name == 'res.company':
                records = self.env.user.company_ids
                none = 'All companies'
            else:
                records = Model.search([], limit=200)
                none = 'None'
            options = [[str(r.id), r.display_name] for r in records]
            if not field.required:
                options = [['', none]] + options
            return {'kind': 'select', 'options': options}
        if field.type == 'many2many':
            if field.comodel_name == 'account.tax':
                records = self._mart369_desk_taxes_for(name, product)
                several = len(records.company_id) > 1
                # Only when a product carries taxes of more than one company
                # does the company need saying - "5% (Sparenix)".
                return {'kind': 'tags', 'options': [
                    [r.id, '%s (%s)' % (r.display_name, r.company_id.name) if several else r.display_name]
                    for r in records]}
            records = self.env[field.comodel_name].search([], limit=200)
            return {'kind': 'tags', 'options': [[r.id, r.display_name] for r in records]}
        return {}

    def _mart369_desk_value_of(self, product, name, field, defaults):
        """What a box shows: the product's value, or Odoo's default for a new
        one - a new product gets the company's taxes and category, as Odoo's
        own form would give it."""
        raw = product[name] if product else defaults.get(name)
        if field.type == 'many2many':
            if product:
                return raw.ids
            ids = []
            for cmd in raw or []:
                if isinstance(cmd, (list, tuple)) and cmd and cmd[0] == 6:
                    ids = list(cmd[2])
                elif isinstance(cmd, (list, tuple)) and cmd and cmd[0] == 4:
                    ids.append(cmd[1])
                elif isinstance(cmd, int):
                    ids.append(cmd)
            return ids
        if field.type == 'many2one':
            rid = raw.id if hasattr(raw, 'id') else raw
            return str(rid) if rid else ''
        if field.type == 'boolean':
            return bool(raw)
        if field.type == 'selection':
            return raw or ''
        if field.type in ('float', 'monetary'):
            # Empty, not 0: a box reading "0" looks like a value somebody set.
            # Saving empty still stores 0.
            return raw or ''
        if field.type == 'integer':
            # 0 is a real answer here ("warning off"), so shown.
            return raw or 0
        return raw or ''

    # On hand is counted stock, not a column, so it is not in `_fields`. The
    # stock-aware module (mart369_catalog) offers the box and books it; here
    # there is no box and nothing to book.

    @api.model
    def _mart369_desk_on_hand_box(self, product):
        """(box, value) for the On hand box, or None when stock is not kept."""
        return None

    def _mart369_desk_set_on_hand(self, product, qty):
        return False

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

        # Odoo's defaults for a new product (taxes, category, type), so the
        # desk starts where Odoo's own form would.
        all_names = [n for _t, names in self.MART_DESK_GROUPS for n in names
                     if n in self._fields]
        defaults = {} if product else self.default_get(all_names)

        groups, values = [], {}
        for title, names in self.MART_DESK_GROUPS:
            boxes = []
            for name in names:
                if name == 'mart_on_hand':
                    got = self._mart369_desk_on_hand_box(product)
                    if got:
                        box, value = got
                        boxes.append(box)
                        values[name] = value
                    continue
                field = self._fields.get(name)
                if not field:
                    continue  # the module that supplies it is not installed
                if name not in self.MART_DESK_ALWAYS and ',%s,' % name in hidden:
                    continue
                boxes.append({
                    'name': name,
                    'label': self.MART_DESK_LABELS.get(name, field.string),
                    'help': self.MART_DESK_HELP.get(name, field.help or ''),
                    'widget': self._mart369_desk_widget(field),
                    'required': name == 'name',
                    **self._mart369_desk_kind_for(name, field, product),
                    **self.MART_DESK_KINDS.get(name, {}),
                })
                if product or name in defaults:
                    values[name] = self._mart369_desk_value_of(
                        product, name, field, defaults)
                    if not product and field.comodel_name == 'account.tax':
                        # Odoo's default is every company's default tax; a
                        # new product here starts with this company's only,
                        # the ones the box can show.
                        offered = {o[0] for o in boxes[-1]['options']}
                        values[name] = [i for i in values[name] if i in offered]
            if boxes:
                groups.append({
                    'title': title,
                    'boxes': boxes,
                    'deskOnly': title in self.MART_DESK_DESK_ONLY,
                })

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
                # The model's own order (sequence, then name). There is no
                # `complete_name` on this model in 19, though `display_name`
                # still reads "Parent / Child", which is what the label wants.
                {'id': c.id, 'name': c.display_name}
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
            elif field.type == 'many2one':
                vals[name] = int(value) if value else False
            elif field.type == 'boolean':
                vals[name] = bool(value)
            elif field.type == 'selection':
                vals[name] = value or False
            elif field.type in ('float', 'monetary'):
                vals[name] = self._mart369_desk_number(field, value)
            elif field.type == 'integer':
                vals[name] = int(self._mart369_desk_number(field, value, whole=True))
            else:
                vals[name] = value if value not in (None, False) else ''

        barcode = vals.get('barcode')
        if barcode and not str(barcode).isdigit():
            current = self.browse(int(product_id)).barcode if product_id else False
            # Only a barcode somebody just typed: an old one with letters,
            # left alone, must not stop this product's price being saved.
            if barcode != current:
                raise UserError(_("Barcode must be digits only."))

        if not product_id and not (vals.get('name') or '').strip():
            raise UserError(_("A product needs a name."))

        if 'image_1920' in (values or {}):
            # '' means "take the photograph away", which is not the same as
            # not mentioning it at all.
            vals['image_1920'] = values['image_1920'] or False

        photos = photos or {}
        demoted = False
        if product_id:
            product = self.browse(int(product_id)).exists()
            if not product:
                raise UserError(_("That product no longer exists."))
            promoted = self._mart369_desk_promoted(product, photos)
            if promoted:
                vals['image_1920'] = promoted.image_1920
            # The card picture being replaced moves into the gallery rather
            # than being lost - read before the write overwrites it.
            if photos.get('demote') and product.image_1920:
                demoted = product.image_1920
            product.write(vals)
            if promoted:
                promoted.unlink()
            if demoted and 'product_template_image_ids' in self._fields:
                self.env['product.image'].create({
                    'name': product.name or 'Photograph',
                    'image_1920': demoted,
                    'product_tmpl_id': product.id,
                })
        else:
            # The desk's list only shows published products, so one created
            # here and left unpublished would vanish the moment it was saved.
            # Published is what the person plainly meant.
            vals.setdefault('is_published', True)
            product = self.create(vals)

        self._mart369_desk_photos(product, photos)

        # Stock last: the product has to exist, and be storable, to be counted.
        on_hand = (values or {}).get('mart_on_hand')
        if on_hand not in (None, ''):
            self._mart369_desk_set_on_hand(
                product, self._mart369_desk_number(None, on_hand, label='On hand'))
        return product.id

    def _mart369_desk_number(self, field, value, whole=False, label=None):
        """A number box's value, refused in words when it is not a number.

        The screen only lets digits through, but this method is reachable on
        its own, and "abc" deserves "Price must be a number" rather than a
        ValueError from float()."""
        if value in (None, '', False):
            return 0.0
        try:
            number = float(value)
        except (TypeError, ValueError):
            number = None
        name = label or (self.MART_DESK_LABELS.get(field.name, field.string) if field else 'This box')
        if number is None or number != number or number in (float('inf'), float('-inf')):
            raise UserError(_("%s must be a number.", name))
        if number < 0:
            raise UserError(_("%s cannot be below zero.", name))
        if whole and number != int(number):
            raise UserError(_("%s must be a whole number.", name))
        return number

    def _mart369_desk_promoted(self, product, photos):
        """The gallery picture chosen to go on the card, if one was - only
        ever one of this product's own."""
        if not photos.get('promote') or 'product_template_image_ids' not in self._fields:
            return self.env['product.image']
        return product.product_template_image_ids.filtered(
            lambda r: r.id == int(photos['promote']))

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
                            limit=300, tab=None, mode=None, sort=None):
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
        domain = self._mart369_picker_domain(tab)
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
        domain += self._mart369_picker_mode_domain(mode)

        # Narrowed and sorted over the whole match before the page is cut:
        # "lowest stock first" and "only the low ones" read stock, which is
        # not a stored field, so neither can be a domain or an ORDER BY.
        found = self._mart369_picker_narrow(
            self.search(domain, order='name'), tab, sort)
        total = len(found)
        found = found[:limit]
        # The compute behind this is a single batched _read_group. Reading it
        # off the recordset keeps it that way; touching it per product inside
        # the loop below would be one query each.
        found.mapped('mart_page_differs')

        extras = self._mart369_picker_extras(found)
        return {
            **extras,
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

    # ------------------------------------------------ the desk's numbers strip

    @api.model
    def mart369_product_stats(self, product_id):
        """On hand, forecast, sold, price, cost and margin for one product -
        the figures Odoo's own form shows in its header. {} here: stock and
        sales are mart369_catalog's to answer, and without it the desk simply
        draws no strip."""
        product = self.browse(int(product_id)).exists()
        return self._mart369_product_stats(product) if product else {}

    @api.model
    def _mart369_product_stats(self, product):
        return {}

    # The picker's hooks. Stock tiles, stock tabs, the storefront filter and
    # the stock sort all need mart369_catalog, which depends on this module -
    # so it fills these in rather than this module reaching up for it. On
    # their own they give the plain picker: published, by name, no tiles.

    @api.model
    def _mart369_picker_domain(self, tab=None):
        # Hidden is the one tab this module can answer by itself.
        return [('is_published', '=', tab != 'off')]

    @api.model
    def _mart369_picker_mode_domain(self, mode=None):
        return []

    @api.model
    def _mart369_picker_narrow(self, found, tab=None, sort=None):
        return found

    @api.model
    def _mart369_picker_extras(self, page):
        """Merged into the picker's answer. {} here; the desk draws its tiles,
        tabs and storefront filter only when these come back."""
        return {}
