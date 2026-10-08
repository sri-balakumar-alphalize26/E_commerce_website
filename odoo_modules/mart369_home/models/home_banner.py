import base64
import binascii

from markupsafe import Markup, escape

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools.mimetypes import guess_mimetype

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
    text_on_image = fields.Boolean(
        string='Show text on the picture', default=False,
        help='Off: an uploaded picture is shown on its own - for a designed '
             'banner that already carries its words and button. On: the small '
             'line, headline, offer line and Shop now are drawn over it.')

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

    def _mart369_picture_url(self):
        """The uploaded picture at full width, with its save time on the end
        so a replaced picture is not served from yesterday's cache."""
        self.ensure_one()
        if not self.image_1920:
            return ''
        stamp = int(self.write_date.timestamp()) if self.write_date else 0
        return '%s?unique=%d' % (self._image_url('image_1920', '1920x768'), stamp)

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
            vals['image'] = self._mart369_picture_url()
            if self.text_on_image:
                vals['textOnImage'] = True
        if self.href:
            vals['href'] = self.href
        return vals

    # Pictures the console may upload: a designed banner is a photo or a flat
    # graphic, never a script. 5 MB is far more than a 1600 x 640 JPEG needs.
    PICTURE_MAX_BYTES = 5 * 1024 * 1024
    PICTURE_TYPES = ('image/png', 'image/jpeg', 'image/webp')

    @api.model
    def _mart369_check_picture(self, value):
        """An upload from the console as Odoo stores it: base64 text, or False
        to take the picture off. Accepts a data: URL. Raises UserError with a
        sentence a shop owner can act on."""
        if not value:
            return False
        if not isinstance(value, str):
            raise UserError(self.env._('That picture could not be read. Please pick the file again.'))
        if value.startswith('data:'):
            value = value.split(',', 1)[-1]
        try:
            raw = base64.b64decode(value, validate=True)
        except (binascii.Error, ValueError):
            raise UserError(self.env._('That picture could not be read. Please pick the file again.'))
        if len(raw) > self.PICTURE_MAX_BYTES:
            raise UserError(self.env._('That picture is too big. Please use one under 5 MB.'))
        if guess_mimetype(raw) not in self.PICTURE_TYPES:
            raise UserError(self.env._('Please use a JPG, PNG or WebP picture.'))
        return value

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
            'image_url': self._mart369_picture_url(),
            'text_on_image': self.text_on_image,
            'write_date': fields.Datetime.to_string(self.write_date),
        }
