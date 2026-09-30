"""The console's Edit product screen edits the senior's two variant tabs.

mart369_product draws a Variants block (image, stock) and leaves two hooks for
whatever gives a variant more than that. sales_automation_confirm does: a
*Variant images* tab (`sa.confirm.picture` with `product_id`) and a *Variant
specs* table (`sa.variant.spec`). They are filled in here, so the same photos
and rows are edited from the console as from Odoo's Product Variants form,
and the WhatsApp page and the website both show what was saved.

sudo, after the desk's own check (`_mart369_desk_check`, the website designer
role): both models are readable by Sales Automation users only, and the
person on the product screen is a shop manager, not necessarily one of them.
"""

from odoo import api, models


class ProductTemplateVariantDesk(models.Model):
    _inherit = 'product.template'

    @api.model
    def _mart369_desk_media_ok(self):
        return True

    @api.model
    def _mart369_desk_variant_extras(self, variant):
        out = super()._mart369_desk_variant_extras(variant)
        variant = variant.sudo()
        pictures = variant.with_context(bin_size=True).sa_variant_picture_ids.sorted(
            lambda p: (p.sequence, p.id)).filtered('image')
        out['pictures'] = [{
            'id': pic.id,
            'name': pic.name or '',
            'url': '/369mart/variant/photo/%d' % pic.id,
        } for pic in pictures]
        out['specs'] = [{
            'id': spec.id,
            'name': spec.name or '',
            'value': spec.value or '',
            'attribute': bool(spec.attribute_id),
        } for spec in variant.sa_spec_ids.sorted(lambda s: (s.sequence, s.id))]
        return out

    def _mart369_desk_save_variant_extras(self, variant, data):
        """data['pictures'] = {'add': [{name, data}], 'remove': [id], 'order': [id]}
        data['specs'] = the whole table, in order: [{id?, name, value}]
        data['fill'] = True to add the attribute lines not in the table yet."""
        super()._mart369_desk_save_variant_extras(variant, data)
        variant = variant.sudo()
        Picture = self.env['sa.confirm.picture'].sudo()
        Spec = self.env['sa.variant.spec'].sudo()

        pictures = data.get('pictures')
        if isinstance(pictures, dict):
            own = variant.sa_variant_picture_ids
            remove = {int(i) for i in (pictures.get('remove') or [])}
            own.filtered(lambda p: p.id in remove).unlink()
            last = max(own.exists().mapped('sequence') or [0])
            for added in pictures.get('add') or []:
                if not isinstance(added, dict) or not added.get('data'):
                    continue
                last += 10
                Picture.create({'product_id': variant.id, 'image': added['data'],
                                'name': (added.get('name') or '')[:120], 'sequence': last})
            for position, pid in enumerate(pictures.get('order') or []):
                own.exists().filtered(lambda p: p.id == int(pid)).write(
                    {'sequence': (position + 1) * 10})

        specs = data.get('specs')
        if isinstance(specs, list):
            own = variant.sa_spec_ids
            kept = set()
            for position, row in enumerate(specs):
                if not isinstance(row, dict):
                    continue
                name = ' '.join(str(row.get('name') or '').split())
                if not name:
                    continue
                vals = {'name': name, 'value': (row.get('value') or '').strip(),
                        'sequence': (position + 1) * 10}
                line = own.filtered(lambda s: s.id == int(row.get('id') or 0))
                if line:
                    line.write(vals)
                    kept.add(line.id)
                else:
                    kept.add(Spec.create(dict(vals, product_id=variant.id)).id)
            own.filtered(lambda s: s.id not in kept).unlink()

        if data.get('fill'):
            variant.action_sa_fill_specs()
        return True
