"""The website's delivery settings move into the senior's, once.

Where `sales_automation_quick_express` is installed, the website now reads and
writes his service areas, fee rules, slots and delivery shops (qe_link.py).
What a shop had set up on the website side - areas, the two fees, slots,
each warehouse's pin and Quick reach, products' own delivery texts - is
copied across first, so nothing is lost. Elsewhere this does nothing.
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    done = env['mart369.delivery.rule']._mart369_qe_copy_across()
    _logger.info('bridge: delivery settings copied into Quick / Express: %s', done)
