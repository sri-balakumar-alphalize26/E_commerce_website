"""Publish every review that existed before moderation did.

`mart369_state` is new. Odoo writes a new column's default into existing rows
as it adds it, so in the ordinary case there is nothing here to do - but the
cost of being wrong about that is the whole shop losing every review it has
ever been given, silently, because `REVIEW_DOMAIN` now asks for 'published'
and a NULL is not 'published'.

So this fills blanks and only blanks. A review staff had already hidden keeps
its state; a row Odoo already defaulted is left alone.
"""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute("""
        UPDATE rating_rating
           SET mart369_state = 'published'
         WHERE mart369_state IS NULL
    """)
    if cr.rowcount:
        _logger.info('369 Mart: published %s review(s) that predate moderation',
                     cr.rowcount)
