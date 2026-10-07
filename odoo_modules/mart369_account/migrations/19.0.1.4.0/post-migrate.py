"""Archive the example notices nobody has made their own.

Two sources of them: `_mart369_load_notice_demo` (names ending "[demo]"),
which no longer runs on install, and the grocery "Weekend grocery sale is
live" from data/account_data.xml, no longer installed. On the Dubai shop both
were showing customers a grocery sale and "Deliveries are running late
today".

Judged on the words, not on dates: a notice still tagged "[demo]", or still
saying exactly what was installed, is the example; one an operator reworded
is theirs, and stays. Archived rather than deleted either way.
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

GROCERY = ('Weekend grocery sale is live',
           'Up to 40% off on fresh picks. Ends Sunday midnight.')


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Notice = env['mart369.notice'].with_context(active_test=False)
    gone = Notice.search([('name', 'like', '[demo]'), ('active', '=', True)])
    grocery = env.ref('mart369_account.notice_weekend_sale', raise_if_not_found=False)
    if grocery and grocery.active and (grocery.name, grocery.text) == GROCERY:
        gone |= grocery
    gone.write({'active': False})
    _logger.info('mart369_account: archived %d example notice(s)', len(gone))
