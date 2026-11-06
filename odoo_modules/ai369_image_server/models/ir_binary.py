"""/web/image and /web/content: answer with a redirect to the image server instead of streaming bytes."""
import logging

from odoo import models

import base64

from odoo.http import Stream

from .imgsrv_client import PREFIX, is_marker_b64, marker_url

_logger = logging.getLogger(__name__)


class IrBinary(models.AbstractModel):
    _inherit = "ir.binary"

    def _imgsrv_attachment(self, record, field_name, depth=0):
        """Find the attachment that really holds the image, following related fields and the
        product variant -> template fallback. Returns an ir.attachment (maybe empty)."""
        Att = self.env["ir.attachment"].sudo()
        field = record._fields.get(field_name)
        if not field or field.type != "binary" or depth > 3 or len(record) != 1:
            return Att
        if field.attachment and field.store:
            return Att.search([("res_model", "=", record._name), ("res_id", "=", record.id),
                               ("res_field", "=", field_name)], limit=1)
        if field.related:
            rel = field.related.split(".") if isinstance(field.related, str) else list(field.related)
            *path, last = rel
            target = record.sudo()
            for name in path:
                target = target[name][:1]
                if not target:
                    return Att
            return self._imgsrv_attachment(target, last, depth + 1)
        if record._name == "product.product" and field_name.startswith("image_"):
            variant = field_name.replace("image_", "image_variant_", 1)
            if variant in record._fields:
                att = self._imgsrv_attachment(record, variant, depth + 1)
                if att:
                    return att
            return self._imgsrv_attachment(record.sudo().product_tmpl_id, field_name, depth + 1)
        return Att

    def _record_to_stream(self, record, field_name):
        if not (record._name == "ir.attachment" and field_name in ("raw", "datas", "db_datas")):
            try:
                att = self._imgsrv_attachment(record, field_name)
            except Exception:  # never break image display because of the connector
                _logger.exception("image server: lookup failed for %s.%s", record._name, field_name)
                att = None
            if att and att.store_fname and att.store_fname.startswith(PREFIX) and att.imgsrv_url:
                record._check_field_access(record._fields[field_name], "read")
                return att._to_http_stream()
            # a pasted link / direct upload that is not filed yet (or a field kept in the table): show the picture
            url = None
            try:
                if att and not (att.store_fname or "").startswith(PREFIX) and (att.file_size or 0) <= 800:
                    url = marker_url(self.env, att._imgsrv_marker())
                elif not att and field_name in record._fields and record._fields[field_name].type == "binary":
                    val = record.sudo()[field_name]
                    if val and is_marker_b64(val):
                        url = marker_url(self.env, base64.b64decode(val))
            except Exception:
                url = None
            if url:
                record._check_field_access(record._fields[field_name], "read")
                return Stream(type="url", url=url, max_age=60)
        return super()._record_to_stream(record, field_name)
