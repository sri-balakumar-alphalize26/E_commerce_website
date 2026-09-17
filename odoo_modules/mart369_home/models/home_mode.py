from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .serializers import ART_CHOICES, ICON_CHOICES, TONE_CHOICES


class Mart369HomeMode(models.Model):
    """One app mode - Quick or Express - and everything shown inside it."""

    _name = 'mart369.home.mode'
    _description = '369 Mart App Mode'
    _inherit = ['mart369.home.serializable']
    _order = 'sequence, id'

    config_id = fields.Many2one(
        'mart369.home.config', string='Settings',
        required=True, ondelete='cascade', index=True)
    key = fields.Selection([
        ('quick', 'Quick - delivery in minutes'),
        ('all', 'Express - delivery in days'),
    ], string='Mode', required=True,
        help='Which tab of the app this configures. The app has exactly these '
             'two, so there is one record for each.')
    name = fields.Char(
        string='Name', required=True,
        help='Only used here in Odoo, to tell the two apart.')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(
        default=True,
        help='Off: this whole tab disappears from the app.')

    free_delivery_at = fields.Float(
        string='Free delivery above', default=499.0, digits='Product Price',
        help='The app nudges the customer with "add X more for free delivery" '
             'until the basket reaches this amount.')

    tab_ids = fields.One2many('mart369.home.tab', 'mode_id', string='Tabs')
    banner_ids = fields.One2many('mart369.home.banner', 'mode_id', string='Banners')
    tile_ids = fields.One2many('mart369.home.tile', 'mode_id', string='Category Tiles')
    section_ids = fields.One2many('mart369.home.section', 'mode_id', string='Sections')

    _key_uniq = models.Constraint(
        'unique (key)',
        'There can only be one setup per app mode.')

    @api.model
    def _get(self, key):
        return self.search([('key', '=', key)], limit=1)

    # ------------------------------------------------------------- serialise

    def _serialize(self):
        """One mode: {tabs, banners, categories, sections, freeDeliveryAt}."""
        self.ensure_one()
        sections = self.section_ids._live().sorted('sequence')
        # Resolve every product on the page once, so prices cost one query
        # instead of one per product.
        price_ctx = self._price_context(sections)
        return {
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
        return self.env['mart369.home.serializable']._price_context_for(
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

    @api.model
    def builder_load(self, key):
        """Everything the visual builder screen needs for one mode, in one call.

        The mock on that screen is drawn from the same _serialize() the app
        reads, so what the operator sees is what the customer gets. Hidden
        records are included (with active=False) so they can be shown greyed
        out and switched back on.
        """
        mode = self.with_context(active_test=False)._get(key)
        if not mode:
            raise UserError(_("There is no home page set up for '%s'.", key))

        sections = mode.section_ids._kept().sorted('sequence')
        price_ctx = mode._price_context(sections)
        Category = self.env['product.public.category']
        Tag = self.env['product.tag']

        return {
            'mode': {
                'id': mode.id,
                'key': mode.key,
                'name': mode.name,
                'free_delivery_at': mode.free_delivery_at,
                'active': mode.active,
            },
            'modes': [{'id': m.id, 'key': m.key, 'name': m.name, 'active': m.active}
                      for m in self.with_context(active_test=False).search([])],
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
            'trash_days': self.env['mart369.home.config'].sudo()._get()._trash_days(),
            'categories': [{'id': c.id, 'name': c.display_name}
                           for c in Category.search([])],
            'tags': [{'id': t.id, 'name': t.name} for t in Tag.search([], order='name')],
        }
