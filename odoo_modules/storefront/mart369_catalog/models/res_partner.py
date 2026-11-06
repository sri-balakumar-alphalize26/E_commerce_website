"""A customer's own recent searches.

The app keeps these in localStorage under `369mart.searches`, so they are tied
to one browser and start life seeded with five searches nobody made. Held on the
partner instead, they follow the account to a phone and a laptop, and they start
empty because nothing has been searched yet.

Stored as JSON in a Char rather than a model of its own: it is a short list,
always read and written whole, and never queried across customers.
"""

import json

from odoo import fields, models

KEEP = 8  # the app shows at most this many


class ResPartner(models.Model):
    _inherit = 'res.partner'

    mart369_recent_searches = fields.Char(
        string='Recent searches', copy=False, groups='base.group_system',
        help="The last few things this customer searched for in the app, "
             "newest first. Cleared when they clear it in the app.")

    def _mart369_recent_list(self):
        self.ensure_one()
        try:
            found = json.loads(self.sudo().mart369_recent_searches or '[]')
        except ValueError:
            return []
        return [t for t in found if isinstance(t, str)][:KEEP]

    def _mart369_recent_add(self, term):
        """Newest first, no duplicates, capped. Returns the new list."""
        self.ensure_one()
        term = self.env['mart369.search.term']._mart369_clean(term)
        if not term:
            return self._mart369_recent_list()
        found = [t for t in self._mart369_recent_list() if t != term]
        found.insert(0, term)
        found = found[:KEEP]
        self.sudo().mart369_recent_searches = json.dumps(found)
        return found

    def _mart369_recent_clear(self):
        self.ensure_one()
        self.sudo().mart369_recent_searches = '[]'
        return []
