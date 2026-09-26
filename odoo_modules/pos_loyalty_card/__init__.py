import os
from . import models
from . import wizard
from . import controllers


def _post_init_hook(env):
    """Auto-provision the Baileys WhatsApp helper in the BACKGROUND so module install
    returns immediately. A fresh machine needs a Node download + npm install that can
    otherwise exceed Odoo's request time limit; the health-check cron self-heals if the
    background run doesn't finish (e.g. no internet at install time)."""
    try:
        from .models import baileys_provision
        baileys_provision.provision_in_background()
    except Exception:
        pass
