# -*- coding: utf-8 -*-
"""What the AI already told us, so it is not asked twice.

The guided finder asks Gemini the same three questions for every customer who
types "headphone": which kinds exist, which brands make them, which models a
brand sells. The answers change over months, not minutes. Keeping them for a
week turns a dozen slow, metered calls into one, and lets the finder answer
instantly - and keep answering when the API is down.

Reference images are kept here too: they are the expensive call, and the same
model gets asked for many times.
"""

import base64
import json
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class SaAiSuggestion(models.Model):
    _name = 'sa.ai.suggestion'
    _description = 'Cached AI Suggestions'
    _order = 'id desc'
    _rec_name = 'seed'

    kind = fields.Selection([
        ('types', 'Product Types'),
        ('brands', 'Brands'),
        ('models', 'Models'),
        ('image', 'Reference Image'),
        # "Can a supplier price this as written?" - cached because the same
        # generic words come round again and again in a sales group.
        ('quotable', 'Quotable As Written'),
    ], required=True, index=True)
    seed = fields.Char(
        'Key', required=True, index=True,
        help="Normalised question, e.g. brands|headphone|wireless over-ear.")
    payload = fields.Text('Answer (JSON)')
    image = fields.Binary('Image', attachment=False)
    image_mimetype = fields.Char('Image Type')
    model_used = fields.Char('Model')
    expires_at = fields.Datetime('Expires', required=True, index=True)
    hits = fields.Integer('Reused', default=0)

    _kind_seed_uniq = models.Constraint(
        'UNIQUE(kind, seed)', 'One cache row per kind and seed.')

    # ------------------------------------------------------------------
    @api.model
    def _key(self, *parts):
        """One canonical key however the words were typed."""
        return '|'.join(' '.join((p or '').lower().split()) for p in parts)

    @api.model
    def _ttl_days(self):
        settings = self.env['sa.ai.settings'].sudo().get_settings()
        return max(1, getattr(settings, 'finder_cache_days', 7) or 7)

    @api.model
    def recall(self, kind, seed):
        """The cached answer, or None. Images come back as (bytes, mimetype)."""
        row = self.sudo().search([('kind', '=', kind), ('seed', '=', seed)],
                                 limit=1)
        if not row:
            return None
        if row.expires_at and row.expires_at < fields.Datetime.now():
            row.unlink()
            return None
        row.hits += 1
        if kind == 'image':
            if not row.image:
                return None
            return base64.b64decode(row.image), row.image_mimetype or 'image/jpeg'
        try:
            return json.loads(row.payload or 'null')
        except ValueError:
            row.unlink()
            return None

    @api.model
    def store(self, kind, seed, data=None, image=None, mimetype='image/jpeg',
              model_used=''):
        """Keep an answer. Replaces whatever was there for this key."""
        vals = {
            'kind': kind,
            'seed': seed,
            'model_used': model_used or '',
            'expires_at': fields.Datetime.add(fields.Datetime.now(),
                                              days=self._ttl_days()),
        }
        if kind == 'image':
            vals['image'] = base64.b64encode(image).decode() if image else False
            vals['image_mimetype'] = mimetype
        else:
            vals['payload'] = json.dumps(data, ensure_ascii=False)
        row = self.sudo().search([('kind', '=', kind), ('seed', '=', seed)],
                                 limit=1)
        if row:
            row.write(vals)
            return row
        return self.sudo().create(vals)

    @api.model
    def _cron_purge(self):
        gone = self.sudo().search([('expires_at', '<', fields.Datetime.now())])
        if gone:
            _logger.info("Sales Automation: purged %d expired AI suggestion(s)",
                         len(gone))
            gone.unlink()
        return True
