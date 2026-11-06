import logging

from odoo import http
from odoo.http import request

import requests

from ..models.imgsrv_client import Client, ImgSrvError, conf, public_url, server_path

_logger = logging.getLogger(__name__)


class ImgSrvController(http.Controller):

    @http.route("/ai369_image_server/upload_ticket", type="jsonrpc", auth="user")
    def upload_ticket(self, count=1):
        """Short-lived upload links so the browser sends pictures straight to the image server."""
        env = request.env
        if not env.user._is_internal():
            return {"enabled": False}
        c = conf(env)
        if not (c["enabled"] and c["direct"]):
            return {"enabled": False}
        try:
            return {"enabled": True, "tickets": Client(c).tickets(min(int(count or 1), 20))}
        except ImgSrvError as e:
            _logger.info("image server: no upload link (%s), using normal upload", e)
            return {"enabled": False, "error": str(e)}

    @http.route("/ai369_image_server/image_url", type="jsonrpc", auth="user", readonly=True)
    def image_url(self, model, res_id, field):
        """Permanent image-server link of one image field (shown under every image box)."""
        env = request.env
        if model not in env or not res_id:
            return {}
        record = env[model].browse(int(res_id)).exists()
        if not record or field not in record._fields:
            return {}
        record.check_access("read")
        att = env["ir.binary"]._imgsrv_attachment(record, field)
        if not att:
            return {"status": "none"}
        if att.store_fname and att.store_fname.startswith("imgsrv:") and att.imgsrv_url:
            return {"status": "remote", "url": att.imgsrv_url.split("?")[0], "versioned": att.imgsrv_url,
                    "thumb": (att.imgsrv_thumb_url or "").split("?")[0],
                    "linked": (att.imgsrv_ref or "").startswith("link|")}
        if att.store_fname and att.store_fname.startswith("imgsrv:"):
            return {"status": "private", "path": att.imgsrv_ref}
        return {"status": att.imgsrv_state or "local", "error": att.imgsrv_error or ""}

    @http.route("/ai369_image_server/check_link", type="jsonrpc", auth="user")
    def check_link(self, url):
        """Is this URL an image on our image server? (used by 'Paste link' in the image box)"""
        c = conf(request.env)
        if not request.env.user._is_internal() or not c["enabled"]:
            return {"ok": False, "error": "Image server is not switched on (Settings › Image Server)."}
        url = (url or "").strip()
        path = server_path(c, url)
        if not path:
            return {"ok": False, "error": f"Paste a link of an image on {c['url']} (JPG, PNG, WEBP or GIF)."}
        pub = public_url(c, path)
        try:
            r = requests.head(pub, timeout=c["timeout"], allow_redirects=True)
        except requests.RequestException as e:
            return {"ok": False, "error": f"Image server not reachable ({e.__class__.__name__})."}
        if r.status_code != 200 or not (r.headers.get("content-type") or "").startswith("image/"):
            return {"ok": False, "error": f"No image at this link (status {r.status_code})."}
        return {"ok": True, "url": url.split("#")[0], "public": pub}
