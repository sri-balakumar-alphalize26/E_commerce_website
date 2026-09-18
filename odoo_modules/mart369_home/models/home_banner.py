from markupsafe import Markup, escape

from odoo import api, fields, models

from odoo.addons.mart369.models.serializers import TONE_CHOICES, TONE_CSS, slugify


class Mart369HomeBanner(models.Model):
    """A promo card. Shown in the carousel at the top of the app, and reusable
    in any number of banner strips further down the page."""

    _name = 'mart369.home.banner'
    _description = '369 Mart Home Banner'
    _inherit = ['image.mixin', 'mart369.serializable',
                'mart369.home.trashable']
    _order = 'sequence, id'
    _trash_what = 'Banner'

    mode_id = fields.Many2one(
        'mart369.home.mode', string='App Mode',
        required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(
        default=10,
        help='Drag the rows to change the order the banners slide past in.')
    active = fields.Boolean(
        default=True,
        help='Off: this banner disappears from the app, including from any '
             'banner strip that uses it. Nothing is deleted - switch it back '
             'on and it returns.')

    key = fields.Char(
        string='Key', required=True,
        help='A short internal name, e.g. b1. Banner strips refer to banners '
             'by this. Leave it alone once the app is live.')
    kicker = fields.Char(
        string='Small line above',
        help='The little line above the headline, e.g. Fresh fruit week.')
    name = fields.Char(
        string='Headline',
        help='The big words on the banner, e.g. Fruits picked this morning.')
    note = fields.Char(
        string='Offer line',
        help='The offer underneath, e.g. Up to 30% off.')
    tone = fields.Selection(
        TONE_CHOICES, string='Colour', required=True, default='green',
        help='The background colour, used when no picture is uploaded and as '
             'the colour behind a picture while it loads.')

    art_lines = fields.Text(
        string='Drawings',
        help='Only used when no picture is uploaded: the app draws these '
             'instead. One name per line, e.g.\nApple\nOrange\nBanana\n'
             'Pick from the list on any product tile.')

    href = fields.Char(
        string='Opens',
        help='Where tapping the banner takes the customer, e.g. /category/'
             'fruits-vegetables. Leave empty for a banner that does nothing.')

    usage_count = fields.Integer(
        string='Used in strips', compute='_compute_usage_count',
        help='How many banner strips on the home page show this banner.')
    preview_html = fields.Html(
        string='Preview', compute='_compute_preview_html', sanitize=False)

    _key_uniq = models.Constraint(
        'unique (mode_id, key)',
        'Two banners in the same app mode cannot share a key.')

    @api.onchange('name')
    def _onchange_name(self):
        if self.name and not self.key:
            self.key = slugify(self.name)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('key'):
                vals['key'] = slugify(vals.get('name')) or 'banner'
        return super().create(vals_list)

    def _compute_usage_count(self):
        Line = self.env['mart369.home.section.banner']
        counts = dict(Line._read_group(
            [('banner_id', 'in', self.ids)], groupby=['banner_id'],
            aggregates=['__count']))
        for rec in self:
            rec.usage_count = counts.get(rec, 0)

    def action_toggle_active(self):
        for rec in self:
            rec.active = not rec.active
        return True

    # ------------------------------------------------------------- rendering

    @api.depends('kicker', 'name', 'note', 'tone', 'image_1920')
    def _compute_preview_html(self):
        """The banner drawn the way the app draws it.

        sanitize=False is safe here: every operator-entered value goes through
        escape() below, and the only markup is ours.
        """
        for rec in self:
            if rec.image_1920:
                raw = rec.image_1920
                b64 = raw if isinstance(raw, str) else raw.decode()
                bg = ("background-image:url('data:image/png;base64,%s');"
                      "background-size:cover;background-position:center;" % b64)
            else:
                bg = 'background:%s;' % TONE_CSS.get(rec.tone or 'green',
                                                     TONE_CSS['green'])
            parts = []
            if rec.kicker:
                parts.append('<span class="mart-pv-kicker">%s</span>'
                             % escape(rec.kicker))
            if rec.name:
                parts.append('<span class="mart-pv-title">%s</span>'
                             % escape(rec.name))
            if rec.note:
                parts.append('<span class="mart-pv-note">%s</span>'
                             % escape(rec.note))
            if not parts:
                parts.append('<span class="mart-pv-title">Picture only</span>')
            rec.preview_html = Markup(
                '<div class="mart-pv"><div class="mart-pv-banner" style="%s">'
                '<div class="mart-pv-banner-in">%s</div></div></div>'
            ) % (Markup(bg), Markup(''.join(parts)))

    # ------------------------------------------------------------- serialise

    def _serialize(self):
        self.ensure_one()
        vals = {
            'id': self.key,
            'kicker': self.kicker or '',
            'title': self.name or '',
            'note': self.note or '',
            'tone': self.tone,
            'art': self._lines_to_list(self.art_lines),
        }
        if self.image_1920:
            vals['image'] = self._image_url('image_1024', '1024x512')
        if self.href:
            vals['href'] = self.href
        return vals

    def _can_return_content(self, field_name=None, access_token=None):
        """Let the app load banner pictures without logging in. Only the
        picture - the record itself stays private."""
        if field_name in ('image_1920', 'image_1024', 'image_512',
                          'image_256', 'image_128'):
            return True
        return super()._can_return_content(field_name, access_token)

    def _builder_vals(self):
        """What the visual builder needs to list and edit this banner."""
        self.ensure_one()
        return {
            'id': self.id,
            'key': self.key,
            'kicker': self.kicker or '',
            'name': self.name or '',
            'note': self.note or '',
            'tone': self.tone,
            'art_lines': self.art_lines or '',
            'href': self.href or '',
            'active': self.active,
            'sequence': self.sequence,
            'usage_count': self.usage_count,
            'has_image': bool(self.image_1920),
            'image_url': (self._image_url('image_1024', '1024x512')
                          if self.image_1920 else ''),
            'write_date': fields.Datetime.to_string(self.write_date),
        }
