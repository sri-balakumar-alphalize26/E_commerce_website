"""1.1.0: our role replaces Odoo's User / Administrator line.

Owner now carries Odoo's Administrator right, so every existing Administrator
has to become Owner - otherwise the form would show them as a plain "User"
and the first person to save it would take their admin away.
"""

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    from odoo.addons.mart369_roles import _mart369_give_roles
    _mart369_give_roles(api.Environment(cr, SUPERUSER_ID, {}))
