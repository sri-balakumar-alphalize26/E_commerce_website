from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.mart369.models.serializers import ART_CHOICES, ICON_CHOICES, TONE_CHOICES


class Mart369HomeMode(models.Model):
    """One app mode - Quick or Express - and everything shown inside it."""

    _name = 'mart369.home.mode'
    _description = '369 Mart App Mode'
    _inherit = ['mart369.serializable']
    _order = 'sequence, id'

    config_id = fields.Many2one(
        'mart369.config', string='Settings',
        required=True, ondelete='cascade', index=True)
    version_id = fields.Many2one(
        'mart369.home.version', string='Saved page',
        ondelete='cascade', index=True,
        help='Which saved home page this tab belongs to. Every saved page has '
             'its own Quick and its own Express, which is what makes a '
             'festival page a copy rather than an edit of the live one.')
    key = fields.Selection([
        ('quick', 'Quick - delivery in minutes'),
        ('all', 'Express - delivery in days'),
    ], string='Mode', required=True,
        help='Which tab of the app this configures. The app has exactly these '
             'two, so there is one record for each.')
    name = fields.Char(
        string='Name', required=True,
        help='Only used here in Odoo, to tell the two apart.')

    # ── What the shopper is told this tab is ──
    #
    # These three used to be hard-coded in the app - "Parts & peripherals in
    # minutes" and "Electronics, home & more · 2-5 day delivery" were written
    # into the storefront. Delivery promises change, and changing one meant a
    # developer and a deploy. They are the shop's words about its own service,
    # so they belong to the shop.
    label = fields.Char(
        string='Shown as',
        help='What the tab is called in the app: "Quick", "Express".')
    tagline = fields.Char(
        string='Promise',
        help='The line the app shows when someone switches to this tab, e.g. '
             '"Parts & peripherals in minutes" or "2-5 day delivery". This is '
             'a promise to the customer - keep it true.')
    # No default on purpose. A blanket one would have put a grid on Quick,
    # whose icon has always been a lightning bolt, and there would be no way
    # afterwards to tell "the default filled this in" from "somebody chose a
    # grid". Empty means "use this tab's own default", which `_copy_vals`
    # decides per key.
    icon = fields.Selection(
        ICON_CHOICES, string='Icon',
        help='The small icon beside the tab name. Left empty, each tab uses '
             'its own: a lightning bolt for Quick, a grid for Express.')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(
        default=True,
        help='Off: this whole tab disappears from the app.')

    free_delivery_at = fields.Float(
        string='Free delivery above', default=499.0, digits='Product Price',
        help='The app nudges the customer with "add X more for free delivery" '
             'until the basket reaches this amount.')

    # copy=True throughout: Odoo does not copy one-to-many fields by default,
    # and duplicating a saved home page that arrives empty is worse than not
    # being able to duplicate one at all.
    tab_ids = fields.One2many(
        'mart369.home.tab', 'mode_id', string='Tabs', copy=True)
    banner_ids = fields.One2many(
        'mart369.home.banner', 'mode_id', string='Banners', copy=True)
    tile_ids = fields.One2many(
        'mart369.home.tile', 'mode_id', string='Category Tiles', copy=True)
    section_ids = fields.One2many(
        'mart369.home.section', 'mode_id', string='Sections', copy=True)

    _key_uniq = models.Constraint(
        'unique (version_id, key)',
        'A saved home page can only have one setup per app mode.')

    @api.model
    def _get(self, key, version=None):
        """The Quick or Express setup of one saved home page.

        Since pages are saved under a name there is one `quick` per saved
        page, so matching on the key alone returns an arbitrary one - and the
        builder would open a festival page's bands while the shop serves the
        everyday one. So resolve the page first: the one asked for, else
        whichever is live right now, which is the same choice
        `_serialize_modes()` makes for the app's own feed.

        Searching rather than walking `version.mode_ids`, so that the caller's
        context reaches the query - `builder_load` asks with
        `active_test=False` precisely to find a switched-off mode.
        """
        version = version or self.env['mart369.home.version']._mart369_live()
        mode = self.browse()
        if version:
            mode = self.search(
                [('key', '=', key), ('version_id', '=', version.id)], limit=1)
        if not mode:
            # A saved page with no modes can only happen mid-upgrade, and a
            # blank home page is never the right answer to that: fall back to
            # the modes still hanging off the settings, as the feed does.
            mode = self.search(
                [('key', '=', key), ('version_id', '=', False)], limit=1)
        return mode

    # ------------------------------------------------------------- serialise

    # What the app falls back to when the shop has not been asked yet. The
    # exact words the storefront used to have written into it, so an upgrade
    # changes nothing until somebody edits them on purpose.
    _DEFAULT_COPY = {
        'quick': ('Quick', 'bolt', 'Parts & peripherals in minutes'),
        'all': ('Express', 'grid', 'Electronics, home & more · 2–5 day delivery'),
    }

    def _copy_vals(self):
        """Label, icon and promise, with the app's old defaults behind them."""
        self.ensure_one()
        label, icon, tagline = self._DEFAULT_COPY.get(
            self.key, (self.name or '', 'grid', ''))
        return {
            'label': self.label or label,
            'icon': self.icon or icon,
            'tagline': self.tagline or tagline,
        }

    def _serialize(self):
        """One mode: {label, icon, tagline, tabs, banners, categories,
        sections, freeDeliveryAt}."""
        self.ensure_one()
        sections = self.section_ids._live().sorted('sequence')
        # Resolve every product on the page once, so prices cost one query
        # instead of one per product.
        price_ctx = self._price_context(sections)
        return {
            **self._copy_vals(),
            'tabs': [t._serialize() for t in
                     self.tab_ids._live().sorted('sequence')],
            'banners': [b._serialize() for b in
                        self.banner_ids._live().sorted('sequence')],
            'categories': [c._serialize() for c in
                           self.tile_ids._live().sorted('sequence')],
            'sections': [s for s in (sec._serialize(price_ctx) for sec in sections)
                         if s],
            'freeDeliveryAt': self.free_delivery_at,
        }

    def _price_context(self, sections):
        """Prices for every product these sections will show, in one pass."""
        self.ensure_one()
        Template = self.env['product.template'].sudo()
        templates = Template.browse()
        for section in sections:
            templates |= section._resolve_products()
        return self.env['mart369.serializable']._price_context_for(
            templates)

    # ---------------------------------------------------------- the builder

    def _trash_list(self):
        """Everything of this mode's that is waiting in the Trash, newest first."""
        self.ensure_one()
        rows = []
        for records in (self.section_ids, self.banner_ids,
                        self.tile_ids, self.tab_ids):
            rows += [r._trash_vals() for r in records._trashed()]
        return sorted(rows, key=lambda r: r['deleted_at'] or '', reverse=True)

    # ------------------------------------------------ drawn, not described

    # Which kind each band model is called on the screens. The REST console
    # and the builder both speak in kinds; the Trash list names models. Say it
    # once, here, next to the records themselves.
    BAND_KIND = {
        'mart369.home.banner': 'banner',
        'mart369.home.tab': 'tab',
        'mart369.home.tile': 'tile',
        'mart369.home.section': 'section',
    }

    def _drawable(self, pick):
        """Bands serialized the way the app receives them, so a builder can
        draw them with the shop's own components.

        `pick` chooses which ones - `_kept()` for the page itself, `_trashed()`
        for the Trash. Both go through here rather than through two
        near-identical loops, because a Trash that describes a banner in words
        while the page draws it is two different answers to "what is this?".

        This sits on the mode rather than on a controller so the REST console
        and the Odoo builder draw from one body of code. Two copies would
        drift, and the drift would surface as "the preview looks different
        depending on which screen you opened it from".
        """
        self.ensure_one()
        sections = pick(self.section_ids).sorted('sequence')
        price_ctx = self._price_context(sections)

        def rows(records, serialize, stub=None):
            out = []
            for record in pick(records).sorted('sequence'):
                # A row with nothing in it serializes to None, because the app
                # should not draw a bare heading. The editor still has to show
                # it, or an empty row becomes invisible and unfixable.
                vals = serialize(record) or (stub(record) if stub else None)
                if not vals:
                    continue
                out.append(dict(vals, rid=record.id, active=record.active))
            return out

        return {
            'tabs': rows(self.tab_ids, lambda r: r._serialize()),
            'banners': rows(self.banner_ids, lambda r: r._serialize()),
            'categories': rows(self.tile_ids, lambda r: r._serialize()),
            'sections': rows(
                sections, lambda r: r._serialize(price_ctx),
                stub=lambda r: {'key': r.key or 'sec%s' % r.id,
                                'title': r.name or '', 'subtitle': r.subtitle or '',
                                'items': [], 'empty': True}),
        }

    def _preview_payload(self):
        """The app's own payload for this tab, hidden bands included."""
        self.ensure_one()
        return dict(self._drawable(lambda records: records._kept()),
                    freeDeliveryAt=self.free_delivery_at)

    def _trash_preview_map(self):
        """Everything in the Trash, drawn rather than described.

        The Trash list on its own says "Banner - New banner", which is not
        enough to decide whether to put something back: two banners called
        "Onam" tell you nothing, and a row's name says nothing about what was
        in it. So the same serialized payload the page is drawn from comes back
        for removed bands too, keyed by kind.
        """
        self.ensure_one()
        drawn = self._drawable(lambda records: records._trashed())
        # Keyed by "kind:id", because the Trash list is flat and each row needs
        # to find its own drawing without the screen re-deriving the mapping.
        group_kind = {'tabs': 'tab', 'banners': 'banner',
                      'categories': 'tile', 'sections': 'section'}
        out = {}
        for group, kind in group_kind.items():
            for vals in drawn.get(group, []):
                out['%s:%s' % (kind, vals['rid'])] = vals
        return out

    @api.model
    def builder_load(self, key, version_id=None):
        """Everything the visual builder screen needs for one mode, in one call.

        The mock on that screen is drawn from the same _serialize() the app
        reads, so what the operator sees is what the customer gets. Hidden
        records are included (with active=False) so they can be shown greyed
        out and switched back on.
        """
        version = self.env['mart369.home.version'].browse(
            version_id).exists() if version_id else None
        mode = self.with_context(active_test=False)._get(key, version=version)
        if not mode:
            raise UserError(_("There is no home page set up for '%s'.", key))

        sections = mode.section_ids._kept().sorted('sequence')
        price_ctx = mode._price_context(sections)
        Category = self.env['product.public.category']
        Tag = self.env['product.tag']

        data = {
            'mode': dict(
                mode._copy_vals(),
                id=mode.id,
                key=mode.key,
                name=mode.name,
                free_delivery_at=mode.free_delivery_at,
                active=mode.active,
            ),
            # This page's own tabs, not every saved page's - the switcher at the
            # top of the builder offers Quick and Express, and offering six
            # would be offering to edit a page nobody opened.
            'modes': [dict(m._copy_vals(), id=m.id, key=m.key, name=m.name,
                           active=m.active)
                      for m in self.with_context(active_test=False).search(
                          [('version_id', '=', mode.version_id.id)],
                          order='sequence, id')],
            'vocab': {
                'art': ART_CHOICES,
                'icons': ICON_CHOICES,
                'tones': TONE_CHOICES,
            },
            'bands': [s._builder_vals(price_ctx) for s in sections],
            'banners': [b._builder_vals()
                        for b in mode.banner_ids._kept().sorted('sequence')],
            'tiles': [t._builder_vals()
                      for t in mode.tile_ids._kept().sorted('sequence')],
            'tabs': [t._builder_vals()
                     for t in mode.tab_ids._kept().sorted('sequence')],
            'trash': mode._trash_list(),
            'trash_days': self.env['mart369.config'].sudo()._get()._trash_days(),
            'categories': [{'id': c.id, 'name': c.display_name}
                           for c in Category.search([])],
            'tags': [{'id': t.id, 'name': t.name} for t in Tag.search([], order='name')],
        }

        # The same three things the REST console gets, so a builder reading
        # over the ORM draws exactly what a builder reading over HTTP draws.
        data['preview'] = mode._preview_payload()
        data['trash_preview'] = mode._trash_preview_map()
        data['page'] = mode.version_id._serialize_card() if mode.version_id else None
        # The Trash list names Odoo models; the screens speak in kinds. Say
        # both, so a screen does not keep its own copy of the mapping and
        # drift from this one.
        for row in data.get('trash', []):
            row['kind'] = self.BAND_KIND.get(row.get('model'), '')
        return data
