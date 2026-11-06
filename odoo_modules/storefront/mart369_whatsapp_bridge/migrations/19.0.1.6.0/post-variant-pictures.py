"""The Variant images tab now draws Photographs: its pictures move to Extra Variant Media."""
from odoo import SUPERUSER_ID, api

from odoo.addons.mart369_whatsapp_bridge.hooks import copy_variant_pictures


def migrate(cr, version):
    copy_variant_pictures(api.Environment(cr, SUPERUSER_ID, {}))
