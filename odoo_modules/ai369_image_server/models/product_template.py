import base64
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .imgsrv_client import CACHE, PREFIX, PRODUCT_SIZES, Client, ImgSrvError, conf, is_marker_b64, version_of

_logger = logging.getLogger(__name__)
BRAND_FIELDS = ("product_brand_id", "brand_id", "x_brand", "x_studio_brand", "brand")
SIZE_FIELDS = list(PRODUCT_SIZES)
GALLERY_FIELDS = ("product_template_image_ids", "product_variant_image_ids")


def _onchange_needs_pictures(values):
    """A form refresh compares every picture on the form, which downloads each one
    from the image server. Their sizes do just as well, except for a real picture
    just put on an existing gallery row: website_sale measures it against the row's
    other sizes (a pasted link is only a marker, and is not measured)."""
    for name in GALLERY_FIELDS:
        for command in values.get(name) or []:
            if command[0] == 1:
                image = (command[2] or {}).get("image_1920")
                if image and not is_marker_b64(image):
                    return True
    return False


class ProductTemplate(models.Model):
    _inherit = "product.template"

    def onchange(self, values, field_names, fields_spec):
        records = self if _onchange_needs_pictures(values) else self.with_context(bin_size=True)
        return super(ProductTemplate, records).onchange(values, field_names, fields_spec)

    imgsrv_image_url = fields.Char("Image URL", compute="_compute_imgsrv")
    imgsrv_thumb_url = fields.Char("Thumbnail URL", compute="_compute_imgsrv")
    imgsrv_folder = fields.Char("Server folder", compute="_compute_imgsrv")
    imgsrv_status = fields.Selection(
        [("none", "No image"), ("local", "Stored in ERP"), ("remote", "On image server"),
         ("pending", "Waiting to upload"), ("error", "Upload failed")], compute="_compute_imgsrv",
        string="Image Server status")
    imgsrv_error = fields.Char("Image Server error", compute="_compute_imgsrv")
    imgsrv_gallery_urls = fields.Text("Gallery URLs", compute="_compute_imgsrv")

    # ------------------------------------------------------------------ naming
    @api.model
    def _imgsrv_brand_field(self, c=None):
        c = c or conf(self.env)
        name = c["brand_field"]
        if name and name != "auto":
            return name if name in self._fields else None
        return next((f for f in BRAND_FIELDS if f in self._fields), None)

    def _imgsrv_names(self, c=None):
        """(category, brand, model reference) used as the server folder."""
        self.ensure_one()
        c = c or conf(self.env)
        cat = self.categ_id.complete_name or ""
        brand = ""
        bf = self._imgsrv_brand_field(c)
        if bf:
            val = self[bf]
            brand = (val.display_name if isinstance(val, models.BaseModel) else val) or ""
        ref = self.default_code or self.product_variant_ids[:1].default_code or f"PT{self.id}"
        return cat, str(brand), ref

    # ------------------------------------------------------------------ display
    def _imgsrv_main_attachment(self):
        self.ensure_one()
        return self.env["ir.attachment"].sudo().search(
            [("res_model", "=", "product.template"), ("res_id", "=", self.id), ("res_field", "=", "image_1920")], limit=1)

    @api.depends("image_1920", "categ_id", "default_code")
    def _compute_imgsrv(self):
        Att = self.env["ir.attachment"].sudo()
        c = conf(self.env)
        atts = Att.search([("res_model", "=", "product.template"), ("res_id", "in", self.ids),
                           ("res_field", "=", "image_1920")]) if self.ids else Att
        by_id = {a.res_id: a for a in atts}
        gallery = {}
        if "product_template_image_ids" in self._fields and self.ids:
            imgs = self.env["product.image"].sudo().search([("product_tmpl_id", "in", self.ids)])
            tmpl_of = {i.id: i.product_tmpl_id.id for i in imgs}
            if imgs:
                for g in Att.search([("res_model", "=", "product.image"), ("res_id", "in", imgs.ids),
                                     ("res_field", "=", "image_1920"), ("imgsrv_url", "!=", False)], order="res_id"):
                    slot = (g.imgsrv_ref or "").split("|")[-1]
                    gallery.setdefault(tmpl_of[g.res_id], []).append((int(slot) if slot.isdigit() else 999, g.imgsrv_url))
        for t in self:
            a = by_id.get(t.id)
            remote = bool(a and a.store_fname and a.store_fname.startswith(PREFIX))
            t.imgsrv_image_url = a.imgsrv_url if remote else False
            t.imgsrv_thumb_url = a.imgsrv_thumb_url if remote else False
            ref = a.imgsrv_ref or "" if a else ""
            t.imgsrv_folder = ((ref.split("|", 1)[1].rsplit("/", 1)[0] + "  (linked)") if ref.startswith("link|")
                               else ref.split("|")[0]) if remote else False
            t.imgsrv_status = ("none" if not a else "remote" if remote else a.imgsrv_state or "local")
            t.imgsrv_error = (a.imgsrv_error or a._imgsrv_reason(c) or False) if a and not remote else False
            t.imgsrv_gallery_urls = "\n".join(u for _n, u in sorted(gallery.get(t.id, []))) or False

    # ------------------------------------------------------------------ moves (category / brand / reference changed)
    def write(self, vals):
        res = super().write(vals)
        c = None
        keys = {"categ_id", "default_code"}
        bf = self._imgsrv_brand_field()
        if bf:
            keys.add(bf)
        if keys & set(vals) and not self.env.context.get("imgsrv_skip"):
            c = conf(self.env)
            if c["enabled"]:
                data = self.env["ir.attachment"]._imgsrv_hook()
                data["ai369_imgsrv.moves"].update(self.ids)
        return res

    def _imgsrv_attachments(self):
        """All remote product image attachments of these templates (template + gallery)."""
        Att = self.env["ir.attachment"].sudo()
        dom = [("res_field", "in", SIZE_FIELDS), ("store_fname", "like", PREFIX + "p:%")]
        atts = Att.search(dom + [("res_model", "=", "product.template"), ("res_id", "in", self.ids)])
        if "product_template_image_ids" in self._fields:
            imgs = self.env["product.image"].sudo().search([("product_tmpl_id", "in", self.ids)])
            if imgs:
                atts |= Att.search(dom + [("res_model", "=", "product.image"), ("res_id", "in", imgs.ids)])
        return atts

    def _imgsrv_apply_moves(self):
        c = conf(self.env)
        if not c["enabled"]:
            return
        try:
            client = Client(c)
        except ImgSrvError:
            return
        for t in self:
            atts = t._imgsrv_attachments()
            folders = {(a.imgsrv_ref or "").split("|")[0] for a in atts} - {""}
            if not folders:
                continue
            cat, brand, ref = t._imgsrv_names(c)
            for folder in folders:
                parts = folder.split("/")
                if len(parts) != 4:
                    continue
                try:
                    res = client.move(parts[3], parts[1], parts[2], cat, brand, ref, c["similar"])
                except ImgSrvError as e:
                    _logger.warning("image server: could not move %s: %s", folder, e)
                    if hasattr(t, "message_post"):
                        t.message_post(body=_("Image server folder could not be renamed: %s", e))
                    continue
                if res["folder"] != folder:
                    t._imgsrv_relink(atts.filtered(lambda a: a.imgsrv_ref.split("|")[0] == folder), res)

    @api.model
    def _imgsrv_relink(self, atts, payload):
        """Point attachments at the folder described by a server folder payload."""
        entries = {"main": payload.get("main")}
        for g in payload.get("gallery") or []:
            entries[str(g["slot"])] = g
        for a in atts:
            slot = (a.imgsrv_ref or "|main").split("|")[1] or "main"
            e = entries.get(slot)
            if not e or not e.get("original"):
                continue
            size = PRODUCT_SIZES[a.res_field]
            fname = f"{PREFIX}p:{e['original']}?v={version_of(e['image'])}#{size}"
            old = CACHE.get(a.store_fname)
            if old:
                CACHE.put(fname, old)
            a._imgsrv_set(fname, e["image"] if size >= 512 else (e["thumb"] or e["image"]),
                          f"{payload['folder']}|{slot}", e["thumb"] or e["image"])

    # ------------------------------------------------------------------ buttons
    def action_imgsrv_send(self):
        """Upload now (also retries failed uploads)."""
        Att = self.env["ir.attachment"].sudo()
        atts = Att.search([("res_model", "=", "product.template"), ("res_id", "in", self.ids),
                           ("res_field", "in", SIZE_FIELDS)])
        if "product_template_image_ids" in self._fields:
            imgs = self.env["product.image"].sudo().search([("product_tmpl_id", "in", self.ids)])
            atts |= Att.search([("res_model", "=", "product.image"), ("res_id", "in", imgs.ids),
                                ("res_field", "in", SIZE_FIELDS)])
        variants = self.mapped("product_variant_ids")
        atts |= Att.search([("res_model", "=", "product.product"), ("res_id", "in", variants.ids),
                            ("res_field", "!=", False)])
        local = atts.filtered(lambda a: not a._imgsrv_is_remote())
        if not local:
            return self._imgsrv_notify(_("All images of this product are already on the image server."), "info")
        c = conf(self.env)
        reasons = {r for r in (a._imgsrv_reason(c) for a in local) if r}
        n = local._imgsrv_push(c)
        failed = local.filtered(lambda a: not a._imgsrv_is_remote())
        if not failed:
            return self._imgsrv_notify(_("%s image file(s) sent to the image server.", n), "success")
        why = "; ".join(sorted(reasons)) or "; ".join(sorted(set(failed.mapped("imgsrv_error")) - {False})) \
            or _("unknown reason — see Image Server › Image Files")
        return self._imgsrv_notify(_("%(n)s sent, %(f)s kept in the ERP: %(e)s", n=n, f=len(failed), e=why), "warning")

    def action_imgsrv_pull(self):
        """Load the main image (and gallery) that already exists in the server folder for this product."""
        c = conf(self.env)
        client = Client(c)
        Att = self.env["ir.attachment"].sudo()
        done, missing = 0, []

        def put(rec, raw, folder, slot, entry):
            rec.with_context(imgsrv_skip=True).image_1920 = base64.b64encode(raw)
            rec.flush_recordset()
            atts = Att.search([("res_model", "=", rec._name), ("res_id", "=", rec.id),
                               ("res_field", "in", SIZE_FIELDS)])
            link = {"folder": folder, "slot": slot, "original": entry["original"], "image": entry["image"],
                    "thumb": entry["thumb"] or entry["image"]}
            atts._imgsrv_push(c, link={(rec._name, rec.id): link})

        for t in self:
            cat, brand, ref = t._imgsrv_names(c)
            try:
                info = client.product_info(cat, brand, ref)
                if not info.get("main"):
                    missing.append(ref)
                    continue
                put(t, client.get_file(info["main"]["original"]), info["folder"], "main", info["main"])
                if "product_template_image_ids" in self._fields:
                    have = {(a.imgsrv_ref or "").split("|")[-1] for a in t._imgsrv_attachments()}
                    for g in info.get("gallery") or []:
                        if str(g["slot"]) in have or not g.get("original"):
                            continue
                        graw = client.get_file(g["original"])
                        img = self.env["product.image"].with_context(imgsrv_skip=True).create(
                            {"name": f"{t.name} {g['slot']}", "product_tmpl_id": t.id,
                             "image_1920": base64.b64encode(graw)})
                        put(img, graw, info["folder"], str(g["slot"]), g)
                done += 1
            except ImgSrvError as e:
                missing.append(f"{ref} ({e})")
        msg = _("%s product image(s) loaded from the image server.", done)
        if missing:
            msg += " " + _("Not found: %s", ", ".join(missing[:10]))
        return self._imgsrv_notify(msg, "success" if not missing else "warning")

    def _imgsrv_notify(self, message, kind="info"):
        return {"type": "ir.actions.client", "tag": "display_notification",
                "params": {"title": _("Image Server"), "message": message, "type": kind, "sticky": False,
                           "next": {"type": "ir.actions.client", "tag": "soft_reload"}}}


class ProductProduct(models.Model):
    """The variant form is built on the product form, so it carries the Image
    Server tab's buttons too; without these, validating any view that extends
    the variant form fails ("action_imgsrv_send is not a valid action")."""
    _inherit = "product.product"

    def onchange(self, values, field_names, fields_spec):
        records = self if _onchange_needs_pictures(values) else self.with_context(bin_size=True)
        return super(ProductProduct, records).onchange(values, field_names, fields_spec)

    def action_imgsrv_send(self):
        return self.product_tmpl_id.action_imgsrv_send()

    def action_imgsrv_pull(self):
        return self.product_tmpl_id.action_imgsrv_pull()
