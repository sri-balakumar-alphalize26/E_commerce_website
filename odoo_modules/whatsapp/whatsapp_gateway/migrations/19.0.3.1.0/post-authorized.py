# -*- coding: utf-8 -*-
"""Read the authorized number and sender address from the panel once."""
import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for session in env['whatsapp.session'].search([('gateway_api_key', '!=', False)]):
        try:
            session._sync_mail_from()
        except Exception as err:  # noqa: BLE001 - the panel may be down during an upgrade
            _logger.info("whatsapp_gateway: %s not synced from the panel: %s", session.name, err)
