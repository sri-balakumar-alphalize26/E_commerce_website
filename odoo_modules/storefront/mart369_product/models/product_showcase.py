"""Big pictures with a short caption, under the product - Amazon's "From the
manufacturer".

Each block is one picture, an optional caption printed above it, and a
width: a full block takes the whole row, two half blocks sit side by side.
Edited in the 369 Mart section (and on 369 Mart > Products) through
`product.template.mart_showcase_json`, one list for the whole stack, so the
form's own Save keeps them with everything else.
"""

from odoo import api, fields, models


class Mart369ProductShowcase(models.Model):
    _name = 'mart369.product.showcase'
    _description = '369 Mart product picture block'
    _order = 'sequence, id'

    product_tmpl_id = fields.Many2one(
        'product.template', string='Product', required=True,
        ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    image = fields.Image(string='Picture', max_width=1920, max_height=1920, required=True)
    caption = fields.Char(help='Printed above the picture, e.g. Four gorgeous colours.')
    width = fields.Selection(
        [('full', 'Full width'), ('half', 'Half width')],
        default='full', required=True,
        help='Full takes the whole row; two half blocks sit side by side.')

    def _can_return_content(self, field_name=None, access_token=None):
        """The shop shows these pictures without logging in - only the
        picture, not the record."""
        if field_name == 'image':
            return True
        return super()._can_return_content(field_name, access_token)


class ProductTemplateShowcase(models.Model):
    _inherit = 'product.template'

    mart_showcase_ids = fields.One2many(
        'mart369.product.showcase', 'product_tmpl_id', string='Picture blocks')
    mart_showcase_json = fields.Json(
        string='From the manufacturer',
        compute='_compute_mart_showcase_json', inverse='_inverse_mart_showcase_json',
        help='Big pictures with a short caption, shown under the product. '
             'Full width: 1600 × 900 px · Half width: 800 × 800 px.')

    @api.depends('mart_showcase_ids', 'mart_showcase_ids.caption',
                 'mart_showcase_ids.width', 'mart_showcase_ids.sequence')
    def _compute_mart_showcase_json(self):
        for product in self:
            product.mart_showcase_json = [{
                'id': block.id,
                'url': '/web/image/mart369.product.showcase/%d/image/512x512?unique=%s' % (
                    block.id, int(block.write_date.timestamp()) if block.write_date else 0),
                'caption': block.caption or '',
                'width': block.width,
            } for block in product.mart_showcase_ids]

    def _inverse_mart_showcase_json(self):
        """The list as the screen holds it: a row with an id is kept (caption,
        width and place updated), a row with picture data is added, and a
        block no longer listed goes. sudo after the product's own write check:
        whoever may edit the product may edit its blocks."""
        Block = self.env['mart369.product.showcase'].sudo()
        for product in self:
            rows = product.mart_showcase_json if isinstance(product.mart_showcase_json, list) else []
            own = product.sudo().mart_showcase_ids
            keep = Block
            for position, row in enumerate(rows):
                if not isinstance(row, dict):
                    continue
                vals = {
                    'caption': str(row.get('caption') or '').strip()[:300],
                    'width': 'half' if row.get('width') == 'half' else 'full',
                    'sequence': (position + 1) * 10,
                }
                block = own.filtered(lambda b: b.id == row.get('id')) if row.get('id') else Block
                if block:
                    block.write(vals)
                    keep |= block
                elif row.get('data'):
                    data = str(row['data']).split(',', 1)[-1]
                    keep |= Block.create(dict(vals, product_tmpl_id=product.id, image=data))
            (own - keep).unlink()
