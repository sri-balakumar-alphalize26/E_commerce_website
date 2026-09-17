from markupsafe import Markup, escape

from odoo import api, fields, models

from .serializers import ART_CHOICES, slugify


class Mart369HomeTile(models.Model):
    """One rounded tile in the category strip under the banner carousel."""

    _name = 'mart369.home.tile'
    _description = '369 Mart Category Tile'
    _inherit = ['image.mixin', 'mart369.home.serializable',
                'mart369.home.trashable']
    _order = 'sequence, id'
    _trash_what = 'Category tile'

    mode_id = fields.Many2one(
        'mart369.home.mode', string='App Mode',
        required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(
        default=10,
        help='Drag the rows to change the order the tiles appear in.')
    active = fields.Boolean(
        default=True,
        help='Off: this tile disappears from the app.')

    name = fields.Char(
        string='Label', required=True,
        help='The words under the tile, e.g. Fresh fruits.')
    key = fields.Char(
        string='Key', required=True,
        help='A short internal name, e.g. fruits. Filled in for you from the '
             'label.')

    public_categ_id = fields.Many2one(
        'product.public.category', string='Category',
        help='Optional. Link the tile to a shop category and it can borrow '
             'the category picture. A tile does not have to be a category - '
             'it can point anywhere.')
    route = fields.Char(
        string='Opens',
        help='Where tapping the tile takes the customer, e.g. '
             'fruits-vegetables/fresh-fruits.')

    # ── Picture ──
    image_source = fields.Selection([
        ('upload', 'A picture uploaded here'),
        ('category', 'The category picture'),
        ('url', 'A picture elsewhere on the web'),
        ('art', 'A drawing (no picture)'),
    ], string='Picture', required=True, default='upload',
        help='Where the tile gets its picture. Choose "a drawing" and the app '
             'draws one itself - useful before you have photos.')
    image_url = fields.Char(
        string='Picture address',
        help='The full web address of the picture, starting with https://')
    image_path = fields.Char(
        string='The app loads', compute='_compute_image_path',
        help='The exact address the app will use. Empty means the app falls '
             'back to the drawing below.')

    # ── Drawing fallback ──
    art = fields.Selection(
        ART_CHOICES, string='Drawing', default='Pack',
        help='Used when there is no picture. The app draws this itself.')
    color = fields.Char(
        string='Drawing colour',
        help='Optional tint for the drawing, e.g. #b0662a.')
    badge = fields.Char(
        string='Text on the drawing',
        help='Optional short word drawn inside, e.g. ATTA.')
    bg = fields.Char(
        string='Tile background', default='#f1f4f6',
        help='The colour behind the tile, e.g. #fdecec.')

    preview_html = fields.Html(
        string='Preview', compute='_compute_preview_html', sanitize=False)

    _key_uniq = models.Constraint(
        'unique (mode_id, key)',
        'Two tiles in the same app mode cannot share a key.')

    @api.onchange('name')
    def _onchange_name(self):
        if self.name and not self.key:
            self.key = slugify(self.name)

    @api.onchange('public_categ_id')
    def _onchange_public_categ_id(self):
        if self.public_categ_id:
            if not self.name:
                self.name = self.public_categ_id.name
            if not self.key:
                self.key = slugify(self.public_categ_id.name)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('key'):
                vals['key'] = slugify(vals.get('name')) or 'tile'
        return super().create(vals_list)

    def action_toggle_active(self):
        for rec in self:
            rec.active = not rec.active
        return True

    @api.depends('image_source', 'image_1920', 'image_url',
                 'public_categ_id.image_1920')
    def _compute_image_path(self):
        for rec in self:
            if rec.image_source == 'url':
                rec.image_path = rec.image_url or ''
            elif rec.image_source == 'category' and rec.public_categ_id.image_1920:
                rec.image_path = rec._image_url(
                    'image_512', '256x256', record=rec.public_categ_id)
            elif rec.image_source == 'upload' and rec.image_1920:
                rec.image_path = rec._image_url('image_512', '256x256')
            else:
                rec.image_path = ''

    @api.depends('name', 'bg', 'color', 'badge', 'image_path')
    def _compute_preview_html(self):
        for rec in self:
            swatch = escape(rec.bg or '#f1f4f6')
            inner = escape(rec.badge or (rec.art or '')[:6] or '')
            rec.preview_html = Markup(
                '<div class="mart-pv"><div class="mart-pv-tile">'
                '<span class="mart-pv-tile-art" style="background:%s;color:%s">%s</span>'
                '<span class="mart-pv-tile-label">%s</span>'
                '</div></div>'
            ) % (swatch, escape(rec.color or '#5b6b76'), inner,
                 escape(rec.name or 'Untitled'))

    # ------------------------------------------------------------- serialise

    def _serialize(self):
        self.ensure_one()
        vals = {
            'key': self.key,
            'image': self.image_path or '',
            'label': self.name,
            'art': self.art or 'Pack',
            'bg': self.bg or '',
        }
        # Optional keys are left out entirely, never sent as null.
        if self.color:
            vals['color'] = self.color
        if self.badge:
            vals['t'] = self.badge
        if self.route:
            vals['route'] = self.route
        return vals

    def _can_return_content(self, field_name=None, access_token=None):
        """Let the app load tile pictures without logging in. Only the
        picture - the record itself stays private."""
        if field_name in ('image_1920', 'image_1024', 'image_512',
                          'image_256', 'image_128'):
            return True
        return super()._can_return_content(field_name, access_token)

    def _builder_vals(self):
        """What the visual builder needs to list and edit this tile."""
        self.ensure_one()
        return {
            'id': self.id,
            'key': self.key,
            'name': self.name,
            'route': self.route or '',
            'public_categ_id': self.public_categ_id.id or False,
            'image_source': self.image_source,
            'image_url': self.image_url or '',
            'image_path': self.image_path or '',
            'art': self.art or 'Pack',
            'color': self.color or '',
            'badge': self.badge or '',
            'bg': self.bg or '#f1f4f6',
            'active': self.active,
            'sequence': self.sequence,
            'has_image': bool(self.image_1920),
            'write_date': fields.Datetime.to_string(self.write_date),
        }
