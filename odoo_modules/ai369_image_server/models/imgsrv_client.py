"""Small HTTP client for the 369ai image server + an in-process byte cache."""
import base64
import logging
import re
import unicodedata
import threading
from collections import OrderedDict
from urllib.parse import parse_qs, quote, urlsplit

import requests

_logger = logging.getLogger(__name__)

P = "ai369_image_server."
PREFIX = "imgsrv:"
MIME_EXT = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp", "image/gif": "gif"}
PRODUCT_SIZES = {"image_1920": 1920, "image_1024": 1024, "image_512": 512, "image_256": 256, "image_128": 128}
PRODUCT_MODELS = ("product.template", "product.product", "product.image")
# technical images that must stay inside the ERP
# (icons shipped inside apps are re-loaded on every app update, so they stay in the ERP)
EXCLUDED_MODELS = {"ir.ui.menu", "ir.module.module", "ir.module.category", "res.lang", "ir.attachment", "ir.ui.view",
                   "mail.compose.message", "base.document.layout", "ir.cron", "bus.bus", "ir.qweb",
                   "spreadsheet.dashboard", "spreadsheet.dashboard.share", "website", "theme.ir.attachment",
                   "ir.actions.report", "ir.ui.view", "web_editor.converter.test", "html_editor.converter.test",
                   "payment.method", "payment.provider", "onboarding.onboarding.step", "res.country",
                   "res.currency", "mail.guest"}
MAX_BYTES = 12 * 1024 * 1024
DOC_MAX_BYTES = 25 * 1024 * 1024
# file types the image server accepts for private files (documents, scans…)
DOC_EXT = {"application/pdf": "pdf", "application/msword": "doc", "application/vnd.ms-excel": "xls",
           "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
           "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
           "application/vnd.ms-powerpoint": "ppt", "application/vnd.oasis.opendocument.text": "odt",
           "application/vnd.oasis.opendocument.spreadsheet": "ods", "text/csv": "csv", "text/plain": "txt",
           "application/xml": "xml", "text/xml": "xml", "application/json": "json", "application/zip": "zip",
           "application/x-zip-compressed": "zip", "application/vnd.rar": "rar", "application/x-7z-compressed": "7z",
           "message/rfc822": "eml", "image/tiff": "tif", "image/bmp": "bmp", "image/heic": "heic",
           "image/svg+xml": "svg", "video/mp4": "mp4", "audio/mpeg": "mp3", "audio/wav": "wav", "audio/ogg": "ogg"}
NAME_EXT = {"pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "odt", "ods", "csv", "txt", "xml", "json", "zip", "rar",
            "7z", "eml", "msg", "tif", "tiff", "bmp", "heic", "svg", "mp4", "mp3", "wav", "ogg", "dwg",
            "png", "jpg", "jpeg", "webp", "gif"}
# images of these models get a public link; every other file is private (no public link, opened through the ERP)
DEFAULT_PUBLIC = "product.template,product.product,product.image,res.partner,res.users,hr.employee,res.company"

# Direct browser upload: the field value is a tiny marker pointing at the file the browser already sent
MARKER = b"<!--imgsrv-staged:"
MARKER_B64 = base64.b64encode(MARKER).decode()          # "PCEtLWltZ3Nydi1zdGFnZWQ6"
STAGED_RE = re.compile(r"media/_incoming/[0-9a-f]{24}\.[a-z0-9]{1,5}")

# image sizes kept by the ERP for one picture: stored once on the server, the smaller sizes are links to it
SIZE_FAMILIES = {f"{fam}_{n}": (fam, n) for fam in ("image", "image_variant") for n in (1920, 1024, 512, 256, 128)}

# readable folder per model: <db>/<folder>/<name>-<id>.<ext>
TYPE_FOLDERS = {"res.partner": "contacts", "res.users": "users", "hr.employee": "employees",
                "res.company": "companies", "product.product": "product-variants", "product.template": "products",
                "product.image": "product-images", "hr.applicant": "applicants", "fleet.vehicle": "vehicles",
                "fleet.vehicle.model": "vehicle-models", "fleet.vehicle.model.brand": "vehicle-brands",
                "website": "website", "pos.category": "pos-categories", "product.category": "product-categories"}


LINK_MARKER = b"<!--imgsrv-linked:"                       # image already on the server, linked by its URL


def linked_url(raw):
    if not raw or not raw.startswith(LINK_MARKER):
        return None
    u = raw[len(LINK_MARKER):].split(b"-->")[0].decode(errors="ignore").strip()
    return u if re.fullmatch(r"https?://[^\s<>\"']+", u) else None


def is_marker_b64(value):
    """Field value is one of our small markers (direct upload or pasted link), not a picture."""
    if isinstance(value, bytes):
        value = value.decode(errors="ignore")
    if not isinstance(value, str) or not value.startswith("PCEtLWltZ3Nydi"):
        return False
    try:
        return base64.b64decode(value[:24]).startswith(b"<!--imgsrv-")
    except ValueError:
        return False


def server_path(c, url):
    """https://images.369ai.biz/danat/contacts/x.jpg?v=1 -> media/danat/contacts/x.jpg ; products/... stays."""
    base = c["url"].rstrip("/") + "/"
    if not url or not url.startswith(base):
        return None
    p = url[len(base):].split("?")[0].split("#")[0].strip("/")
    if not p or ".." in p.split("/") or not re.search(r"\.(png|jpe?g|webp|gif)$", p, re.I):
        return None
    return p if p.split("/")[0] in ("products", "brands", "categories", "media") else "media/" + p


def public_url(c, path):
    return c["url"].rstrip("/") + "/" + (path[6:] if path.startswith("media/") else path)


def staged_path(raw):
    """Path of a directly uploaded file if `raw` is a staged marker, else None."""
    if not raw or not raw.startswith(MARKER):
        return None
    p = raw[len(MARKER):].split(b"-->")[0].decode(errors="ignore")
    return p if STAGED_RE.fullmatch(p) else None


def is_staged_b64(value):
    if isinstance(value, bytes):
        value = value.decode(errors="ignore")
    return isinstance(value, str) and value.startswith(MARKER_B64)


def type_folder(model):
    return TYPE_FOLDERS.get(model) or model.replace(".", "-")


def slug(text, size=40):
    v = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode()
    v = re.sub(r"[^a-zA-Z0-9]+", "-", v).strip("-").lower()[:size].strip("-")
    return v or "item"


class ImgSrvError(Exception):
    def __init__(self, message, retry=True, similar=None):
        super().__init__(message)
        self.retry, self.similar = retry, similar


def conf(env):
    get = env["ir.config_parameter"].sudo().get_param
    models = [m.strip() for m in (get(P + "models") or "").split(",") if m.strip()]
    return {
        "enabled": get(P + "enabled") == "True",
        "url": (get(P + "url") or "").rstrip("/"),
        "key": get(P + "api_key") or "",
        "scope": get(P + "scope") or "all",
        "public_models": [m.strip() for m in (get(P + "public_models") or DEFAULT_PUBLIC).split(",") if m.strip()],
        "models": models,
        "similar": get(P + "similar") or "use_existing",
        "brand_field": (get(P + "brand_field") or "auto").strip() or "auto",
        "timeout": int(get(P + "timeout") or 20),
        "direct": (get(P + "upload_mode") or "direct") != "server",
        # folder given by the image server for this connection's key, else the database name
        "db": get(P + "db_folder") or re.sub(r"[^A-Za-z0-9_-]+", "-", env.cr.dbname).strip("-") or "db",
    }


def in_scope(c, model):
    if not model or model in EXCLUDED_MODELS:
        return False
    if c["scope"] == "products":
        return model in PRODUCT_MODELS
    if c["scope"] == "selected":
        return model in c["models"]
    return True


def version_of(url):
    try:
        return (parse_qs(urlsplit(url).query).get("v") or ["0"])[0]
    except Exception:
        return "0"


class Client:
    def __init__(self, c):
        if not c["url"] or not c["key"]:
            raise ImgSrvError("image server URL / API key not set", retry=False)
        self.base, self.key, self.timeout = c["url"], c["key"], c["timeout"]

    def _req(self, method, path, **kw):
        headers = {"X-API-Key": self.key, **kw.pop("headers", {})}
        try:
            r = requests.request(method, self.base + path, headers=headers, timeout=self.timeout, **kw)
        except requests.RequestException as e:
            raise ImgSrvError(f"image server not reachable: {e.__class__.__name__}", retry=True)
        if r.status_code < 400:
            return r
        try:
            j = r.json()
            detail = j.get("detail") if isinstance(j.get("detail"), str) else str(j)
        except ValueError:
            j, detail = {}, r.text[:200]
        if r.status_code == 401:
            raise ImgSrvError(f"image server refused the API key: {detail}", retry=False)
        if r.status_code == 403:
            raise ImgSrvError(f"not allowed by the image server: {detail}", retry=False)
        if r.status_code == 409:   # similar name waiting for approval / folder busy -> retry later
            raise ImgSrvError(detail, retry=True, similar=j.get("similar"))
        raise ImgSrvError(detail, retry=r.status_code >= 500)

    def me(self):
        return self._req("GET", "/api/me").json()

    def put_file(self, path, data, mimetype, private=False):
        return self._req("PUT", "/api/files/" + quote(path), data=data, params={"private": "true"} if private else None,
                         headers={"Content-Type": mimetype}).json()

    def get_file(self, path):
        return self._req("GET", "/api/files/" + quote(path)).content

    def delete_file(self, path):
        return self._req("DELETE", "/api/files/" + quote(path)).json()

    def tickets(self, count=1):
        return self._req("POST", "/api/upload-tickets", json={"count": count}).json()["tickets"]

    def adopt_media(self, src, dest, private=False):
        return self._req("POST", "/api/files/adopt", json={"src": src, "dest": dest, "private": private}).json()

    def adopt_product(self, src, category, brand, ref, slot, on_similar):
        return self._req("POST", "/api/files/adopt", json={
            "src": src, "category": category, "brand": brand, "ref": ref, "slot": str(slot),
            "on_similar": on_similar}).json()

    def upload_product(self, category, brand, ref, slot, data, filename, mimetype, on_similar):
        return self._req("POST", "/api/products/upload",
                         data={"category": category, "brand": brand, "ref": ref, "slot": str(slot), "on_similar": on_similar},
                         files={"file": (filename, data, mimetype)}).json()

    def product_info(self, category, brand, ref):
        return self._req("GET", "/api/products/info", params={"category": category, "brand": brand, "ref": ref}).json()

    def move(self, ref, from_category, from_brand, to_category, to_brand, to_ref, on_similar):
        return self._req("POST", "/api/products/move", json={
            "ref": ref, "from_category": from_category, "from_brand": from_brand,
            "to_category": to_category, "to_brand": to_brand, "to_ref": to_ref, "on_similar": on_similar}).json()


class ByteCache:
    """Per-worker LRU cache of image bytes read back from the server (reports, resizes)."""

    def __init__(self, max_bytes=64 * 1024 * 1024):
        self.max, self.size, self.data, self.lock = max_bytes, 0, OrderedDict(), threading.Lock()

    def get(self, key):
        with self.lock:
            v = self.data.get(key)
            if v is not None:
                self.data.move_to_end(key)
            return v

    def put(self, key, value):
        if not value or len(value) > self.max // 4:
            return
        with self.lock:
            if key in self.data:
                self.size -= len(self.data.pop(key))
            self.data[key] = value
            self.size += len(value)
            while self.size > self.max and self.data:
                self.size -= len(self.data.popitem(last=False)[1])


CACHE = ByteCache()


def marker_target(raw):
    """('link', url) / ('staged', path) for our small markers, else None."""
    if isinstance(raw, str):
        raw = raw.encode()
    if not raw or not raw.startswith(b"<!--imgsrv-") or len(raw) > 800:
        return None
    u = linked_url(raw)
    if u:
        return ("link", u)
    p = staged_path(raw)
    return ("staged", p) if p else None


def marker_bytes(env, raw):
    """Real file bytes behind a marker (used when the marker could not be filed, or the field is not a file)."""
    t = marker_target(raw)
    if not t:
        return None
    c = conf(env)
    try:
        if t[0] == "link":
            r = requests.get(t[1], timeout=c["timeout"])
            return r.content if r.status_code == 200 else None
        return Client(c).get_file(t[1])
    except (requests.RequestException, ImgSrvError) as e:
        _logger.warning("image server: cannot fetch %s: %s", t[1], e)
        return None


def marker_url(env, raw):
    """Browser URL to show a marker's picture (pasted link, or a direct upload not filed yet)."""
    t = marker_target(raw)
    if not t:
        return None
    if t[0] == "link":
        return t[1]
    return public_url(conf(env), t[1]) if t[1].rsplit(".", 1)[-1] in ("png", "jpg", "webp", "gif") else None
