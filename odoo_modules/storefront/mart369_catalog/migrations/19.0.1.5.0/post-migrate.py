"""Tidy the grocery example out of a shop already installed.

* Its empty categories leave the app - the same step a fresh install takes in
  post_init_hook (see hide_sample_categories in __init__.py).
* The invented search counts `_mart369_load_demo` made ("milk" 34 times,
  "fresh paneer" 9) leave the staff's demand list. Only rows still holding
  exactly the invented numbers: one a real customer has since searched has
  real counts in it, and stays.
"""

import logging

from odoo import SUPERUSER_ID, api

from odoo.addons.mart369_catalog import hide_sample_categories

_logger = logging.getLogger(__name__)

INVENTED = {('milk', 34, 12), ('bread', 21, 8), ('phone charger', 12, 5),
            ('fresh paneer', 9, 0)}


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    hide_sample_categories(env)
    Term = env['mart369.search.term']
    gone = Term.search([('term', 'in', [t for t, __, __ in INVENTED])]).filtered(
        lambda r: (r.term, r.hits, r.results) in INVENTED)
    gone.unlink()
    _logger.info('mart369_catalog: removed %d invented search count(s)', len(gone))
