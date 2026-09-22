"""Moderation: the one field that decides whether a review is shown.

The field lives here rather than in `mart369_account`, which is where reviews
are *written*, because of who has to read it. `REVIEW_DOMAIN` below in
product_page.py and `RATING_DOMAIN` in mart369_catalog both filter on it, and
neither of those modules depends on `mart369_account` - the dependency runs the
other way round (account -> order -> cart -> catalog -> product). Defined up
there, the domains would reference a column that need not exist.

Nothing else about a review is here. `mart369_account` still owns the title,
the tags, the photo count and the writing.
"""

from odoo import fields, models


class RatingRating(models.Model):
    _inherit = 'rating.rating'

    mart369_state = fields.Selection(
        [('pending', 'Waiting'), ('published', 'Published'), ('hidden', 'Hidden')],
        string='Moderation', default='published', index=True,
        help="Whether the product page shows this review. New reviews are "
             "published straight away and the waiting list is read afterwards, "
             "so a page never goes quiet because nobody worked a queue.")
