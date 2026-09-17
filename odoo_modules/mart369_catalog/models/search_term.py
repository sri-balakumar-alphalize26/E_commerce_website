"""What people search for, so "Trending" can be true.

The app ships six frozen trending terms (`TRENDING` in SearchOverlay.jsx) that
are the same for every shopper on every day. One row per normalised term, with
a count and a last-seen date, is enough to replace them - and it doubles as the
list an operator reads to find out what the catalogue is missing.

Deliberately not linked to a customer: this is a counter, not a history. What
one person searched for is on their own partner record instead.
"""

from odoo import api, fields, models

# Terms this short are noise ("a", "ok"), and terms this long are a paste.
MIN_LEN = 2
MAX_LEN = 64


class Mart369SearchTerm(models.Model):
    _name = 'mart369.search.term'
    _description = '369 Mart Search Term'
    _order = 'hits desc, last_seen desc'
    _rec_name = 'term'

    term = fields.Char(string='Search', required=True, index=True, readonly=True)
    hits = fields.Integer(string='Searches', default=0, readonly=True)
    results = fields.Integer(
        string='Results last time', readonly=True,
        help="How many products the last search for this found. A popular "
             "term with zero results is a gap in the catalogue.")
    last_seen = fields.Datetime(string='Last searched', readonly=True)
    trending = fields.Boolean(
        string='Allow in Trending', default=True,
        help="Off: keep counting it, but never show it to shoppers as a "
             "suggestion. Use it for anything embarrassing or misspelt.")

    _term_uniq = models.Constraint(
        'unique (term)',
        'That search term is already counted.',
    )

    @api.model
    def _mart369_clean(self, term):
        """Fold case and whitespace so 'Dark  Chocolate' counts once."""
        term = ' '.join((term or '').split()).lower()
        return term if MIN_LEN <= len(term) <= MAX_LEN else ''

    @api.model
    def _mart369_record(self, term, results=0):
        """Count one search. Never raises - a failed count must not fail a
        search, which is the thing the customer actually asked for."""
        term = self._mart369_clean(term)
        if not term:
            return self.browse()
        try:
            existing = self.sudo().search([('term', '=', term)], limit=1)
            if existing:
                existing.write({
                    'hits': existing.hits + 1,
                    'results': results,
                    'last_seen': fields.Datetime.now(),
                })
                return existing
            return self.sudo().create({
                'term': term, 'hits': 1, 'results': results,
                'last_seen': fields.Datetime.now(),
            })
        except Exception:  # noqa: BLE001 - counting is best effort
            return self.browse()

    @api.model
    def _mart369_trending(self, limit=6):
        """The terms the app shows under "Trending", most searched first.

        Only terms that found something: suggesting a search that returns an
        empty page is worse than suggesting nothing.
        """
        terms = self.sudo().search(
            [('trending', '=', True), ('results', '>', 0)], limit=limit)
        return [t.term for t in terms]
