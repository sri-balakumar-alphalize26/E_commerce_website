# -*- coding: utf-8 -*-
"""Per-variant pictures and specs, on the variant form and on the confirmation page.

The owner (30 Sep 2026): "multiple image add for each variant, and a details
tab like an e-commerce website - the attribute values fetched by default,
editable". Odoo's own extra-media fields live in website_sale, which this
stack does not depend on, so the pictures reuse `sa.confirm.picture` (a new
`product_id` link) and the specs are a small table of their own.
"""
from odoo import _, api, fields, models


class SaConfirmPictureVariant(models.Model):
    _inherit = 'sa.confirm.picture'

    product_id = fields.Many2one('product.product', 'Variant', ondelete='cascade', index=True)
    name = fields.Char('Caption')


class SaVariantSpec(models.Model):
    """One line of the specs table: "Processor: Core i3"."""
    _name = 'sa.variant.spec'
    _description = 'Variant specification line'
    _order = 'sequence, id'

    product_id = fields.Many2one('product.product', 'Variant', required=True,
                                 ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    name = fields.Char('Specification', required=True)
    value = fields.Char('Value')
    attribute_id = fields.Many2one('product.attribute', 'From attribute',
                                   help="Filled from this attribute of the variant. "
                                        "Edit the value freely; it stays yours.")


class ProductProductMedia(models.Model):
    _inherit = 'product.product'

    sa_variant_picture_ids = fields.One2many(
        'sa.confirm.picture', 'product_id', string='Variant pictures',
        help="Extra photos of THIS variant. The first one becomes the main "
             "picture on the WhatsApp confirmation page when the variant has "
             "no image of its own; the others fill the strip.")
    sa_spec_ids = fields.One2many(
        'sa.variant.spec', 'product_id', string='Variant specs',
        help="What the confirmation page lists under the picture. Filled "
             "from the attributes; add or edit lines as you like.")
    sa_spec_count = fields.Integer(compute='_compute_sa_spec_count')

    @api.depends('sa_spec_ids')
    def _compute_sa_spec_count(self):
        for v in self:
            v.sa_spec_count = len(v.sa_spec_ids)

    def _sa_shop_media(self):
        """This variant's own Extra Product Media (website_sale, when installed), as bytes."""
        self.ensure_one()
        if 'product_variant_image_ids' not in self._fields:
            return []
        from .product_image_fetch import _media_bytes
        return _media_bytes(self.product_variant_image_ids)

    def _sa_variant_tab_pictures(self):
        """The "Variant images" tab, in order. With 369 Mart, mart369_whatsapp_bridge
        copies these to Extra Product Media and marks them; they count once, there."""
        self.ensure_one()
        return self.sa_variant_picture_ids.filtered(lambda p: p.source != 'photographs').sorted(
            lambda p: (p.sequence, p.id))

    def _sa_own_pictures(self):
        """Every picture of THIS variant, as bytes, no repeats: its photo, the
        "Variant images" tab, then its Extra Product Media."""
        self.ensure_one()
        import base64
        out = []
        sources = [self.image_variant_1920] + [p.image for p in self._sa_variant_tab_pictures()]
        for data in sources:
            if data:
                raw = base64.b64decode(data)
                if raw not in out:
                    out.append(raw)
        out += [raw for raw in self._sa_shop_media() if raw not in out]
        return out

    def _sa_chosen_attribute_rows(self):
        """(label, value) of each chosen attribute, the shop's edited spec line
        winning over the raw value; shown once, under the pictures."""
        self.ensure_one()
        edited = {s.attribute_id.id: s for s in self.sa_spec_ids if s.attribute_id and (s.name or '').strip()}
        rows = []
        for attr, value in self._sa_attribute_pairs():
            s = edited.get(attr.id)
            rows.append((s.name.strip(), (s.value or '').strip()) if s else (attr.name, value))
        return rows

    # ------------------------------------------------------------------
    # Specs: attributes by default, edits kept
    # ------------------------------------------------------------------
    def _sa_attribute_pairs(self):
        """[(attribute, value name)] for this variant, in attribute order."""
        self.ensure_one()
        ptavs = self.product_template_variant_value_ids.sorted(
            lambda x: (x.attribute_id.sequence, x.attribute_id.id))
        return [(x.attribute_id, x.name) for x in ptavs]

    def action_sa_fill_specs(self):
        """Add one line per attribute that is not in the table yet. Lines
        the shop already has (edited or not) are left alone."""
        Spec = self.env['sa.variant.spec'].sudo()
        for v in self:
            have = {s.attribute_id.id for s in v.sa_spec_ids if s.attribute_id}
            seq = 10
            for attr, value in v._sa_attribute_pairs():
                if attr.id in have:
                    continue
                Spec.create({'product_id': v.id, 'sequence': seq,
                             'name': attr.name, 'value': value,
                             'attribute_id': attr.id})
                seq += 10
        return True

    def _sa_spec_rows(self):
        """(label, value) pairs for the page: stored lines first (they may be
        edited), then any attribute not covered by a stored line."""
        self.ensure_one()
        rows, covered = [], set()
        for s in self.sa_spec_ids.sorted(lambda s: (s.sequence, s.id)):
            if not (s.name or '').strip():
                continue
            rows.append((s.name.strip(), (s.value or '').strip()))
            if s.attribute_id:
                covered.add(s.attribute_id.id)
        for attr, value in self._sa_attribute_pairs():
            if attr.id not in covered:
                rows.append((attr.name, value))
        return rows

    @api.model_create_multi
    def create(self, vals_list):
        """A new variant starts with its attribute lines already in the table,
        so the shop sees them and can edit them without pressing anything."""
        records = super().create(vals_list)
        try:
            records.filtered(lambda v: v.product_template_variant_value_ids).action_sa_fill_specs()
        except Exception:  # noqa: BLE001 - never block a product create
            pass
        return records
