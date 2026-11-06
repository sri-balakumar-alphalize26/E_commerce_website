"""The shop's footer, set in Odoo: its tagline, app links, the "We accept"
chips, and which categories its Shop column lists.

369 Mart > Page building > Footer. Categories are picked with "In footer" in
the catalogue's category list (drag to order); with none picked, the footer
lists the first few shown in the app, as before.
"""

from odoo import api, fields, models

DEFAULT_PAYMENTS = 'UPI\nCredit & debit cards\nNet banking\nCash on delivery\n369 Wallet'


class Mart369ConfigFooter(models.Model):
    _inherit = 'mart369.config'

    footer_tagline = fields.Char(
        string='Line under the logo', default='Computer parts and gear. In minutes, or in days.')
    footer_android_url = fields.Char(
        string='Android app link', help='The Play Store address. Empty: the Android button is hidden.')
    footer_ios_url = fields.Char(
        string='iPhone app link', help='The App Store address. Empty: the iPhone button is hidden.')
    footer_payments = fields.Text(
        string='"We accept"', default=DEFAULT_PAYMENTS,
        help='One per line, shown as chips at the foot of every page. Empty: the row is hidden.')
    footer_category_count = fields.Integer(
        string='Categories in the footer', default=5,
        help='When no category is ticked "In footer", the footer lists this many, '
             'in the order of the catalogue.')

    def mart369_action_footer(self):
        """Open the one settings record on its Footer form."""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Footer',
            'res_model': 'mart369.config',
            'res_id': self.sudo()._get().id,
            'view_mode': 'form',
            'views': [(self.env.ref('mart369_pages.view_mart369_footer_form').id, 'form')],
            'target': 'current',
        }

    @api.model
    def _mart369_footer(self):
        """Everything the shop's footer draws."""
        config = self.sudo()._get()
        Category = self.env['product.public.category'].sudo()
        shown = [('mart_in_app', '=', True)]
        picked = Category.search(shown + [('mart_in_footer', '=', True)], order='sequence, id')
        top = Category.search(shown + [('parent_id', '=', False)], order='sequence, id')
        if picked:
            cats = picked
        else:
            cats = top[:max(0, config.footer_category_count or 0)]

        def slug(category):
            # A sub-category opens inside its parent: "laptops/gaming".
            if category.parent_id and category.parent_id.mart_slug:
                return '%s/%s' % (category.parent_id.mart_slug, category.mart_slug)
            return category.mart_slug

        return {
            'tagline': config.footer_tagline or '',
            'apps': {'android': config.footer_android_url or '', 'ios': config.footer_ios_url or ''},
            'payments': [p.strip() for p in (config.footer_payments or '').splitlines() if p.strip()],
            'shop': [{'name': c.name, 'slug': slug(c)} for c in cats if c.mart_slug],
            # "All categories" when the shop has more than the footer lists.
            'more': len(top) > len(cats),
            'columns': self.env['mart369.info.page']._mart369_footer_columns(),
        }


class ProductPublicCategoryFooter(models.Model):
    _inherit = 'product.public.category'

    mart_in_footer = fields.Boolean(
        string='In footer',
        help='List this category in the shop footer\'s Shop column. With none ticked, '
             'the footer lists the first few categories.')
