# -*- coding: utf-8 -*-
"""Settings rows created on the reference Windows box carry that PC's Python and browser
paths. On any other machine they cannot be right: fall back to Odoo's own Python and
Playwright's default folder."""
import os
import sys

from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    # The browser search and these settings were removed in 19.0.2.9.0.
    if 'confirm_browser_python' not in env['sa.ai.settings']._fields:
        return
    for rec in env['sa.ai.settings'].search([]):
        vals = {}
        py = rec.confirm_browser_python or ''
        if not py or not os.path.exists(py):
            vals['confirm_browser_python'] = sys.executable
        br = rec.confirm_browsers_path or ''
        if br and not os.path.isdir(br):
            vals['confirm_browsers_path'] = ''
        if vals:
            rec.write(vals)
