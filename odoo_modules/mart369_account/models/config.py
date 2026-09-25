"""Settings > Reviews: what a customer may attach, and which words hold a review.

Photos and videos are stored in Odoo's own filestore and travel with every
backup, so how many and how big is the shop's call - and it is enforced on the
server (review_media.py), where an app cannot talk its way past it. Changes
apply to new uploads.

The blocked words add to the built-in list in review_filter.py; phone numbers
and links are always held whatever is here.
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

REVIEW_FIELDS = {
    # console key: (mart369.config field, kind)
    'maxPhotos': ('review_max_photos', int),
    'photoMb': ('review_photo_mb', int),
    'video': ('review_video', bool),
    'videoSeconds': ('review_video_seconds', int),
    'videoMb': ('review_video_mb', int),
    'blockedWords': ('review_blocked_words', str),
}


class Mart369Config(models.Model):
    _inherit = 'mart369.config'

    review_max_photos = fields.Integer(string='Photos per review', default=5)
    review_photo_mb = fields.Integer(string='Max size per photo (MB)', default=5)
    review_video = fields.Boolean(string='Allow a video', default=True)
    review_video_seconds = fields.Integer(string='Max video length (seconds)', default=30)
    review_video_mb = fields.Integer(string='Max video size (MB)', default=25)
    review_blocked_words = fields.Text(
        string='Also hold reviews with these words',
        help='One per line, any language. Adds to the built-in list.')

    @api.constrains('review_max_photos', 'review_photo_mb', 'review_video_seconds', 'review_video_mb')
    def _check_review_limits(self):
        for config in self:
            if config.review_max_photos < 0 or config.review_photo_mb < 1 \
                    or config.review_video_seconds < 1 or config.review_video_mb < 1:
                raise ValidationError(_('Review limits must be positive.'))

    @api.model
    def _mart369_review_limits(self):
        config = self.sudo()._get()
        return {
            'maxPhotos': config.review_max_photos,
            'photoBytes': config.review_photo_mb * 1024 * 1024,
            'video': bool(config.review_video),
            'videoSeconds': config.review_video_seconds,
            'videoBytes': config.review_video_mb * 1024 * 1024,
        }

    # ------------------------------------------------------ settings screen

    @api.model
    def _mart369_admin_settings_groups(self):
        groups = super()._mart369_admin_settings_groups()
        config = self._get()
        groups['reviews'] = {key: (config[field] if kind is not str else config[field] or '')
                             for key, (field, kind) in REVIEW_FIELDS.items()}
        return groups

    @api.model
    def _mart369_admin_save_group(self, group, values):
        if group != 'reviews':
            return super()._mart369_admin_save_group(group, values)
        vals = {}
        for key, (field, kind) in REVIEW_FIELDS.items():
            if key not in values:
                continue
            value = values[key]
            if kind is bool:
                vals[field] = bool(value)
            elif kind is str:
                vals[field] = (value or '').strip() or False
            else:
                try:
                    number = int(value)
                except (TypeError, ValueError):
                    raise UserError(_('That must be a whole number.'))
                if number < (0 if key == 'maxPhotos' else 1):
                    raise UserError(_('That must be more than zero.'))
                vals[field] = number
        if vals:
            self._get().write(vals)
        return True
