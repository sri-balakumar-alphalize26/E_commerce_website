from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..models.imgsrv_client import PREFIX, conf

P = "ai369_image_server.migration"


class ImgSrvMigration(models.TransientModel):
    _name = "ai369.imgsrv.migration"
    _description = "Move images to / from the Image Server"

    local_count = fields.Integer("Still stored in the ERP", compute="_compute_counts")
    remote_count = fields.Integer("On the image server", compute="_compute_counts")
    pending_count = fields.Integer("Waiting to upload (auto retry)", compute="_compute_counts")
    error_count = fields.Integer("Failed", compute="_compute_counts")
    local_mb = fields.Float("ERP storage used by these images (MB)", compute="_compute_counts", digits=(16, 1))
    running = fields.Selection([("move", "Moving to the image server"), ("back", "Bringing back to the ERP")],
                               compute="_compute_counts", string="Running in background")

    @api.depends_context("uid")
    def _compute_counts(self):
        Att = self.env["ir.attachment"].sudo()
        c = conf(self.env)
        dom = Att._imgsrv_scope_domain(c)
        local = dom + [("store_fname", "not like", PREFIX + "%")]
        for w in self:
            w.local_count = Att.search_count(local)
            w.remote_count = Att.search_count([("store_fname", "like", PREFIX + "%"), "|", ("res_field", "!=", False), ("res_field", "=", False)])
            w.pending_count = Att.search_count(local + [("imgsrv_state", "=", "pending")])
            w.error_count = Att.search_count(local + [("imgsrv_state", "=", "error")])
            groups = Att._read_group(local, [], ["file_size:sum"])
            w.local_mb = (groups[0][0] or 0) / 1048576 if groups else 0
            w.running = self.env["ir.config_parameter"].sudo().get_param(P) or False

    def _check(self):
        if not conf(self.env)["enabled"]:
            raise UserError(_("Turn on 'Store images on the Image Server' in Settings first."))

    def _reopen(self):
        return {"type": "ir.actions.act_window", "res_model": self._name, "view_mode": "form",
                "target": "new", "name": _("Image Server migration")}

    def action_move_batch(self):
        self._check()
        Att = self.env["ir.attachment"].sudo()
        c = conf(self.env)
        todo = Att.search(Att._imgsrv_scope_domain(c) + [("store_fname", "not like", PREFIX + "%"),
                                                         ("imgsrv_state", "=", False)], limit=50)
        todo._imgsrv_migrate(c)
        return self._reopen()

    def action_move_all(self):
        self._check()
        self.env["ir.config_parameter"].sudo().set_param(P, "move")
        self.env["ir.attachment"].sudo().search(["|", ("res_field", "!=", False), ("res_field", "=", False), ("imgsrv_state", "=", "error")]).write({"imgsrv_state": False})
        self.env.ref("ai369_image_server.ir_cron_imgsrv")._trigger()
        return self._reopen()

    def action_retry_failed(self):
        self._check()
        Att = self.env["ir.attachment"].sudo()
        Att.search(["|", ("res_field", "!=", False), ("res_field", "=", False), ("imgsrv_state", "in", ("error", "pending")),
                    ("store_fname", "not like", PREFIX + "%")], limit=200)._imgsrv_push()
        return self._reopen()

    def action_bring_back(self):
        ICP = self.env["ir.config_parameter"].sudo()
        ICP.set_param("ai369_image_server.enabled", "False")   # stop sending new images
        ICP.set_param(P, "back")
        self.env.ref("ai369_image_server.ir_cron_imgsrv")._trigger()
        return self._reopen()

    def action_stop(self):
        self.env["ir.config_parameter"].sudo().set_param(P, "")
        return self._reopen()

    def action_refresh(self):
        return self._reopen()
