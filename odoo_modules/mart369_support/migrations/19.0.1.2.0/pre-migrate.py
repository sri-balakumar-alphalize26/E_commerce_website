"""Protect what an operator has already typed, before the data file is read.

`data/bot_rules.xml` has just been wrapped in `noupdate="1"`, so the bot
answers, the two config parameters and the sequence are an operator's to keep.

Odoo decides whether to skip a record from the `noupdate` flag stored on its
`ir.model.data` row, not from the attribute in the file it is about to read. So
on a database where those rows still say false, the very upgrade that
introduces the declaration would overwrite one last time - landing on exactly
the person it is meant to protect. Setting the flag first, in a pre-migrate,
closes that window; a post-migrate would run after the damage.

**On the database this was written against the rows already said true**, set
when the module was first installed, so here it updates nothing and the
declaration in the XML only makes explicit what was already the case. It is
kept for the databases where that is not so, and because the guarantee should
live in the repository rather than in whatever happened to set those flags.

Scoped to this module's own xmlids so it cannot touch anything else.
"""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    # A raw string, and a single %: psycopg2 does no interpolation when there
    # are no parameters, so a doubled %% would be matched literally and this
    # would quietly update nothing. The backslash escapes the underscore, which
    # is a single-character wildcard in LIKE.
    cr.execute(r"""
        UPDATE ir_model_data
           SET noupdate = true
         WHERE module = 'mart369_support'
           AND noupdate = false
           AND (name LIKE 'rule\_%'
                OR name LIKE 'param\_%'
                OR name = 'seq_mart369_ticket')
    """)
    if cr.rowcount:
        _logger.info(
            '369 Mart: %s seeded support record(s) are now an operator\'s to '
            'keep', cr.rowcount)
