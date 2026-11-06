"""Give every existing tab the words the app used to have written into it.

`label`, `icon` and `tagline` are new. Left empty they fall back to the same
defaults in `_copy_vals()`, so the shop reads identically either way - but
writing them out means the first person to open the editor sees the real
wording in the fields instead of empty boxes, and can edit it rather than
having to guess what it currently says.

Only blanks are filled. Anything already set was set on purpose.
"""

import logging

_logger = logging.getLogger(__name__)

COPY = {
    'quick': ('Quick', 'bolt', 'Parts & peripherals in minutes'),
    'all': ('Express', 'grid', 'Electronics, home & more · 2–5 day delivery'),
}


def migrate(cr, version):
    filled = 0
    for key, (label, icon, tagline) in COPY.items():
        cr.execute(
            """
            UPDATE mart369_home_mode
               SET label = COALESCE(NULLIF(label, ''), %s),
                   icon = COALESCE(NULLIF(icon, ''), %s),
                   tagline = COALESCE(NULLIF(tagline, ''), %s)
             WHERE key = %s
               AND (label IS NULL OR label = ''
                    OR icon IS NULL OR icon = ''
                    OR tagline IS NULL OR tagline = '')
            """,
            (label, icon, tagline, key),
        )
        filled += cr.rowcount
        # The field briefly shipped with `default='grid'`, which Odoo wrote
        # into every row as it created the column - including Quick, whose
        # icon has always been a lightning bolt. On this one upgrade a 'grid'
        # on Quick can only have come from that default, never from a choice.
        cr.execute(
            """
            UPDATE mart369_home_mode
               SET icon = %s
             WHERE key = %s AND icon = 'grid' AND %s <> 'grid'
            """,
            (icon, key, icon),
        )
        filled += cr.rowcount
    if filled:
        _logger.info('369 Mart: filled the wording on %s tab(s)', filled)
