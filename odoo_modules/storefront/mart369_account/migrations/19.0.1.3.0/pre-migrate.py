"""Protect what an operator has already typed, before the data file is read.

`data/account_data.xml` has just been wrapped in `noupdate="1"`. That is too
late for this upgrade on its own, and the reason is worth writing down:

Odoo decides whether to skip a record from the `noupdate` flag stored on its
`ir.model.data` row - not from the attribute in the file it is about to read.
Checked on the database this was written against, all four of those rows say
false, so without this the very upgrade that introduces the declaration would
overwrite one last time, landing on exactly the person it is meant to protect.

The referral reward is the one that matters. The admin console has a PATCH
route for it, so marketing is invited to change it, and every upgrade so far
has quietly put 100 back.

A pre-migrate rather than a post-migrate: the file is read between the two, so
a post-migrate would run after the damage.

Scoped to this module's own xmlids so it cannot touch anything else.
"""

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute("""
        UPDATE ir_model_data
           SET noupdate = true
         WHERE module = 'mart369_account'
           AND noupdate = false
           AND model IN ('ir.config_parameter', 'mart369.notice')
    """)
    if cr.rowcount:
        _logger.info(
            "369 Mart: %s seeded account record(s) are now an operator's to "
            "keep", cr.rowcount)
