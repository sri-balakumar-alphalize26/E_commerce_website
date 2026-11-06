"""Store image attachments on the 369ai image server.

store_fname formats (anything else is the normal local filestore):
    imgsrv:m:<media path>?v=<ver>[#<size>]        other images: media/<db>/<type>/<name>-<id>.<ext>  (public /<db>/<type>/...)
    imgsrv:p:<original path>?v=<ver>#<size>       product image: products/<category>/<brand>/<ref>/original.<ext>
One picture = one file on the server; the smaller ERP sizes link to it and are resized only when bytes are read.

Upload paths:
  * browser (default): the image box sends the file straight to the image server with a short-lived upload link and
    saves only a tiny marker; at commit the ERP asks the server to file it (no image bytes through the ERP);
  * server: anything else (imports, code, other apps) is pushed by the ERP in a pre-commit hook.
If the server can't be reached the image simply stays local (state "pending") and the cron retries.
"""
import base64
import logging

import requests
import hashlib
import hmac
from collections import defaultdict

from odoo import api, fields, models
from odoo.http import Stream
from odoo.tools.image import image_process

from .imgsrv_client import (CACHE, DOC_EXT, DOC_MAX_BYTES, EXCLUDED_MODELS, NAME_EXT, MAX_BYTES, MIME_EXT, PREFIX,
                            PRODUCT_SIZES, SIZE_FAMILIES, Client, ImgSrvError,
                            conf, in_scope, linked_url, marker_bytes, public_url, server_path, slug, staged_path, type_folder,
                            version_of)

_logger = logging.getLogger(__name__)
GALLERY_MODELS = ("product.image",)


def _parse(fname):
    """imgsrv:m:media/x.png?v=1  -> ('m', 'media/x.png', '1', None)
       imgsrv:p:products/a/b/c/original.png?v=1#256 -> ('p', 'products/a/b/c/original.png', '1', 256)"""
    kind, rest = fname[len(PREFIX):].split(":", 1)
    size = None
    if "#" in rest:
        rest, size = rest.rsplit("#", 1)
        size = int(size)
    path, _, ver = rest.partition("?v=")
    return kind, path, ver, size


class IrAttachment(models.Model):
    _inherit = "ir.attachment"

    imgsrv_state = fields.Selection(
        [("remote", "On image server"), ("pending", "Waiting to upload"), ("error", "Upload failed")],
        string="Image Server", index=True, copy=True, readonly=True)
    imgsrv_url = fields.Char("Image URL", copy=True, readonly=True)
    imgsrv_thumb_url = fields.Char("Thumbnail URL", copy=True, readonly=True)
    imgsrv_ref = fields.Char("Server path", copy=True, readonly=True,
                             help="media path, or 'products/<category>/<brand>/<ref>|<slot>' for product images")
    imgsrv_error = fields.Char("Last error", copy=False, readonly=True)

    # ------------------------------------------------------------------ helpers
    def _imgsrv_is_remote(self):
        return bool(self.store_fname and self.store_fname.startswith(PREFIX))

    @api.model
    def _imgsrv_scope_domain(self, c):
        """Files the connector handles: files of record fields (images, documents) and files attached to records."""
        dom = [("type", "=", "binary"), ("res_id", "!=", False), ("res_model", "!=", False), ("store_fname", "!=", False),
               ("url", "=", False), "|", ("res_field", "!=", False), ("public", "=", False)]
        if c["scope"] in ("images", "products"):
            dom += [("res_field", "!=", False), ("mimetype", "in", list(MIME_EXT))]
        if c["scope"] == "products":
            dom.append(("res_model", "in", ["product.template", "product.product", "product.image"]))
        elif c["scope"] == "selected":
            dom.append(("res_model", "in", c["models"] or ["-"]))
        else:
            dom.append(("res_model", "not in", list(EXCLUDED_MODELS)))
        return dom

    def _imgsrv_is_public(self, c):
        """Image of a record field of a 'public' model -> public link. Everything else is private."""
        self.ensure_one()
        st = self._imgsrv_staged()
        is_img = (st.rsplit(".", 1)[-1] in ("png", "jpg", "webp", "gif")) if st else self.mimetype in MIME_EXT
        return bool(self.res_field and is_img and self.res_model in c["public_models"])

    def _imgsrv_ext(self):
        st = self._imgsrv_staged()
        if st:
            return st.rsplit(".", 1)[-1]
        name_ext = (self.name or "").rsplit(".", 1)[-1].lower() if "." in (self.name or "") else ""
        if self.mimetype in MIME_EXT:
            return MIME_EXT[self.mimetype]
        if name_ext in NAME_EXT:
            return "jpg" if name_ext == "jpeg" else name_ext
        return DOC_EXT.get(self.mimetype)

    def _imgsrv_marker(self):
        """The tiny marker stored instead of a file (direct upload / pasted link), read as-is."""
        self.ensure_one()
        if not self.store_fname or self._imgsrv_is_remote() or (self.file_size or 0) > 800:
            return None
        try:
            return self.with_context(imgsrv_raw_marker=True)._file_read(self.store_fname)
        except Exception:
            return None

    def _imgsrv_staged(self):
        """Directly uploaded file waiting to be filed (tiny marker instead of the file)."""
        self.ensure_one()
        return staged_path(self._imgsrv_marker())

    def _imgsrv_reason(self, c):
        """Plain-language reason why this attachment is not sent (None = it can be sent)."""
        self.ensure_one()
        a = self.sudo()
        if not c["enabled"]:
            return "'Store images on the Image Server' is not ticked in Settings › Image Server"
        if not c["url"] or not c["key"]:
            return "server URL or API key missing in Settings › Image Server"
        if not in_scope(c, a.res_model):
            return f"'{a.res_model}' is not in 'What to store' (Settings › Image Server)"
        if a.type != "binary" or not a.store_fname or a.url:
            return "file is stored inside the database, not as a file"
        if not a.res_id:
            return "file is not attached to a record"
        if not a.res_field and a.public:
            return "public website file — kept in the ERP"
        if a._imgsrv_staged() or a._imgsrv_linked():
            return None
        if a.res_field and a.mimetype == "image/svg+xml":
            return "SVG pictures (default avatars) stay in the ERP"
        if c["scope"] in ("images", "products") and (not a.res_field or a.mimetype not in MIME_EXT):
            return "only images are stored on the image server ('What to store')"
        if a._imgsrv_is_public(c):
            if not 0 < (a.file_size or 0) <= MAX_BYTES:
                return f"image is {round((a.file_size or 0) / 1048576, 1)} MB (limit 12 MB)"
            return None
        if not a._imgsrv_ext():
            return f"file type {a.mimetype} is not supported"
        if not 0 < (a.file_size or 0) <= DOC_MAX_BYTES:
            return f"file is {round((a.file_size or 0) / 1048576, 1)} MB (limit 25 MB)"
        return None

    def _imgsrv_linked(self):
        """URL pasted in the image box (picture already on the image server, nothing to upload)."""
        self.ensure_one()
        return linked_url(self._imgsrv_marker())

    def _imgsrv_push_link(self, c, model, rid, siblings, main, url, session=requests):
        """Point the record's image (all sizes) at an existing image-server file; that file is never deleted by us.
        `session`: one connection shared by the pictures of a save (a new one costs about a second each)."""
        path = server_path(c, url)
        if not path:
            raise ImgSrvError("the link is not an image on " + c["url"], retry=False)
        pub = public_url(c, path)
        try:
            r = session.head(pub, timeout=c["timeout"], allow_redirects=True)
        except requests.RequestException as e:
            raise ImgSrvError(f"image server not reachable: {e.__class__.__name__}", retry=True)
        if r.status_code != 200:
            raise ImgSrvError(f"image not found on the image server ({r.status_code}): {pub}", retry=False)
        mime = (r.headers.get("content-type") or "").split(";")[0] or "image/webp"
        ver = version_of(url) if "?v=" in url else \
            hashlib.md5((r.headers.get("last-modified") or r.headers.get("etag") or "0").encode()).hexdigest()[:10]
        folder, name = path.rsplit("/", 1)
        stem, _dot, _ext = name.rpartition(".")
        if path.startswith("products/"):
            thumb_name = "thumb.webp" if stem == "main" else (f"thumb_{stem}.webp" if stem.isdigit() else name)
        else:
            thumb_name = f"{stem}_thumb.webp"
        thumb = public_url(c, f"{folder}/{thumb_name}")
        try:
            if session.head(thumb, timeout=c["timeout"]).status_code != 200:
                thumb = pub
        except requests.RequestException:
            thumb = pub
        meta = {"mimetype": mime, "file_size": int(r.headers.get("content-length") or 0) or None,
                "checksum": hashlib.sha1(f"{path}?{ver}".encode()).hexdigest()}
        owned = {a.imgsrv_ref for a in siblings if (a.imgsrv_ref or "").startswith("media/")}
        for a in siblings:
            size = SIZE_FAMILIES.get(a.res_field, (None, None))[1] or PRODUCT_SIZES.get(a.res_field)
            fname = f"{PREFIX}m:{path}?v={ver}" + (f"#{size}" if size else "")
            a._imgsrv_set(fname, pub if (not size or size >= 512) else thumb, "link|" + path, thumb, **meta)
        for o in owned:   # the record's own earlier upload is no longer used
            if not self.sudo().search_count([("imgsrv_ref", "=", o), ("res_field", "!=", False)]):
                try:
                    Client(c).delete_file(o)
                except ImgSrvError:
                    pass
        return len(siblings)

    def _imgsrv_candidates(self, c):
        out = self.browse()
        for a in self.sudo():
            if not a._imgsrv_is_remote() and a._imgsrv_reason(c) is None:
                out |= a
        return out

    def _imgsrv_set(self, fname, url, ref, thumb=False, state="remote", mimetype=None, file_size=None, checksum=None):
        """Point the attachment at the image server (bypasses ORM write: store_fname is not writable)."""
        self.ensure_one()
        self.flush_recordset()
        old = self.store_fname
        self.env.cr.execute(
            "UPDATE ir_attachment SET store_fname=%s, imgsrv_url=%s, imgsrv_thumb_url=%s, imgsrv_ref=%s,"
            " imgsrv_state=%s, imgsrv_error=NULL, mimetype=COALESCE(%s, mimetype), file_size=COALESCE(%s, file_size),"
            " checksum=COALESCE(%s, checksum), index_content=CASE WHEN %s IS NULL THEN index_content ELSE NULL END"
            " WHERE id=%s",
            (fname, url or None, thumb or url or None, ref, state, mimetype, file_size, checksum, mimetype, self.id))
        self.invalidate_recordset(["store_fname", "imgsrv_url", "imgsrv_thumb_url", "imgsrv_ref", "imgsrv_state",
                                   "imgsrv_error", "raw", "datas", "db_datas", "mimetype", "file_size", "checksum"])
        if old and not old.startswith(PREFIX):
            self._mark_for_gc(old)   # local copy is removed by the filestore garbage collector

    def _imgsrv_fail(self, err):
        state = "pending" if getattr(err, "retry", True) else "error"
        msg = str(err)[:250]
        self.flush_recordset()
        self.env.cr.execute("UPDATE ir_attachment SET imgsrv_state=%s, imgsrv_error=%s WHERE id IN %s",
                            (state, msg, tuple(self.ids)))
        self.invalidate_recordset(["imgsrv_state", "imgsrv_error"])
        _logger.info("image server: %s attachment(s) kept local (%s): %s", len(self), state, msg)

    # ------------------------------------------------------------------ push
    def _imgsrv_push(self, c=None, link=None):
        """Upload eligible attachments. Never raises: failures are recorded on the attachment."""
        c = c or conf(self.env)
        if not c["enabled"]:
            return 0
        todo = self._imgsrv_candidates(c).sorted("id")
        if not todo:
            return 0
        try:
            client = Client(c)
        except ImgSrvError as e:
            todo._imgsrv_fail(e)
            return 0
        groups = defaultdict(lambda: self.browse())
        for a in todo:
            if not a._imgsrv_linked() and not a._imgsrv_is_public(c):
                groups[("f", a.res_model, a.res_id, a.id)] |= a        # private file
                continue
            if a.res_model in ("product.template",) + GALLERY_MODELS and a.res_field in PRODUCT_SIZES:
                key = ("p", a.res_model, a.res_id, None)
            else:   # one picture of a record = one file; all its sizes link to it
                fam = SIZE_FAMILIES.get(a.res_field, (a.res_field, None))[0]
                key = ("m", a.res_model, a.res_id, fam)
            groups[key] |= a
        done = 0
        with requests.Session() as session:
            for (kind, model, rid, fam), atts in groups.items():
                try:
                    linked = atts.filtered(lambda x: x._imgsrv_linked())[:1]
                    if linked:                       # a link was pasted: nothing to upload, just point at that file
                        fields_ = list(PRODUCT_SIZES) if kind == "p" else (
                            [f"{fam}_{n}" for n in (1920, 1024, 512, 256, 128)] if fam in ("image", "image_variant")
                            else [linked.res_field])
                        sib = self.sudo().search([("res_model", "=", model), ("res_id", "=", rid),
                                                  ("res_field", "in", fields_)])
                        done += self._imgsrv_push_link(c, model, rid, sib, linked, linked._imgsrv_linked(), session)
                        continue
                    if kind == "f":
                        done += atts._imgsrv_push_private(client, c)
                    elif kind == "p":
                        done += self._imgsrv_push_product(client, c, model, rid, atts, (link or {}).get((model, rid)))
                    else:
                        done += self._imgsrv_push_media(client, c, model, rid, fam, atts)
                except ImgSrvError as e:
                    atts._imgsrv_fail(e)
                except Exception as e:  # never break the user's save
                    _logger.exception("image server push failed")
                    atts._imgsrv_fail(ImgSrvError(str(e), retry=True))
        return done

    def _imgsrv_push_private(self, client, c):
        """Private file: media/<server>/<module>[-files]/<yyyy>/<mm>/<record>-<id>-<field|name>.<ext>, no public link."""
        self.ensure_one()
        a = self.sudo()
        rec = self.env[a.res_model].sudo().browse(a.res_id).exists()
        folder = type_folder(a.res_model) + ("-files" if a.res_model in c["public_models"] else "")
        if a.res_field:
            tail = f"-{a.res_id}-" + slug(a.res_field, 40)
        else:
            stem = (a.name or "file").rsplit(".", 1)[0] if "." in (a.name or "") else (a.name or "file")
            tail = f"-{a.res_id}-" + slug(stem, 50) + f"-{a.id}"
        ext = a._imgsrv_ext()
        prefix = f"media/{c['db']}/{folder}/"
        prev = (a.imgsrv_ref or "").rsplit(".", 1)[0]
        if prev.startswith(prefix) and prev.endswith(tail):
            stem_path = prev                       # same record + field: replace in place
        else:
            d = a.create_date or fields.Datetime.now()
            stem_path = f"{prefix}{d:%Y}/{d:%m}/{slug(rec.display_name if rec else a.res_model, 40)}{tail}"
        old = a.imgsrv_ref if (a.imgsrv_ref or "").startswith("media/") else None
        staged = a._imgsrv_staged()
        if staged:
            res = client.adopt_media(staged, stem_path, private=True)
        else:
            raw = a.raw
            res = client.put_file(f"{stem_path}.{ext}", raw, a.mimetype or "application/octet-stream", private=True)
        path = res["path"]
        ver = res.get("version") or version_of(res.get("url") or "") or "0"
        fname = f"{PREFIX}f:{path}?v={ver}"
        if not staged:
            CACHE.put(fname, raw)
        meta = {}
        if staged:
            meta = {"mimetype": res.get("mimetype"), "file_size": res.get("size"),
                    "checksum": hashlib.sha1(f"{path}?{ver}".encode()).hexdigest()}
        a._imgsrv_set(fname, False, path, False, **meta)
        if old and old != path and not self.sudo().search_count([("imgsrv_ref", "=", old), ("id", "!=", a.id), "|", ("res_field", "!=", False), ("res_field", "=", False)]):
            try:
                client.delete_file(old)
            except ImgSrvError:
                pass
        return 1

    def _imgsrv_media_stem(self, c, model, rid, fam):
        """(prefix, tail, stem): media/<db>/<type>/<name>-<id>[-<field>]  (no extension)."""
        rec = self.env[model].sudo().browse(rid).exists()
        name = slug(rec.display_name if rec else model)
        tail = f"-{rid}" + ("" if fam == "image" else "-" + slug(fam.replace("image_", ""), 30))
        prefix = f"media/{c['db']}/{type_folder(model)}/"
        return prefix, tail, f"{prefix}{name}{tail}"

    def _imgsrv_push_media(self, client, c, model, rid, fam, changed):
        sized = fam in ("image", "image_variant")
        if sized:
            siblings = self.sudo().search([("res_model", "=", model), ("res_id", "=", rid),
                                           ("res_field", "in", [f"{fam}_{n}" for n in (1920, 1024, 512, 256, 128)])])
            main = siblings.sorted(lambda a: -SIZE_FAMILIES[a.res_field][1])[:1]
        else:
            siblings = main = changed[:1]
        if main._imgsrv_is_remote() and main not in changed:   # picture already on the server: link the sizes
            _k, path, ver, _s = _parse(main.store_fname)
            res = {"path": path, "url": main.imgsrv_url, "thumb": main.imgsrv_thumb_url}
            old, staged, raws = None, None, {a.id: a.raw for a in siblings if not a._imgsrv_is_remote()}
        else:
            staged = main._imgsrv_staged()
            raws = {} if staged else {a.id: a.raw for a in siblings if not a._imgsrv_is_remote()}
            prefix, tail, stem = self._imgsrv_media_stem(c, model, rid, fam)
            prev = (main.imgsrv_ref or "").rsplit(".", 1)[0]
            if prev.startswith(prefix) and prev.endswith(tail):
                stem = prev                               # same record: keep its file name (link stays stable)
            old = {a.imgsrv_ref for a in siblings if (a.imgsrv_ref or "").startswith("media/")}
            if staged:
                res = client.adopt_media(staged, stem)
            else:
                raw = raws.get(main.id) or main.raw
                res = client.put_file(f"{stem}.{MIME_EXT[main.mimetype]}", raw, main.mimetype)
            path = res["path"]
        ver = version_of(res["url"])
        meta = {}
        if staged:
            meta = {"mimetype": res.get("mimetype"), "file_size": res.get("size"),
                    "checksum": hashlib.sha1(f"{path}?{ver}".encode()).hexdigest()}
        n = 0
        for a in siblings:
            size = SIZE_FAMILIES[a.res_field][1] if sized else None
            fname = f"{PREFIX}m:{path}?v={ver}" + (f"#{size}" if size else "")
            if a.id in raws and (not size or size == 1920 or a == main):
                CACHE.put(fname, raws[a.id])
            url = res["url"] if (not size or size >= 512) else (res.get("thumb") or res["url"])
            a._imgsrv_set(fname, url, path, res.get("thumb") or res["url"], **meta)
            n += 1
        for o in (old or set()) - {path}:
            if not self.sudo().search_count([("imgsrv_ref", "=", o), ("res_field", "!=", False)]):
                try:
                    client.delete_file(o)
                except ImgSrvError:
                    pass
        return n

    def _imgsrv_push_product(self, client, c, model, rid, changed, link=None):
        rec = self.env[model].sudo().browse(rid).exists()
        tmpl = rec if model == "product.template" else (rec.product_tmpl_id or rec.product_variant_id.product_tmpl_id)
        siblings = self.sudo().search([("res_model", "=", model), ("res_id", "=", rid),
                                       ("res_field", "in", list(PRODUCT_SIZES))])
        main = siblings.filtered(lambda a: a.res_field == "image_1920")[:1]
        if not rec or not tmpl or not main:
            return self._imgsrv_push_media(client, c, model, rid, "image", changed)
        cat, brand, ref = tmpl._imgsrv_names(c)
        staged = main._imgsrv_staged() if not main._imgsrv_is_remote() else None
        raws = {} if staged else {a.id: a.raw for a in siblings if not a._imgsrv_is_remote()}
        meta, res = {}, None
        if link:                                         # image was pulled from the server: just link it
            folder, slot, original, url, thumb = (link["folder"], link["slot"], link["original"], link["image"],
                                                  link["thumb"])
        elif main in changed or not main._imgsrv_is_remote():
            slot = "main"
            if model in GALLERY_MODELS:
                prev = (main.imgsrv_ref or "").split("|")
                slot = prev[1] if len(prev) == 2 and prev[1] not in ("", "main") else "gallery"
            if staged:
                res = client.adopt_product(staged, cat, brand, ref, slot, c["similar"])
            else:
                res = client.upload_product(cat, brand, ref, slot, raws.get(main.id) or main.raw,
                                            main.name or f"{ref}.{MIME_EXT[main.mimetype]}", main.mimetype,
                                            c["similar"])
            folder, slot = res["folder"], res["uploaded_slot"]
            original = res["original"]
            entry = res["main"] if slot == "main" else next(g for g in res["gallery"] if g["slot"] == slot)
            url, thumb = entry["image"], entry["thumb"]
        else:                                           # main already on the server, only link the other sizes
            folder, slot = main.imgsrv_ref.split("|")
            _k, original, _v, _s = _parse(main.store_fname)
            url, thumb = main.imgsrv_url, main.imgsrv_thumb_url
        ver = version_of(url)
        if staged:
            ext = original.rsplit(".", 1)[-1].lower()
            meta = {"mimetype": {"jpg": "image/jpeg", "jpeg": "image/jpeg"}.get(ext, f"image/{ext}"),
                    "file_size": (res or {}).get("size"),
                    "checksum": hashlib.sha1(f"{original}?{ver}".encode()).hexdigest()}
        n = 0
        for a in siblings:
            size = PRODUCT_SIZES[a.res_field]
            fname = f"{PREFIX}p:{original}?v={ver}#{size}"
            if a.id in raws:
                CACHE.put(fname, raws[a.id])
            a._imgsrv_set(fname, url if size >= 512 else thumb, f"{folder}|{slot}", thumb, **meta)
            n += 1
        if res and res.get("width"):
            self._imgsrv_fix_zoom(rec, max(res["width"], res.get("height") or 0))
        return n

    @api.model
    def _imgsrv_fix_zoom(self, rec, longest):
        """Website zoom flag is computed from the picture; directly uploaded pictures report their size instead."""
        for f in ("can_image_1024_be_zoomed",):
            if f in rec._fields and rec._fields[f].store:
                self.env.cr.execute(f'UPDATE "{rec._table}" SET {f}=%s WHERE id=%s', (longest > 1024, rec.id))
                rec.invalidate_recordset([f])

    # ------------------------------------------------------------------ hooks
    @api.model
    def _imgsrv_hook(self):
        """Register (once per transaction) the pre-commit callback; returns the shared queue dict."""
        cr = self.env.cr
        data = cr.precommit.data
        if "ai369_imgsrv.ids" not in data:
            data["ai369_imgsrv.ids"] = set()
            data["ai369_imgsrv.link"] = {}
            data["ai369_imgsrv.moves"] = set()
            env = self.env

            @cr.precommit.add
            def _push():
                ids = data.pop("ai369_imgsrv.ids", set())
                link = data.pop("ai369_imgsrv.link", {})
                moves = data.pop("ai369_imgsrv.moves", set())
                if moves:
                    env["product.template"].sudo().browse(moves).exists()._imgsrv_apply_moves()
                if ids:
                    env["ir.attachment"].sudo().browse(ids).exists()._imgsrv_push(link=link)
        return data

    def _imgsrv_queue(self):
        """Push at the end of the transaction (record is complete, one upload per save)."""
        if self.env.context.get("imgsrv_skip") or not self:
            return
        data = self._imgsrv_hook()
        data["ai369_imgsrv.ids"].update(self.ids)
        if self.env.context.get("imgsrv_link"):
            data["ai369_imgsrv.link"].update(self.env.context["imgsrv_link"])

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records.filtered(lambda a: a.res_model and a.res_id and a.type == "binary")._imgsrv_queue()
        return records

    def write(self, vals):
        res = super().write(vals)
        if {"raw", "datas"} & set(vals):
            self.filtered(lambda a: a.res_model and a.res_id and a.type == "binary")._imgsrv_queue()
        return res

    def unlink(self):
        media = {a.imgsrv_ref for a in self.sudo() if a._imgsrv_is_remote() and (a.imgsrv_ref or "").startswith("media/")}
        res = super().unlink()
        if media:
            left = set(self.sudo().search([("imgsrv_ref", "in", list(media)), "|", ("res_field", "!=", False), ("res_field", "=", False)]).mapped("imgsrv_ref"))
            gone = media - left
            if gone:
                c = conf(self.env)

                @self.env.cr.postcommit.add
                def _delete_remote():
                    try:
                        client = Client(c)
                        for path in gone:
                            client.delete_file(path)
                    except ImgSrvError as e:
                        _logger.info("image server: could not delete %s: %s", gone, e)
        return res

    # ------------------------------------------------------------------ storage overrides
    @api.model
    def _file_read(self, fname, size=None):
        if fname and fname.startswith(PREFIX):
            data = self._imgsrv_read(fname)
            return data[:size] if size else data
        data = super()._file_read(fname, size)
        if data and data.startswith(b"<!--imgsrv-") and len(data) <= 800 and not size \
                and not self.env.context.get("imgsrv_raw_marker"):
            real = marker_bytes(self.env, data)     # not filed yet: give the real bytes (reports, exports)
            if real:
                return real
        return data

    @api.model
    def _file_delete(self, fname):
        if fname and fname.startswith(PREFIX):
            return   # remote files are cleaned up in unlink()
        return super()._file_delete(fname)

    @api.model
    def _imgsrv_read(self, fname):
        data = CACHE.get(fname)
        if data is not None:
            return data
        kind, path, _ver, size = _parse(fname)
        c = conf(self.env)
        try:
            # A public file (e.g. a pasted link) by its public address: under a
            # second, where the API takes about seven. The form reads several
            # on every gallery change.
            raw = self._imgsrv_read_public(c, path) if kind == "m" else None
            if raw is None:
                try:
                    raw = Client(c).get_file(path)
                except ImgSrvError:
                    if kind == "f" or (path.startswith("products/") and "/original" in path):
                        raise
                    r = requests.get(public_url(c, path), timeout=c["timeout"])
                    if r.status_code != 200:
                        raise ImgSrvError(f"{r.status_code}", retry=True)
                    raw = r.content
            if size and size < 1920 and kind != "f":
                raw = image_process(raw, size=(size, size))
        except ImgSrvError as e:
            _logger.warning("image server: cannot read %s: %s", path, e)
            return b""
        CACHE.put(fname, raw)
        return raw

    @api.model
    def _imgsrv_read_public(self, c, path):
        """The file at its public address, or None when it is not answered there as a picture."""
        try:
            r = requests.get(public_url(c, path), timeout=c["timeout"])
        except requests.RequestException:
            return None
        if r.status_code == 200 and (r.headers.get("content-type") or "").startswith("image/"):
            return r.content
        return None

    def _to_http_stream(self):
        if self._imgsrv_is_remote() and not self.imgsrv_url:      # private file: the ERP streams it
            data = self.raw or b""
            return Stream(type="data", data=data, size=len(data), mimetype=self.mimetype, download_name=self.name,
                          etag=self.checksum, public=self.public, last_modified=self.write_date)
        if self._imgsrv_is_remote() and self.imgsrv_url:
            return Stream(type="url", url=self.imgsrv_url, mimetype=self.mimetype, download_name=self.name,
                          etag=self.checksum, public=self.public, max_age=3600)
        return super()._to_http_stream()

    # ------------------------------------------------------------------ bring back / cron
    def _imgsrv_bring_back(self):
        """Copy images back into the local filestore (undo)."""
        done = 0
        for a in self.sudo().filtered(lambda x: x._imgsrv_is_remote()):
            raw = a._imgsrv_read(a.store_fname)
            if not raw:
                continue
            checksum = a._compute_checksum(raw)
            fname = a._file_write(raw, checksum)
            a.flush_recordset()
            self.env.cr.execute(
                "UPDATE ir_attachment SET store_fname=%s, checksum=%s, file_size=%s, imgsrv_state=NULL,"
                " imgsrv_url=NULL, imgsrv_thumb_url=NULL, imgsrv_error=NULL WHERE id=%s",
                (fname, checksum, len(raw), a.id))
            a.invalidate_recordset()
            done += 1
        return done

    @api.model
    def _imgsrv_local_count(self):
        c = conf(self.env)
        return self.sudo().search_count(self._imgsrv_scope_domain(c) + [("store_fname", "not like", PREFIX + "%")])

    def _imgsrv_migrate(self, c):
        """Move a batch; files that can't go (type, size…) are marked with the reason so the batch moves on."""
        n = self._imgsrv_push(c)
        for a in self.exists().filtered(lambda x: not x._imgsrv_is_remote() and not x.imgsrv_state):
            a._imgsrv_fail(ImgSrvError(a._imgsrv_reason(c) or "not handled", retry=False))
        return n

    @api.model
    def _cron_imgsrv(self, batch=300):
        c = conf(self.env)
        ICP = self.env["ir.config_parameter"].sudo()
        Att = self.sudo()
        mode = ICP.get_param("ai369_image_server.migration")
        if not c["enabled"] and mode != "back":
            return
        # 1. retry images that could not be uploaded
        if c["enabled"]:
            Att.search(["|", ("res_field", "!=", False), ("res_field", "=", False), ("imgsrv_state", "=", "pending"), ("store_fname", "not like", PREFIX + "%")],
                       limit=batch)._imgsrv_push(c)
            self.env.cr.commit()
        # 2. background move / bring back started from the wizard
        if mode == "move":
            todo = Att.search(self._imgsrv_scope_domain(c) + [("store_fname", "not like", PREFIX + "%"),
                                                              ("imgsrv_state", "=", False)], limit=batch)
            for chunk in [todo[i:i + 50] for i in range(0, len(todo), 50)]:
                chunk._imgsrv_migrate(c)
                self.env.cr.commit()
            if len(todo) < batch:
                ICP.set_param("ai369_image_server.migration", "")
            else:
                self.env.ref("ai369_image_server.ir_cron_imgsrv")._trigger()
        elif mode == "back":
            todo = Att.search([("store_fname", "like", PREFIX + "%"), "|", ("res_field", "!=", False), ("res_field", "=", False)], limit=batch)
            todo._imgsrv_bring_back()
            self.env.cr.commit()
            if len(todo) < batch:
                ICP.set_param("ai369_image_server.migration", "")
                ICP.set_param("ai369_image_server.enabled", "False")
            else:
                self.env.ref("ai369_image_server.ir_cron_imgsrv")._trigger()
