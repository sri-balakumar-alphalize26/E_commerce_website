import base64
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class WhatsAppHelpDocument(models.Model):
    _name = 'whatsapp.help.document'
    _description = 'Help Document'
    _order = 'sequence, id'

    name = fields.Char('Title', required=True)
    description = fields.Text('Description')
    icon = fields.Char('Icon', help='Emoji or icon character (e.g. clock, envelope)')
    sequence = fields.Integer('Sequence', default=10)
    active = fields.Boolean('Active', default=True)

    pdf_file = fields.Binary('Upload PDF', attachment=True)
    pdf_filename = fields.Char('PDF Filename')
    static_pdf_url = fields.Char(
        'Static PDF URL',
        help='Path to a static PDF file, e.g. /whatsapp_email/static/doc/manual.pdf',
    )
    html_content = fields.Html(
        'HTML Content (optional)',
        help='Shown instead of the PDF on "Open Guide".',
        sanitize=False,
    )

    @staticmethod
    def _normalize_static_url(url):
        """The shipped help PDFs live in whatsapp_email/static/doc/. Older records
        (and the noupdate seed data on already-installed databases) stored a
        whatsapp_gateway/... path that 404s. Rewrite it at runtime so the links
        work on ANY database/install without manual DB edits."""
        if not url:
            return url
        return url.replace('/whatsapp_gateway/static/doc/', '/whatsapp_email/static/doc/')

    @api.model
    def get_help_documents(self):
        """Return active help documents for the client action."""
        docs = self.search([('active', '=', True)])
        result = []
        for doc in docs:
            view_url = ''
            download_url = ''
            if doc.static_pdf_url:
                url = self._normalize_static_url(doc.static_pdf_url)
                view_url = url
                download_url = url
            elif doc.pdf_file:
                fname = doc.pdf_filename or 'document.pdf'
                base = '/web/content/%s/%d/pdf_file/%s' % (
                    self._name, doc.id, fname,
                )
                view_url = base
                download_url = base + '?download=true'
            result.append({
                'id': doc.id,
                'name': doc.name,
                'description': doc.description or '',
                'icon': doc.icon or '',
                'view_url': view_url,
                'download_url': download_url,
                'html_content': doc.html_content or '',
                'sequence': doc.sequence,
            })
        return result
