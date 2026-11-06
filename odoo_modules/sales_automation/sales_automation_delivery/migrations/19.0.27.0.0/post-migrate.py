# -*- coding: utf-8 -*-
"""Handover Address in words for jobs handed over before 19.0.27.0.0.

One reverse lookup per job (cached), a second apart for Nominatim's usage
policy, at most 100 jobs; the rest keep their "Look up address" button.
A failed lookup never stops the upgrade."""
import logging
import time

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    jobs = env['stock.picking'].search([
        ('sa_handover_lat', '!=', 0), ('sa_handover_lng', '!=', 0),
        ('sa_handover_address', '=', False),
    ], order='id desc', limit=100)
    done = 0
    for job in jobs:
        try:
            job._sa_fill_handover_address()
            done += bool(job.sa_handover_address)
        except Exception as err:  # noqa: BLE001
            _logger.info("Handover address for %s not looked up: %s", job.name, err)
        time.sleep(1)
    _logger.info("Handover address filled on %d of %d delivered jobs", done, len(jobs))
