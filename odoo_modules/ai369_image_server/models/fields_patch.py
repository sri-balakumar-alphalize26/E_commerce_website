"""Field support for our small markers (direct browser upload / pasted image-server link).

* image fields stored as files (the normal case) keep the marker until commit; the connector then files it;
* fields stored inside the database table (attachment=False, common in custom modules) can't hold a link,
  so the marker is replaced by the real picture / file before it is written.
"""
import base64
import logging

from odoo import fields
from odoo.exceptions import UserError

from .imgsrv_client import is_marker_b64, marker_bytes

_logger = logging.getLogger(__name__)
_orig_image_process = fields.Image._image_process
_orig_to_column = fields.Binary.convert_to_column


def _image_process(self, value, env):
    if value and is_marker_b64(value):
        if self.attachment:
            return value
        data = marker_bytes(env, base64.b64decode(value))
        if not data:
            raise UserError(env._("The picture could not be loaded from the image server. Check the link and try again."))
        value = base64.b64encode(data)
    return _orig_image_process(self, value, env)


def _convert_to_column(self, value, record, values=None, validate=True):
    if value and not self.attachment and is_marker_b64(value):
        data = marker_bytes(record.env, base64.b64decode(value))
        if not data:
            raise UserError(record.env._("The file could not be loaded from the image server. Try the upload again."))
        value = base64.b64encode(data)
    return _orig_to_column(self, value, record, values, validate)


fields.Image._image_process = _image_process
fields.Binary.convert_to_column = _convert_to_column
