# -*- coding: utf-8 -*-
"""Where a customer page's picture comes from (17 Nov 2026).

With the image server connector (ai369_image_server) installed, Odoo can only
read a picture kept there by downloading it: `product.image_128` fetches the
file from the image server. The order / pay page and the review page put their
pictures inline, so they downloaded every picture before they could answer -
one of the reasons the pay page was slow. And a page that links a picture as
/web/image sends the phone through Odoo first, only to be redirected.

A picture kept on the image server is now linked straight there; any other
picture is shown exactly as before. The connector is optional and found at run
time: without it, or for a picture still kept in Odoo, nothing changes.
"""
import logging
from urllib.parse import urlsplit

from markupsafe import Markup

from odoo import api, models
from odoo.tools.image import image_data_uri

_logger = logging.getLogger(__name__)


class SaPicture(models.AbstractModel):
    _name = 'sa.picture'
    _description = 'Pictures on customer pages'

    @api.model
    def remote_url(self, record, field):
        """The image server's own address of `record.field`, or '' when the
        picture is not kept there (or the connector is not installed)."""
        if not record or len(record) != 1:
            return ''
        Binary = self.env['ir.binary'].sudo()
        if not hasattr(Binary, '_imgsrv_attachment'):
            return ''
        try:
            attachment = Binary._imgsrv_attachment(record.sudo(), field)
            if attachment and (attachment.store_fname or '').startswith('imgsrv:') and attachment.imgsrv_url:
                return attachment.imgsrv_url
        except Exception:  # noqa: BLE001 - a picture is never worth an error
            _logger.info("Picture link for %s.%s not found", record._name, field, exc_info=True)
        return ''

    @api.model
    def image_host(self):
        """'https://images.example' when the image server connector is
        installed and switched on, else ''."""
        if 'imgsrv_url' not in self.env['ir.attachment']._fields:
            return ''
        get = self.env['ir.config_parameter'].sudo().get_param
        if str(get('ai369_image_server.enabled') or '').lower() not in ('true', '1'):
            return ''
        parts = urlsplit((get('ai369_image_server.url') or '').strip())
        if parts.scheme not in ('http', 'https') or not parts.netloc:
            return ''
        return '%s://%s' % (parts.scheme, parts.netloc)

    @api.model
    def preconnect_html(self):
        """Tags that let the phone connect to the image server while the page
        is still arriving, instead of when the first picture is reached. No
        `crossorigin`: pictures are plain <img> loads, which only reuse a
        connection opened the same way."""
        host = self.image_host()
        if not host:
            return Markup('')
        return Markup('<link rel="preconnect" href="%s"><link rel="dns-prefetch" href="%s">') % (host, host)

    @api.model
    def has(self, record, field):
        """Is there a picture? Asked by its size: reading the picture itself
        downloads it when it is kept on the image server."""
        if not record or len(record) != 1 or field not in record._fields:
            return False
        if record._name == 'product.product' and field.startswith('image_') \
                and not field.startswith('image_variant_'):
            # A variant's image_* is computed from its own picture or the
            # product's, and computing it reads (downloads) the picture even
            # when only its size is asked for. Both stored fields answer by size.
            own = field.replace('image_', 'image_variant_', 1)
            return (own in record._fields and self.has(record, own)) or self.has(record.product_tmpl_id, field)
        return bool(record.with_context(bin_size=True)[field])

    @api.model
    def url(self, record, field, fallback):
        """For <img src>: the image server's address, else `fallback` (the
        usual /web/image address), else '' when there is no picture."""
        if not self.has(record, field):
            return ''
        return self.remote_url(record, field) or fallback

    @api.model
    def src(self, record, field='image_128'):
        """For <img src> on a page that used to inline the picture: the image
        server's address, else the picture inline exactly as before, else ''."""
        if not self.has(record, field):
            return ''
        remote = self.remote_url(record, field)
        if remote:
            return remote
        value = record[field]
        return image_data_uri(value) if value else ''
