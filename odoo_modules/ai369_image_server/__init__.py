from odoo.exceptions import UserError

from . import controllers
from . import models
from . import wizard


def uninstall_hook(env):
    """Copy every image back into the ERP before the connector disappears, so nothing breaks."""
    Att = env["ir.attachment"].sudo()
    env["ir.config_parameter"].sudo().set_param("ai369_image_server.enabled", "False")
    ids = Att.with_context(active_test=False).search(
        ["|", ("res_field", "!=", False), ("res_field", "=", False), ("store_fname", "like", "imgsrv:%")]).ids
    for i in range(0, len(ids), 200):
        Att.browse(ids[i:i + 200])._imgsrv_bring_back()
    left = Att.search_count(["|", ("res_field", "!=", False), ("res_field", "=", False),
                             ("store_fname", "like", "imgsrv:%")])
    if left:
        raise UserError(f"{left} image(s) could not be copied back from the image server. "
                        "Check that the image server is online, then uninstall again.")
