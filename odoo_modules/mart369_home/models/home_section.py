from datetime import timedelta

from markupsafe import Markup, escape

from odoo import api, fields, models
from odoo.fields import Domain

from .serializers import ART_CHOICES, slugify


class Mart369HomeSection(models.Model):
    """One band of the home page.

    Either a row of products ("Fresh fruits") or a strip of banners. Both live
    in this one model on purpose: the operator then orders the whole home page
    with a single drag handle, which is exactly how the app reads it.
    """

    _name = 'mart369.home.section'
    _description = '369 Mart Home Section'
    _inherit = ['mart369.home.serializable', 'mart369.home.trashable']
    _order = 'sequence, id'
    _trash_what = 'Home section'

    mode_id = fields.Many2one(
        'mart369.home.mode', string='App Mode',
        required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(
        default=10,
        help='Drag the rows to change the order of the home page. This is the '
             'order the customer scrolls through.')
    active = fields.Boolean(
        default=True,
        help='Off: this band disappears from the app. Nothing is deleted.')

    kind = fields.Selection([
        ('rail', 'Product row'),
        ('banner_row', 'Banner strip'),
    ], string='Kind', required=True, default='rail',
        help='A product row shows products side by side. A banner strip shows '
             'one or two promo cards across the page.')

    # -- Heading (product rows) --
    name = fields.Char(
        string='Title',
        help='The heading above the row, e.g. Fresh fruits.')
    key = fields.Char(
        string='Key',
        help='A short internal name, e.g. fruits. Filled in for you.')
    subtitle = fields.Char(
        string='Subtitle',
        help='The smaller line under the heading. Leave empty for none.')
    view_all_route = fields.Char(
        string='"View all" opens',
        help='Where the View all link goes, e.g. '
             'fruits-vegetables/fresh-fruits. Leave empty and no View all '
             'link is shown.')

    # -- Where the products come from --
    source = fields.Selection([
        ('category', 'A product category'),
        ('manual', 'Products I pick myself'),
        ('rule', 'Chosen automatically'),
        ('tag', 'A product tag'),
    ], string='Products from', default='category',
        help='How this row decides what to show. Pick a category and it keeps '
             'itself up to date; pick products yourself for full control.')
    public_categ_id = fields.Many2one(
        'product.public.category', string='Category',
        help='Every published product in this category appears in the row.')
    include_child_categs = fields.Boolean(
        string='Include sub-categories', default=True,
        help='On: products in categories underneath this one count too.')
    product_tag_id = fields.Many2one(
        'product.tag', string='Tag',
        help='Every published product carrying this tag appears in the row. '
             'Tag a product under its General Information page.')
    rule = fields.Selection([
        ('new', 'Newest first'),
        ('best', 'Best sellers'),
        ('discount', 'Biggest discount'),
    ], string='Rule',
        help='The row fills itself and stays current with no upkeep.')
    rule_days = fields.Integer(
        string='Sales over the last (days)', default=365,
        help='Only for best sellers: how far back to count orders.')
    limit = fields.Integer(
        string='Show at most', default=12,
        help='How many products the row holds before the customer scrolls.')

    picked_product_ids = fields.One2many(
        'mart369.home.section.product', 'section_id', string='Chosen products')
    banner_line_ids = fields.One2many(
        'mart369.home.section.banner', 'section_id', string='Banners')

    # -- What will actually show --
    preview_product_ids = fields.Many2many(
        'product.template', string='Will show',
        compute='_compute_preview_products')
    product_count = fields.Integer(
        string='Products', compute='_compute_preview_products')
    preview_html = fields.Html(
        string='Preview', compute='_compute_preview_html', sanitize=False)

    @api.onchange('name')
    def _onchange_name(self):
        if self.name and not self.key:
            self.key = slugify(self.name)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('key') and vals.get('name'):
                vals['key'] = slugify(vals['name'])
        return super().create(vals_list)

    def action_toggle_active(self):
        for rec in self:
            rec.active = not rec.active
        return True

    # ------------------------------------------------------- which products

    def _base_domain(self):
        """Products a row may ever show: published, and in stock if asked."""
        domain = Domain([('is_published', '=', True)])
        config = self.env['mart369.home.config'].sudo()._get()
        Template = self.env['product.template']
        if config.hide_out_of_stock and 'free_qty' in Template._fields:
            domain &= Domain([('free_qty', '>', 0)])
        return domain

    def _resolve_products(self):
        """The products this row will show, in the order it will show them.

        One method feeds both the preview in the form and the JSON the app
        reads, so what an operator sees here is what a customer gets.
        """
        self.ensure_one()
        Template = self.env['product.template'].sudo()
        if self.kind != 'rail':
            return Template.browse()

        domain = self._base_domain()
        limit = self.limit or 12

        if self.source == 'manual':
            # Order comes from the line rows. A many2many could not hold it:
            # Odoo always reads those back in the product's own order.
            picked = self.picked_product_ids.sorted('sequence').product_tmpl_id
            return picked.filtered_domain(list(domain))[:limit]

        if self.source == 'category':
            if not self.public_categ_id:
                return Template.browse()
            operator = 'child_of' if self.include_child_categs else 'in'
            return Template.search(
                domain & Domain([('public_categ_ids', operator,
                                  self.public_categ_id.id)]),
                order='website_sequence, id', limit=limit)

        if self.source == 'tag':
            if not self.product_tag_id:
                return Template.browse()
            return Template.search(
                domain & Domain([('product_tag_ids', 'in',
                                  self.product_tag_id.ids)]),
                order='website_sequence, id', limit=limit)

        if self.source == 'rule':
            if self.rule == 'new':
                return Template.search(
                    domain, limit=limit,
                    order='publish_date desc, create_date desc, id desc')
            if self.rule == 'best':
                return self._products_best_sellers(domain, limit)
            if self.rule == 'discount':
                return self._products_biggest_discount(domain, limit)

        return Template.browse()

    def _products_best_sellers(self, domain, limit):
        """Top sellers, counted from confirmed orders.

        Deliberately not product.template.sales_count: that field computes to
        zero for anyone who is not a salesperson, and sudo() does not change
        that - it bypasses access rules but keeps the same user. On a public
        endpoint every product would score zero and the row would come back in
        an arbitrary order.
        """
        self.ensure_one()
        Template = self.env['product.template'].sudo()
        candidates = Template.search(domain)
        if not candidates:
            return Template.browse()

        Report = self.env['sale.report'].sudo()
        date_from = fields.Date.today() - timedelta(days=self.rule_days or 365)
        groups = Report._read_group(
            [('state', 'in', Report._get_done_states()),
             ('date', '>=', date_from),
             ('product_tmpl_id', 'in', candidates.ids)],
            groupby=['product_tmpl_id'],
            aggregates=['product_uom_qty:sum'],
            order='product_uom_qty:sum desc',
            limit=limit,
        )
        ranked = Template.browse([group[0].id for group in groups])
        if len(ranked) < limit:
            # Nothing sold yet, or a young catalogue: top up with the newest.
            filler = (candidates - ranked).sorted(
                key=lambda p: (p.publish_date or p.create_date), reverse=True)
            ranked |= filler[:limit - len(ranked)]
        return ranked[:limit]

    def _products_biggest_discount(self, domain, limit):
        """Largest saving against the struck-through price.

        Two columns cannot be compared inside a domain, so this narrows the
        field in SQL and ranks in Python.
        """
        self.ensure_one()
        Template = self.env['product.template'].sudo()
        candidates = Template.search(
            domain & Domain([('compare_list_price', '>', 0)]),
            limit=max(limit * 10, 100))
        candidates = candidates.filtered(
            lambda p: p.compare_list_price > p.list_price > 0)
        return candidates.sorted(
            key=lambda p: ((p.compare_list_price - p.list_price)
                           / p.compare_list_price),
            reverse=True)[:limit]

    @api.depends('kind', 'source', 'public_categ_id', 'include_child_categs',
                 'product_tag_id', 'rule', 'rule_days', 'limit',
                 'picked_product_ids.product_tmpl_id',
                 'picked_product_ids.sequence')
    def _compute_preview_products(self):
        for rec in self:
            products = rec._resolve_products()
            rec.preview_product_ids = products
            rec.product_count = len(products)

    # ----------------------------------------------------------- rendering

    @api.depends('name', 'subtitle', 'kind', 'preview_product_ids',
                 'banner_line_ids.banner_id')
    def _compute_preview_html(self):
        """The band drawn the way the app draws it.

        sanitize=False is safe: every operator-entered value goes through
        escape(), and the only markup is ours.
        """
        for rec in self:
            if rec.kind == 'banner_row':
                rec.preview_html = rec._preview_banner_strip()
            else:
                rec.preview_html = rec._preview_rail()

    def _preview_banner_strip(self):
        self.ensure_one()
        cards = []
        for banner in self.banner_line_ids.sorted('sequence').banner_id:
            cards.append(
                '<div class="mart-pv-strip-card mart-pv-tone-%s">'
                '<span class="mart-pv-kicker">%s</span>'
                '<span class="mart-pv-title">%s</span>'
                '</div>' % (
                    escape(banner.tone or 'green'),
                    escape(banner.kicker or ''),
                    escape(banner.name or banner.key or ''),
                ))
        if cards:
            body = '<div class="mart-pv-strip">%s</div>' % ''.join(cards)
        else:
            body = ('<div class="mart-pv-empty">No banners chosen yet. '
                    'This strip stays out of the app until it has one.</div>')
        return Markup('<div class="mart-pv">%s</div>') % Markup(body)

    def _preview_rail(self):
        self.ensure_one()
        cards = []
        for product in self.preview_product_ids[:8]:
            cards.append(
                '<div class="mart-pv-card">'
                '<span class="mart-pv-card-img"></span>'
                '<span class="mart-pv-card-name">%s</span>'
                '<span class="mart-pv-card-price">%s%s</span>'
                '</div>' % (
                    escape(product.name or ''),
                    escape(product.currency_id.symbol or ''),
                    escape('%.0f' % (product.list_price or 0.0)),
                ))
        if cards:
            body = '<div class="mart-pv-rail">%s</div>' % ''.join(cards)
        else:
            body = ('<div class="mart-pv-empty">No products match yet. '
                    'This row stays out of the app until it has some.</div>')

        subtitle = ('<span class="mart-pv-h2">%s</span>' % escape(self.subtitle)
                    if self.subtitle else '')
        view_all = ('<span class="mart-pv-all">View all &rsaquo;</span>'
                    if self.view_all_route else '')
        head = ('<div class="mart-pv-head">'
                '<span class="mart-pv-h1">%s</span>%s%s'
                '</div>' % (escape(self.name or 'Untitled row'),
                            subtitle, view_all))
        return Markup('<div class="mart-pv">%s%s</div>') % (
            Markup(head), Markup(body))

    # ----------------------------------------------------------- serialise

    def _serialize(self, price_ctx):
        """One entry of the app's `sections` array, or None to leave it out."""
        self.ensure_one()

        if self.kind == 'banner_row':
            keys = [line.banner_id.key
                    for line in self.banner_line_ids.sorted('sequence')
                    if line.banner_id.active and not line.banner_id.deleted_at
                    and line.banner_id.key]
            # A banner strip carries this key and nothing else - that is how
            # the app tells it apart from a product row.
            return {'banner': keys} if keys else None

        products = self._resolve_products()
        overrides = {line.product_tmpl_id.id: line
                     for line in self.picked_product_ids}
        items = [self._serialize_product(p, overrides.get(p.id), price_ctx)
                 for p in products]
        if not items:
            # An empty row would render as a bare heading. Leave it out.
            return None

        vals = {
            'key': self.key or 'sec%s' % self.id,
            'title': self.name or '',
            'subtitle': self.subtitle or '',
            'items': items,
        }
        if self.view_all_route:
            vals['route'] = self.view_all_route
        return vals

    def _serialize_product(self, product, line, price_ctx):
        """One product card. Delegates to the shared helper so the home
        page and the product page cannot drift apart."""
        self.ensure_one()
        return self.env['mart369.home.serializable']._serialize_product(
            product, line, price_ctx, self.mode_id.key)

    # ---------------------------------------------------------- the builder

    def _builder_vals(self, price_ctx):
        """What the visual builder needs to draw and edit this band.

        `preview` is the same dict the app receives for this band (or None
        when it has nothing to show), so the mock and the app agree.
        """
        self.ensure_one()
        picked = []
        for line in self.picked_product_ids.sorted('sequence'):
            picked.append({
                'id': line.id,
                'sequence': line.sequence,
                'product_tmpl_id': line.product_tmpl_id.id,
                'product_name': line.product_tmpl_id.display_name,
                'name_override': line.name_override or '',
                'unit_override': line.unit_override or '',
                'art_override': line.art_override or '',
                'color_override': line.color_override or '',
                'label_override': line.label_override or '',
                'note_override': line.note_override or '',
                'tag_override': line.tag_override or '',
                'delivery_override': line.delivery_override or '',
            })
        lines = [{
            'id': line.id,
            'sequence': line.sequence,
            'banner_id': line.banner_id.id,
            'banner_key': line.banner_id.key,
            'banner_name': line.banner_id.name or line.banner_id.key,
            'banner_active': line.banner_id.active,
        } for line in self.banner_line_ids.sorted('sequence')]

        return {
            'id': self.id,
            'kind': self.kind,
            'active': self.active,
            'sequence': self.sequence,
            'name': self.name or '',
            'key': self.key or '',
            'subtitle': self.subtitle or '',
            'view_all_route': self.view_all_route or '',
            'source': self.source,
            'public_categ_id': self.public_categ_id.id or False,
            'public_categ_name': self.public_categ_id.display_name or '',
            'include_child_categs': self.include_child_categs,
            'product_tag_id': self.product_tag_id.id or False,
            'product_tag_name': self.product_tag_id.name or '',
            'rule': self.rule or False,
            'rule_days': self.rule_days,
            'limit': self.limit,
            'product_count': self.product_count,
            'picked': picked,
            'lines': lines,
            'preview': self._serialize(price_ctx),
        }


class Mart369HomeSectionProduct(models.Model):
    """One hand-picked product inside a row.

    The override fields apply to this placement only - the product itself is
    never changed, so the same product can read differently in two rows.
    """

    _name = 'mart369.home.section.product'
    _description = '369 Mart Chosen Product'
    _order = 'sequence, id'

    section_id = fields.Many2one(
        'mart369.home.section', string='Section',
        required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(
        default=10,
        help='Drag the rows to change the order the products appear in.')
    product_tmpl_id = fields.Many2one(
        'product.template', string='Product', required=True,
        ondelete='cascade', domain=[('is_published', '=', True)],
        help='Unpublish a product and it drops out of the row on its own - '
             'there is no need to come back and remove it here.')

    name_override = fields.Char(
        string='Show as',
        help='Optional. A different name, just in this row.')
    unit_override = fields.Char(
        string='Size',
        help='Optional. e.g. 1 kg, 500 g, 2 pieces.')
    art_override = fields.Selection(
        ART_CHOICES, string='Drawing',
        help='Optional. Used only when the product has no photo.')
    color_override = fields.Char(
        string='Drawing colour', help='Optional tint, e.g. #e0453a.')
    label_override = fields.Char(
        string='Text on drawing', help='Optional short word, e.g. ATTA.')
    note_override = fields.Char(
        string='Small note', help='Optional, e.g. Approx 250-400 g.')
    tag_override = fields.Char(
        string='Badge', help='Optional pill on the card, e.g. New.')
    delivery_override = fields.Char(
        string='Delivery', help='Express only, e.g. 3-5 days.')

    _product_uniq = models.Constraint(
        'unique (section_id, product_tmpl_id)',
        'That product is already in this row.')


class Mart369HomeSectionBanner(models.Model):
    """One banner inside a banner strip."""

    _name = 'mart369.home.section.banner'
    _description = '369 Mart Banner in a Strip'
    _order = 'sequence, id'

    section_id = fields.Many2one(
        'mart369.home.section', string='Section',
        required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(
        default=10,
        help='Drag the rows to change the order the banners appear in.')
    banner_id = fields.Many2one(
        'mart369.home.banner', string='Banner', required=True,
        ondelete='cascade',
        help='Banners are shared. Edit one under Banners and every strip '
             'using it updates.')
