"""Give an existing shop the permanent Demo page (models/home_starter.py)."""

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['mart369.home.version']._mart369_ensure_demo()
