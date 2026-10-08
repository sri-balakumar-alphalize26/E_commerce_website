"""The shop footer's pages, kept in Odoo.

One record per page: a title, the address it lives at (/page/<slug> on the
shop), the footer column it sits in, and its text - written with Odoo's own
editor. Some pages carry more than text: FAQs are questions and answers,
Contact adds the shop's phone, email and address, Delivery areas the pincodes
the shop serves.
"""

from odoo import api, fields, models
from odoo.tools import html2plaintext, html_sanitize

COLUMNS = [
    ('help', 'Help'),
    ('company', 'Company'),
    ('policies', 'Policies'),
    ('none', 'Not in the footer'),
]
KINDS = [
    ('page', 'A page of text'),
    ('faqs', 'Questions and answers'),
    ('contact', 'Contact details'),
    ('areas', 'Delivery areas'),
]


def _clean(html):
    """The editor's HTML as the shop may draw it, or '' when it says nothing."""
    if not html2plaintext(html or '').strip():
        return ''
    return str(html_sanitize(html, strip_style=True, strip_classes=True) or '')


class Mart369InfoPage(models.Model):
    _name = 'mart369.info.page'
    _description = '369 Mart info page'
    _order = 'column, sequence, id'

    name = fields.Char(string='Title', required=True)
    slug = fields.Char(
        string='Address', required=True,
        help='The page lives at /page/<address> on the shop, e.g. terms.')
    column = fields.Selection(COLUMNS, string='Footer column', default='help', required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True, help='Off: the page and its footer link are gone from the shop.')
    kind = fields.Selection(KINDS, string='Page type', default='page', required=True)
    summary = fields.Char(help='One line under the title, e.g. "How we look after your data".')
    body = fields.Html(string='Text', sanitize=True,
                       help='Write it like a Word page: headings, bullets, bold, links.')
    faq_ids = fields.One2many('mart369.info.faq', 'page_id', string='Questions')
    preview_url = fields.Char(compute='_compute_preview_url', string='On the shop')

    _slug_uniq = models.Constraint('unique(slug)', 'Another page already uses this address.')

    @api.depends('slug')
    def _compute_preview_url(self):
        site = self.env['product.template']._mart369_site_url()
        for page in self:
            page.preview_url = '%s/page/%s' % (site, page.slug) if page.slug else ''

    @api.onchange('name')
    def _onchange_name_slug(self):
        if self.name and not self.slug:
            self.slug = '-'.join(''.join(c if c.isalnum() else ' ' for c in self.name.lower()).split())

    # ------------------------------------------------------------- the shop

    @api.model
    def _mart369_footer_columns(self):
        """[{key, title, links: [{label, slug}]}] for the footer, in order."""
        out = []
        pages = self.sudo().search([('column', '!=', 'none')])
        for key, title in COLUMNS[:-1]:
            links = [{'label': p.name, 'slug': p.slug} for p in pages if p.column == key]
            if links:
                out.append({'key': key, 'title': title, 'links': links})
        return out

    def _mart369_serialize(self):
        """Everything the shop's page draws."""
        self.ensure_one()
        vals = {
            'slug': self.slug,
            'title': self.name,
            'summary': self.summary or '',
            'kind': self.kind,
            'column': self.column,
            'html': _clean(self.body),
            'updated': fields.Date.to_string(self.write_date.date()) if self.write_date else '',
            # The other pages of the same column, for the side list.
            'siblings': [{'label': p.name, 'slug': p.slug} for p in self.sudo().search(
                [('column', '=', self.column), ('column', '!=', 'none')])],
        }
        if self.kind == 'faqs':
            vals['faqs'] = [{'q': f.question, 'a': _clean(f.answer)} for f in self.faq_ids]
        if self.kind == 'contact':
            vals['contact'] = self._mart369_contact()
        if self.kind == 'areas':
            vals['areas'] = self._mart369_areas()
        return vals

    @api.model
    def _mart369_contact(self):
        """The shop's own phone, email and address (Settings > Companies)."""
        company = self.env.company.sudo()
        partner = company.partner_id
        address = ', '.join(x for x in (partner.street, partner.street2, partner.city,
                                        partner.zip, partner.country_id.name) if x)
        return {'name': company.name or '', 'phone': company.phone or partner.phone or '',
                'email': company.email or partner.email or '', 'address': address}

    @api.model
    def _mart369_areas(self):
        """[{pincode, name, quick, express, eta}] the shop delivers to: the
        Quick / Express module's areas where it runs, else the website's own."""
        env = self.env
        model = None
        if 'sa.qe.service.area' in env and 'sa.qe.delivery.rule' in env:
            model = env['sa.qe.service.area']
        elif 'mart369.service.area' in env:
            model = env['mart369.service.area']
        if model is None:
            return []
        rows = []
        for area in model.sudo().search([], order='pincode'):
            rows.append({
                'pincode': area.pincode or '',
                'name': getattr(area, 'name', '') or '',
                'quick': bool(getattr(area, 'quick', False)),
                'express': bool(getattr(area, 'express', False)),
                'eta': getattr(area, 'eta', '') or '',
            })
        return rows


class Mart369InfoFaq(models.Model):
    _name = 'mart369.info.faq'
    _description = '369 Mart FAQ'
    _order = 'sequence, id'

    page_id = fields.Many2one('mart369.info.page', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    question = fields.Char(required=True)
    answer = fields.Html(sanitize=True)
