import logging

from . import models
from . import wizards

_logger = logging.getLogger(__name__)


# Imported rather than copied: whatsapp_gateway is a hard dependency, so it is
# always importable here, and one definition cannot drift from the other.
from odoo.addons.whatsapp_gateway import _link_whatsapp_groups


def _post_init_hook(env):
    """File this module's groups under its app for this Odoo 19 build."""
    _link_whatsapp_groups(env, 'whatsapp_email')
