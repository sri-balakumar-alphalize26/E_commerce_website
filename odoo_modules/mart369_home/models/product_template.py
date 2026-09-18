from odoo import fields, models

from odoo.addons.mart369.models.serializers import ART_CHOICES


class ProductTemplate(models.Model):
    """Wording the 369 Mart app shows on a product card.

    All optional. Anything left empty falls back to the product's own name,
    unit and photo, so a catalogue works without filling any of this in.
    A row can also override most of it for one placement only.
    """

    _inherit = 'product.template'

    mart_unit_text = fields.Char(
        string='Pack size',
        help='Shown under the name on the card, e.g. 1 kg, 500 g, 2 pieces. '
             'Empty falls back to the unit of measure.')
    mart_per_unit = fields.Char(
        string='Price per unit',
        help='Optional small print, e.g. 17.25 per 250 g.')
    mart_note = fields.Char(
        string='Small note',
        help='Optional line in brackets under the name, '
             'e.g. Approx 250-400 g.')
    mart_home_tag = fields.Char(
        string='Badge',
        help='A short pill on the card, e.g. New. It replaces the discount '
             'pill, so leave it empty on discounted products.')
    mart_is_veg = fields.Boolean(
        string='Vegetarian',
        help='On: the card carries the green vegetarian mark.')
    mart_low_stock_at = fields.Integer(
        string='Warn when stock reaches',
        help='The card says "Only N left" once free stock falls to this '
             'number or below. 0 turns the warning off.')
    mart_delivery_text = fields.Char(
        string='Express delivery time',
        help='Shown on Express cards only, e.g. 3-5 days. A product with '
             'this filled in is treated as an Express item by the app.')

    # -- Used only when the product has no photo --
    mart_art = fields.Selection(
        ART_CHOICES, string='Drawing',
        help='The app draws this instead of a photo when the product has '
             'none, so a card is never blank.')
    mart_color = fields.Char(
        string='Drawing colour',
        help='Optional tint for the drawing, e.g. #e0453a.')
    mart_badge = fields.Char(
        string='Text on drawing',
        help='Optional short word drawn inside, e.g. ATTA or 70%.')
