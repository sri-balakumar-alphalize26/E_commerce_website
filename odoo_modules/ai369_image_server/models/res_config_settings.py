from odoo import _, fields, models

from .imgsrv_client import Client, ImgSrvError, conf


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    imgsrv_enabled = fields.Boolean("Store images on the Image Server", config_parameter="ai369_image_server.enabled")
    imgsrv_url = fields.Char("Server URL", config_parameter="ai369_image_server.url", default="https://images.369ai.biz")
    # the key itself is never sent to the browser: only stars + last 4 characters
    imgsrv_api_key_masked = fields.Char("API key", compute="_compute_imgsrv_key_masked")
    imgsrv_api_key = fields.Char("New API key",
                                 help="Leave empty to keep the saved key. Type a new key only to change it.")
    imgsrv_upload_mode = fields.Selection(
        [("direct", "Browser → image server (fast, recommended)"), ("server", "Through the ERP server")],
        string="Upload pictures", config_parameter="ai369_image_server.upload_mode", default="direct",
        help="Browser → image server: the picture goes straight to the image server with a short-lived upload link; "
             "the ERP keeps only the link.")
    imgsrv_scope = fields.Selection(
        [("all", "All files of every app (images + documents, also apps installed later)"),
         ("images", "Images only (every app)"),
         ("products", "Product images only"),
         ("selected", "Only the models listed below (all their files)")],
        string="What to store", config_parameter="ai369_image_server.scope", default="all")
    imgsrv_public_models = fields.Char(
        "Public image models", config_parameter="ai369_image_server.public_models",
        default="product.template,product.product,product.image,res.partner,res.users,hr.employee,res.company",
        help="Images of these models get a public link. Every other file (cheques, documents, attachments, "
             "custom modules) is private: no public link, opened only through the ERP.")
    imgsrv_models = fields.Char("Models", config_parameter="ai369_image_server.models",
                                help="Comma separated technical names, e.g. product.template,hr.employee,res.partner")
    imgsrv_similar = fields.Selection(
        [("use_existing", "Use existing folder"),
         ("create_new", "Create new folder"),
         ("request", "Ask image server admin")],
        string="Similar folder names", config_parameter="ai369_image_server.similar", default="use_existing")
    imgsrv_brand_field = fields.Char("Brand field", config_parameter="ai369_image_server.brand_field", default="auto",
                                     help="Technical field on product.template used as the Brand folder. "
                                          "'auto' tries product_brand_id, brand_id, x_brand, x_studio_brand.")

    def _compute_imgsrv_key_masked(self):
        key = self.env["ir.config_parameter"].sudo().get_param("ai369_image_server.api_key") or ""
        for r in self:
            r.imgsrv_api_key_masked = ("*" * 12 + key[-4:]) if key else _("not set")

    def set_values(self):
        super().set_values()
        if self.env.user.has_group("base.group_system") and (self.imgsrv_api_key or "").strip():
            ICP = self.env["ir.config_parameter"].sudo()
            ICP.set_param("ai369_image_server.api_key", self.imgsrv_api_key.strip())
            ICP.set_param("ai369_image_server.db_folder", "")
            try:   # learn the database folder of the new key straight away
                ICP.set_param("ai369_image_server.db_folder", Client(conf(self.env)).me().get("media_db") or "")
            except ImgSrvError:
                pass

    def action_imgsrv_test(self):
        self.execute()   # save first
        c = conf(self.env)
        try:
            me = Client(c).me()
        except ImgSrvError as e:
            return self._imgsrv_note(str(e), "danger")
        perms = me.get("perms") or me.get("permissions") or {}
        role = me.get("role")
        ICP = self.env["ir.config_parameter"].sudo()
        # the image server decides the database folder of this connection; remember it
        ICP.set_param("ai369_image_server.db_folder", me.get("media_db") or "")
        who = me.get("connection") or me.get("username")
        if not (role == "admin" or "w" in str(perms.get("images", ""))):
            return self._imgsrv_note(_("Connected as %s, but this key cannot upload images.", who), "warning")
        if me.get("connection"):
            return self._imgsrv_note(_("Connected to %(url)s as connection “%(who)s” — images of this database go to "
                                       "%(url)s/%(db)s/…", url=c["url"], who=who, db=me.get("media_db")), "success")
        return self._imgsrv_note(_("Connected to %(url)s with the master key (%(user)s). Better: create an ERP "
                                   "connection for this database on the image server and use its key.",
                                   url=c["url"], user=who), "success")

    def action_imgsrv_migration(self):
        self.execute()
        return self.env["ir.actions.actions"]._for_xml_id("ai369_image_server.action_imgsrv_migration")

    def _imgsrv_note(self, message, kind):
        return {"type": "ir.actions.client", "tag": "display_notification",
                "params": {"title": _("Image Server"), "message": message, "type": kind, "sticky": kind != "success"}}
