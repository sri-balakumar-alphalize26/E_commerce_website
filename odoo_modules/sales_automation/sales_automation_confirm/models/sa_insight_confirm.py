# -*- coding: utf-8 -*-
"""Clicks on the Insights profile: 'Opened / Accepted the product page'."""
from odoo import api, fields, models


def _iso(dt):
    return fields.Datetime.to_string(dt).replace(' ', 'T') + 'Z' if dt else ''


class SaInsightEntityConfirm(models.Model):
    _inherit = 'sa.insight.entity'

    @api.model
    def sa_insights_profile(self, kind, entity_id):
        data = super().sa_insights_profile(kind, entity_id)
        entity = self.sudo().browse(int(entity_id))
        if not entity.exists():
            return data
        requests = entity.request_ids
        if not requests:
            return data
        Click = self.env['sa.link.click'].sudo()
        clicks = Click.search([('request_id', 'in', requests.ids), ('kind', '=', kind)], order='at desc', limit=40)
        if not clicks:
            return data
        words = {'open': 'Opened the product page', 'accept': 'ACCEPTED on the product page',
                 'reject': 'REJECTED on the product page', 'again': 'Pressed again on a decided page'}
        extra = [{'at': _iso(c.at), 'kind': 'click',
                  'text': '%s (#%s, %s)' % (words.get(c.action, c.action), c.request_id.ref_code or '?', c.ip or 'no ip'),
                  'ref_id': c.request_id.id} for c in clicks]
        for key, cap in (('logs', 30), ('timeline', 12)):
            merged = list(data.get(key) or [])
            for e in extra:
                entry = dict(e)
                if key == 'logs':
                    entry['level'] = 'CLICK'
                    entry.pop('kind', None)
                merged.append(entry)
            merged.sort(key=lambda t: t.get('at') or '', reverse=True)
            data[key] = merged[:cap]
        return data
