"""Photos and a video on a review - and the votes other shoppers cast on it.

**Media.** Stored in Odoo's filestore as attachments, so the limits in
Settings > Reviews are checked here, on the server, before anything is saved:
how many, what type, how big, and for a video how long. A photo is re-encoded
to at most 1600 px on its longest side, which turns a 5 MB phone photo into a
few hundred kB. Every item waits for staff before shoppers see it; one that
staff remove is deleted outright, file and all, so it stops taking up disk.

**Votes.** "Helpful" and "Report", one of each per customer per review. Three
reports send a published review back to Waiting for staff to look at again.
"""

import base64
import binascii
import struct

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.image import image_process

PHOTO_TYPES = {'image/jpeg', 'image/png', 'image/webp'}
VIDEO_TYPES = {'video/mp4', 'video/webm', 'video/quicktime'}
REPORTS_TO_HOLD = 3
REPORT_REASONS = ['Offensive', 'Not about the product', 'Spam or advertising',
                  'Personal details', 'Fake review', 'Other']


def mp4_seconds(data):
    """Length of an MP4/MOV from its `mvhd` box, or None when it cannot be
    read (WebM, or a file that is not what it says) - the size cap still
    applies then."""
    at = data.find(b'mvhd')
    if at < 4 or at + 24 > len(data):
        return None
    version = data[at + 4]
    try:
        if version == 1:
            scale, length = struct.unpack('>IQ', data[at + 24:at + 36])
        else:
            scale, length = struct.unpack('>II', data[at + 16:at + 24])
    except struct.error:
        return None
    return length / scale if scale else None


class Mart369ReviewMedia(models.Model):
    _name = 'mart369.review.media'
    _description = '369 Mart review photo or video'
    _order = 'sequence, id'

    rating_id = fields.Many2one('rating.rating', required=True, index=True, ondelete='cascade')
    attachment_id = fields.Many2one('ir.attachment', required=True, ondelete='cascade')
    kind = fields.Selection([('photo', 'Photo'), ('video', 'Video')], required=True)
    state = fields.Selection([('pending', 'Waiting'), ('approved', 'Shown')],
                             default='pending', required=True, index=True)
    bytes = fields.Integer()
    seconds = fields.Float()
    sequence = fields.Integer(default=10)

    def unlink(self):
        """Removing an item removes its file: that is the point of removing it."""
        attachments = self.sudo().attachment_id
        res = super().unlink()
        attachments.exists().unlink()
        return res

    def _mart369_url(self, staff=False):
        self.ensure_one()
        return ('/369mart/admin/reviews/photo/%d' if staff else '/369mart/reviews/photo/%d') % self.id

    def _mart369_serialize(self, staff=False):
        self.ensure_one()
        return {'id': self.id, 'kind': self.kind, 'state': self.state,
                'url': self._mart369_url(staff), 'mime': self.attachment_id.mimetype or '',
                'bytes': self.bytes, 'seconds': round(self.seconds or 0, 1)}

    @api.model
    def _mart369_add(self, rating, name, mime, payload):
        """Check one upload against Settings > Reviews and store it."""
        limits = self.env['mart369.config']._mart369_review_limits()
        mime = (mime or '').lower()
        if isinstance(payload, str) and payload.startswith('data:'):
            payload = payload.split(',', 1)[-1]
        try:
            data = base64.b64decode(payload or '', validate=True)
        except (binascii.Error, ValueError):
            raise UserError(_('That file could not be read.'))
        if not data:
            raise UserError(_('That file is empty.'))
        existing = rating.sudo().mart369_media_ids

        if mime in PHOTO_TYPES:
            if len(existing.filtered(lambda m: m.kind == 'photo')) >= limits['maxPhotos']:
                raise UserError(_('Up to %s photos per review.', limits['maxPhotos']))
            if len(data) > limits['photoBytes']:
                raise UserError(_('A photo can be up to %s MB.', limits['photoBytes'] // (1024 * 1024)))
            try:
                data = image_process(data, size=(1600, 1600), quality=85)
            except Exception:  # noqa: BLE001 - not an image after all
                raise UserError(_('That photo could not be read.'))
            kind, seconds = 'photo', 0.0
        elif mime in VIDEO_TYPES:
            if not limits['video']:
                raise UserError(_('Videos are not accepted on reviews.'))
            if existing.filtered(lambda m: m.kind == 'video'):
                raise UserError(_('One video per review.'))
            if len(data) > limits['videoBytes']:
                raise UserError(_('A video can be up to %s MB.', limits['videoBytes'] // (1024 * 1024)))
            seconds = mp4_seconds(data) if mime != 'video/webm' else None
            if seconds is not None and seconds > limits['videoSeconds'] + 0.5:
                raise UserError(_('A video can be up to %s seconds.', limits['videoSeconds']))
            kind, seconds = 'video', seconds or 0.0
        else:
            raise UserError(_('Photos (JPG, PNG, WebP) and videos (MP4, WebM) only.'))

        attachment = self.env['ir.attachment'].sudo().create({
            'name': (name or kind)[:120],
            'datas': base64.b64encode(data),
            'mimetype': mime if kind == 'video' else 'image/jpeg' if mime == 'image/jpeg' else mime,
            'res_model': 'mart369.review.media',
            'type': 'binary',
        })
        media = self.sudo().create({
            'rating_id': rating.id, 'attachment_id': attachment.id, 'kind': kind,
            'bytes': len(data), 'seconds': seconds, 'sequence': len(existing) + 1,
        })
        attachment.res_id = media.id
        return media


class Mart369ReviewVote(models.Model):
    _name = 'mart369.review.vote'
    _description = '369 Mart review vote'

    rating_id = fields.Many2one('rating.rating', required=True, index=True, ondelete='cascade')
    partner_id = fields.Many2one('res.partner', required=True, index=True, ondelete='cascade')
    kind = fields.Selection([('helpful', 'Helpful'), ('report', 'Report')], required=True)
    reason = fields.Char()

    _one_each = models.Constraint(
        'unique (rating_id, partner_id, kind)', 'One vote of each kind per customer.')
