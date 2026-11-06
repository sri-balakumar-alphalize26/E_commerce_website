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

    # ------------------------------------------------------- the staff screen

    # The tabs both front ends offer. 'popular' is not a domain but an order:
    # every term is popular relative to the ones below it, and a threshold
    # ("more than 5 searches") would be a number nobody chose.
    ADMIN_TABS = ('all', 'popular', 'empty', 'blocked')

    @api.model
    def mart369_admin_list(self, tab='all', q='', limit=200):
        """The rows and the tiles in one call, filtered on the server.

        One call rather than a list plus counts, for the reason the other
        desks give: the tiles are the tabs, and fetching them apart is how the
        two end up disagreeing between requests.

        Read by both the app console (over /369mart/admin/searches) and the
        backend desk (over the ORM), so the two cannot drift.
        """
        domain = []
        if tab == 'empty':
            domain = [('results', '=', 0)]
        elif tab == 'blocked':
            domain = [('trending', '=', False)]
        q = (q or '').strip()
        if q:
            domain = domain + [('term', 'ilike', q)]

        # 'popular' is the default order already; the others read better with
        # the most recent search first, because they are worked through rather
        # than ranked.
        order = 'hits desc, last_seen desc' if tab in ('all', 'popular') \
            else 'last_seen desc, hits desc'
        rows = self.search(domain, order=order, limit=limit)

        everything = self.search([])
        empty = everything.filtered(lambda t: not t.results)
        return {
            'rows': [row._mart369_admin_row() for row in rows],
            'counts': {
                'all': len(everything),
                'popular': len(everything),
                'empty': len(empty),
                'blocked': len(everything.filtered(lambda t: not t.trending)),
            },
            'tiles': {
                # Searches, not terms: one person typing "milk" forty times is
                # forty searches and one gap in the catalogue. Both numbers are
                # here because they answer different questions.
                'searches': sum(everything.mapped('hits')),
                'terms': len(everything),
                'empty': len(empty),
                # What those fruitless searches cost, in searches rather than
                # in terms - the number that says how often somebody went
                # looking and left with nothing.
                'empty_searches': sum(empty.mapped('hits')),
                'blocked': len(everything.filtered(lambda t: not t.trending)),
            },
        }

    def _mart369_admin_row(self):
        self.ensure_one()
        return {
            'id': self.id,
            'term': self.term or '',
            'hits': self.hits,
            'results': self.results,
            'trending': self.trending,
            # Epoch milliseconds, like every other admin payload: the screens
            # format dates themselves, and a naive string would be read as UTC
            # by the browser and printed hours early.
            'at': int(self.last_seen.timestamp() * 1000) if self.last_seen else None,
        }

    def mart369_admin_set_trending(self, trending):
        """Allow, or stop, this term appearing to shoppers as a suggestion.

        The only write either screen offers, and deliberately the only one:
        `term`, `hits`, `results` and `last_seen` are counts of things that
        really happened, and a staff member who could edit them could make the
        catalogue's gaps disappear by typing over them.

        Not sudo'd. A designer may write this because the ACL says so - see
        security/ir.model.access.csv - so Odoo's own rules do the refusing.
        """
        self.ensure_one()
        self.write({'trending': bool(trending)})
        return self._mart369_admin_row()

    # ------------------------------------------------------------ demo data

    @api.model
    def _mart369_load_demo(self):
        """A few searches to look at, on a shop where nobody has searched yet.

        Safe to invent, unlike anything on the payments or wallet screens:
        these are counts of searches, not money and not a claim about a named
        customer. One of them deliberately found nothing, because that row is
        the reason this screen exists and an operator should see what it looks
        like.

        Does nothing once a single real search has been counted, so a shop
        with traffic never has examples mixed into its demand list.
        """
        if self.search_count([]):
            return False
        now = fields.Datetime.now()
        self.create([
            {'term': 'milk', 'hits': 34, 'results': 12, 'last_seen': now},
            {'term': 'bread', 'hits': 21, 'results': 8, 'last_seen': now},
            {'term': 'phone charger', 'hits': 12, 'results': 5, 'last_seen': now},
            # The one that matters: somebody asked, the shop had nothing.
            {'term': 'fresh paneer', 'hits': 9, 'results': 0, 'last_seen': now},
        ])
        return True
