"""Switch off the bot's "[demo]" answers.

`_mart369_load_bot_demo` no longer runs on install. Its two answers ("Opening
hours [demo]", "Bulk orders [demo]") told customers hours the shop never set.
Switched off, not deleted - the console's Off tab still lists them.
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    gone = env['mart369.bot.rule'].search([('title', 'like', '[demo]'), ('active', '=', True)])
    gone.write({'active': False})
    _logger.info('mart369_support: switched off %d example bot answer(s)', len(gone))
