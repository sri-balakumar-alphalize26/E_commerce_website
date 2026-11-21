# -*- coding: utf-8 -*-
"""Exact product before the picture: attribute polls.

A catalogue item like "Hard Disk 3.5 inch" carries Odoo attributes (Brand,
Capacity …). Before the picture + page go out, each attribute is asked as a
tap list, the answers resolve to one variant (product.product), and the
enquiry then names that exact item ("Seagate BarraCuda 2TB Hard Disk 3.5
inch"): the picture search, the page, the vendors' price check and the order
line all use it. No brand or size is hard-coded here - whatever attributes
the shop puts on the product are what gets asked.
"""
import json
import logging
import re

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

ANY = "\u270F\uFE0F TYPE IT / OTHER"
OTHER = "\u270F\uFE0F OTHER"
GENERIC = ('intel', 'amd', 'the', 'and', 'with', 'for', 'inch', 'ssd', 'ram', 'core')
ANY_WORDS = ("any", "anything", "no", "skip", "not sure", "dont know", "don't know", "whatever", "ok")


class SaGroupRequestVariant(models.Model):
    _inherit = 'sa.group.request'

    sa_variant_id = fields.Many2one('product.product', 'Exact variant', copy=False, ondelete='set null',
                                    help="The variant the customer picked through the attribute questions.")
    sa_attr_typing = fields.Text('Waiting for a typed attribute (JSON)', copy=False, readonly=True)
    sa_attr_notes = fields.Char('Customer\'s own words for an attribute', copy=False, readonly=True,
                                help="What they typed when no listed value matched (e.g. '64GB'); part of the item name.")

    # ------------------------------------------------------------------
    # Names
    # ------------------------------------------------------------------
    def _sa_variant_name(self):
        """'Seagate BarraCuda 2TB Hard Disk 3.5 inch' - chosen values, then the item."""
        self.ensure_one()
        v = self.sa_variant_id
        if not v:
            return ''
        values = [x.name for x in v.product_template_variant_value_ids.sorted(lambda x: x.attribute_id.sequence)]
        notes = (self.sa_attr_notes or '').strip()
        # typed values replace the listed values of their attributes
        if notes:
            open_attrs = self._sa_note_attrs()
            values = [x.name for x in v.product_template_variant_value_ids.sorted(lambda x: x.attribute_id.sequence)
                      if x.attribute_id.id not in open_attrs]
            for part in notes.split('; '):
                values.append(part.split(': ', 1)[-1] if ': ' in part else part)
        return ' '.join(values + [v.product_tmpl_id.name]).strip()

    def _sa_note_attrs(self):
        """Attribute ids the customer answered in their own words."""
        self.ensure_one()
        try:
            return set(json.loads(self.sa_attr_typing or '{}').get('noted') or [])
        except ValueError:
            return set()

    def _sa_confirm_name(self):
        self.ensure_one()
        if self.sa_variant_id:
            return self._sa_variant_name()
        return super()._sa_confirm_name()

    def _sa_wechat_item(self):
        """The vendors' WeChat text names the exact variant too."""
        self.ensure_one()
        if self.sa_variant_id:
            qty = int(self.qty or 0)
            return self._sa_variant_name(), ((' x %d' % qty) if qty else '')
        return super()._sa_wechat_item()

    # ------------------------------------------------------------------
    # Which attributes still need an answer
    # ------------------------------------------------------------------
    def _sa_attr_lines(self, product=None):
        product = product or self.product_id
        return product.attribute_line_ids.filtered(lambda l: len(l.value_ids) > 1).sorted(
            lambda l: (l.attribute_id.sequence, l.id)) if product else product

    def _sa_attr_needed(self):
        """True when the product has attributes and no variant is chosen yet."""
        self.ensure_one()
        return bool(self.product_id and not self.sa_variant_id and self._sa_attr_lines())

    VARIANT_POLL_MAX = 8

    def _sa_variant_sellable(self, variant):
        """Same rule as the menu's products: a variant that may not be sold
        short and has none free is not offered."""
        tmpl = variant.product_tmpl_id
        if 'allow_out_of_stock_order' not in tmpl._fields or 'free_qty' not in variant._fields:
            return True
        if not getattr(tmpl, 'is_storable', False) or tmpl.allow_out_of_stock_order:
            return True
        return (variant.sudo().free_qty or 0.0) > 0

    def _sa_variant_poll(self):
        """Every variant in one poll ("8GB · 256GB") when there are only a few,
        instead of one question per attribute. False when it does not apply."""
        self.ensure_one()
        product = self.product_id
        lines = self._sa_attr_lines(product)
        if not lines:
            return False
        variants = product.product_variant_ids.filtered(lambda v: v.active and self._sa_variant_sellable(v))
        if not 2 <= len(variants) <= self.VARIANT_POLL_MAX:
            return False
        menu, used = {}, set()
        for v in variants:
            values = v.product_template_attribute_value_ids.filtered(
                lambda x: x.attribute_line_id in lines).sorted(lambda x: (x.attribute_id.sequence, x.attribute_id.id))
            label = ' · '.join(values.mapped('name'))[:50] or v.display_name[:50]
            base, n = label, 2
            while label in used:
                label = '%s (%d)' % (base[:45], n)
                n += 1
            used.add(label)
            menu[label] = {'kind': 'variant', 'target': v.id}
        menu[OTHER] = {'kind': 'attr_steps'}
        for item in menu.values():
            item['req'] = self.id
            item['parent'] = 'attr'
        self.sa_menu_json = json.dumps(menu)
        self._ask(_("\U0001F4E6 *%(product)s* - which one? Tap one:", product=product.name),
                  [{'id': 'sa_var_%d' % i, 'title': label} for i, label in enumerate(menu)])
        return True

    def _sa_attr_ask(self, chosen=None, skipped=None):
        """Poll the next unanswered attribute. `chosen` = ptav ids so far,
        `skipped` = attribute ids the customer left open."""
        self.ensure_one()
        chosen = [int(c) for c in (chosen or []) if c]
        skipped = sorted({int(a) for a in (skipped or [])})
        if not chosen and not skipped and not self.env.context.get('sa_attr_steps') \
                and self._sa_variant_poll():
            return True
        product = self.product_id
        chosen_attr_ids = {ptav.attribute_id.id for ptav in
                           self.env['product.template.attribute.value'].sudo().browse(chosen)}
        for line in self._sa_attr_lines(product):
            if line.attribute_id.id in chosen_attr_ids or line.attribute_id.id in skipped:
                continue
            ptavs = line.product_template_value_ids.filtered(lambda v: v.ptav_active and v.product_attribute_value_id in line.value_ids)
            opts = []
            for ptav in ptavs[:8]:
                opts.append((ptav.name[:50], {'kind': 'attr', 'val': ptav.id, 'chosen': chosen, 'skipped': skipped, 'attr': line.attribute_id.id}))
            opts.append((ANY, {'kind': 'attr', 'val': 0, 'chosen': chosen, 'skipped': skipped, 'attr': line.attribute_id.id}))
            menu = {}
            for label, item in opts:
                item = dict(item)
                item.setdefault('req', self.id)
                item['parent'] = 'attr'
                menu[label] = item
            self.sa_menu_json = json.dumps(menu)
            self._ask(_("\U0001F4E6 *%(product)s* - which %(attr)s? Tap one:",
                        product=product.name, attr=line.attribute_id.name.lower()),
                      [{'id': 'sa_attr_%d' % i, 'title': label} for i, label in enumerate(menu)])
            return True
        return self._sa_attr_done(chosen)

    def _sa_attr_done(self, chosen):
        """All answered: pick the variant and carry on to the picture + page."""
        self.ensure_one()
        PTAV = self.env['product.template.attribute.value'].sudo()
        ptavs = PTAV.browse([c for c in chosen if c]).exists()
        product = self.product_id
        variant = self.env['product.product']
        if ptavs:
            # Every variant whose combination contains all the chosen values; the first of them when
            # some attribute was left open ("not sure").
            for v in product.product_variant_ids.filtered('active'):
                if ptavs <= v.product_template_attribute_value_ids:
                    variant = v
                    break
        if not variant:
            variant = product.product_variant_id
        self.sudo().write({'sa_variant_id': variant.id, 'sa_menu_json': False})
        self.sudo().write({'ai_search_term': self._sa_variant_name() or product.name})
        _logger.info("Sales Automation: enquiry %s -> variant %s (%s)", self.id, variant.id, self._sa_variant_name())
        return self._sa_confirm_customer_send()

    def _sa_menu_tapped(self, item):
        self.ensure_one()
        if item.get('kind') == 'variant':
            v = self.env['product.product'].sudo().browse(int(item.get('target') or 0)).exists()
            if v and v.product_tmpl_id == self.product_id:
                return self._sa_attr_done(v.product_template_attribute_value_ids.ids)
            return self._sa_attr_ask([], [])
        if item.get('kind') == 'attr_steps':
            # OTHER on the variant poll: one question per attribute, as before.
            return self.with_context(sa_attr_steps=True)._sa_attr_ask([], [])
        if item.get('kind') == 'attr':
            chosen = list(item.get('chosen') or [])
            skipped = list(item.get('skipped') or [])
            if item.get('val'):
                chosen.append(int(item['val']))
                return self._sa_attr_ask(chosen, skipped)
            # "type it": the next message from this person answers this attribute
            attr = self.env['product.attribute'].sudo().browse(int(item.get('attr') or 0))
            line = self._sa_attr_lines().filtered(lambda l: l.attribute_id == attr)[:1]
            example = ', '.join(line.value_ids.sorted('sequence').mapped('name')[:3]) if line else ''
            state = json.loads(self.sa_attr_typing or '{}') if self.sa_attr_typing else {}
            state.update({'attr': attr.id, 'chosen': chosen, 'skipped': skipped})
            self.sudo().write({'sa_attr_typing': json.dumps(state), 'sa_menu_json': False})
            self._say(_("\u270F\uFE0F Type the %(attr)s you need for *%(product)s* (for example: %(ex)s) - or reply ANY if it doesn't matter.",
                        attr=attr.name.lower(), product=self.product_id.name, ex=example or _('your value')))
            return True
        return super()._sa_menu_tapped(item)

    @api.model
    def _sa_typed_answer_hook(self, group, message, text):
        """The router: a typed message from somebody we asked to type an attribute."""
        pending = self.sudo().search([('group_id', '=', group.id), ('sa_attr_typing', '!=', False),
                                      ('state', '=', 'awaiting_confirm'),
                                      ('write_date', '>=', self._sa_still_warm())], order='id desc', limit=5)
        for req in pending:
            if req._sa_asked_of(message):
                return req._sa_attr_typed(text)
        return super()._sa_typed_answer_hook(group, message, text)

    @staticmethod
    def _sa_norm(text):
        import re as _re
        return _re.sub(r'[^a-z0-9]+', '', (text or '').lower())

    def _sa_attr_typed(self, text):
        """Read the typed words against the open attribute (and any other
        unanswered one they may have named in the same message)."""
        self.ensure_one()
        state = json.loads(self.sa_attr_typing or '{}') if self.sa_attr_typing else {}
        attr_id = int(state.get('attr') or 0)
        chosen = [int(c) for c in state.get('chosen') or []]
        skipped = [int(a) for a in state.get('skipped') or []]
        noted = set(state.get('noted') or [])
        typed = (text or '').strip()
        low = typed.lower().strip(' .!?')
        product = self.product_id
        if not typed or low in ANY_WORDS:
            skipped.append(attr_id)
            self.sudo().write({'sa_attr_typing': json.dumps({'noted': sorted(noted)})})
            return self._sa_attr_ask(chosen, skipped)
        norm = self._sa_norm(typed)
        chosen_attr_ids = {p.attribute_id.id for p in self.env['product.template.attribute.value'].sudo().browse(chosen)}
        matched_open = False
        for line in self._sa_attr_lines(product):
            if line.attribute_id.id in chosen_attr_ids or line.attribute_id.id in skipped:
                continue
            best, best_hits = None, 0
            words = set(w for w in re.split(r'[^a-z0-9]+', low) if w)
            for ptav in line.product_template_value_ids.filtered(lambda v: v.ptav_active and v.product_attribute_value_id in line.value_ids):
                vn = self._sa_norm(ptav.name)
                hits = 0
                if vn and (vn in norm or (len(vn) >= 3 and norm in vn)):
                    hits = 10
                else:
                    # the value's own code words ("b760m", "ddr5", "amd", "am5"): a long typed
                    # sentence that names the chipset still resolves to it
                    tokens = [t for t in re.split(r'[^a-z0-9]+', ptav.name.lower())
                              if t not in GENERIC and (len(t) >= 3 or (len(t) == 2 and any(c.isdigit() for c in t)))]
                    # "512" alone stands for "512GB": the bare number of a number+unit value counts too
                    for t in list(tokens):
                        mnum = re.match(r'^(\d+(?:\.\d+)?)[a-z]+$', t)
                        if mnum and mnum.group(1) not in tokens:
                            tokens.append(mnum.group(1))
                    hits = sum(1 for t in tokens if t in words or any(t in w for w in words if len(w) >= 4))
                    if tokens and tokens[0] in words:
                        hits += 2
                if hits > best_hits:
                    best, best_hits = ptav, hits
            if best is not None:
                chosen.append(best.id)
                chosen_attr_ids.add(line.attribute_id.id)
                if line.attribute_id.id == attr_id:
                    matched_open = True
        # A typed value with a unit that belongs to another still-open attribute
        # ("64gb" when the capacities listed are 8/16/32GB): remembered in the
        # customer's words for that attribute, no further question about it.
        unit_of = {}
        for line in self._sa_attr_lines(product):
            if line.attribute_id.id in chosen_attr_ids or line.attribute_id.id in skipped:
                continue
            for val in line.value_ids:
                m = re.match(r'\s*\d+(?:\.\d+)?\s*([a-z]+)', val.name.lower())
                if m:
                    unit_of.setdefault(m.group(1), set()).add(line.attribute_id.id)
        extra_notes = []
        for m in re.finditer(r'(\d+(?:\.\d+)?)\s*([a-z]+)', low):
            unit = m.group(2)
            attrs = unit_of.get(unit) or set()
            if len(attrs) == 1:
                aid = next(iter(attrs))
                if aid != attr_id or matched_open:
                    a2 = self.env['product.attribute'].sudo().browse(aid)
                    extra_notes.append('%s: %s%s' % (a2.name, m.group(1), unit.upper() if len(unit) <= 3 else unit))
                    noted.add(aid)
                    skipped.append(aid)
                    del unit_of[unit]
        if extra_notes:
            self.sudo().write({'sa_attr_notes': '; '.join(filter(None, [self.sa_attr_notes] + extra_notes))})
            self._say(_("Noted: *%(note)s* 👍", note=', '.join(n.split(': ', 1)[-1] for n in extra_notes)))
        if not matched_open:
            # their own words for this attribute: kept in the item's name, the attribute left open
            attr = self.env['product.attribute'].sudo().browse(attr_id)
            short = re.split(r'[,;(\n]', typed, 1)[0].strip()[:40]
            note = '%s: %s' % (attr.name, short) if attr else short
            noted.add(attr_id)
            skipped.append(attr_id)
            self.sudo().write({'sa_attr_notes': '; '.join(filter(None, [self.sa_attr_notes, note]))})
            self._say(_("Noted: *%(note)s* \U0001F44D", note=typed[:40]))
        self.sudo().write({'sa_attr_typing': json.dumps({'noted': sorted(noted)})})
        return self._sa_attr_ask(chosen, skipped)

    # ------------------------------------------------------------------
    # Hooks into the confirmation flow
    # ------------------------------------------------------------------
    def _sa_confirm_customer_send(self, text_only=False):
        """Attributes first; the picture + page only for the exact variant."""
        self.ensure_one()
        if self._sa_attr_needed():
            if self.state != 'awaiting_confirm':
                self.state = 'awaiting_confirm'
            return self._sa_attr_ask([])
        return super()._sa_confirm_customer_send(text_only=text_only)

    def _place_order(self):
        """The order line carries the exact variant, not the template's first one."""
        self.ensure_one()
        res = super()._place_order()
        self._sa_variant_pin_line(self.order_id)
        return res

    def _sa_variant_pin_line(self, order):
        """Put the exact variant on this enquiry's own order line - the first
        line of the product. A cart can hold the same product again in another
        variant, and that line already carries its own."""
        self.ensure_one()
        try:
            order = order.sudo()
            v = self.sa_variant_id
            if order and v:
                lines = order.order_line.filtered(
                    lambda l: l.product_id and l.product_id.product_tmpl_id == v.product_tmpl_id).sorted('id')[:1]
                for line in lines:
                    if line.product_id != v:
                        line.write({'product_id': v.id})
        except Exception as err:  # noqa: BLE001 - the order stands either way
            _logger.warning("Sales Automation: variant on order line for enquiry %s skipped: %s", self.id, err)

    # ------------------------------------------------------------------
    # Picture for the exact variant
    # ------------------------------------------------------------------
    def _sa_confirm_picture(self, fetch=True):
        self.ensure_one()
        v = self.sa_variant_id
        if not v:
            return super()._sa_confirm_picture(fetch=fetch)
        import base64
        # The variant's own photo, its "Variant images" tab (30 Sep 2026), then
        # its Extra Product Media (8 Oct 2026).
        own = v._sa_own_pictures()
        if own:
            return own[0], 'local'
        # No variant photo: the shop's own product photo, then the usual chain.
        if v.product_tmpl_id.image_1920:
            return base64.b64decode(v.product_tmpl_id.image_1920), 'local'
        return super()._sa_confirm_picture(fetch=fetch)


class SaConfirmLinkVariant(models.Model):
    _inherit = 'sa.confirm.link'

    def _picture_refs(self):
        """Variant links show only the chosen variant: its own pictures (photo,
        "Variant images" tab, Extra Product Media), the product's only when the
        variant has none of its own. Never another colour's picture."""
        self.ensure_one()
        v = self.request_id.sa_variant_id
        if not v:
            return super()._picture_refs()
        own = [(v, 'image_variant_1920')] if v.with_context(bin_size=True).image_variant_1920 else []
        own += [(p, 'image') for p in v._sa_variant_tab_pictures()]
        if 'product_variant_image_ids' in v._fields:
            own += [(i, 'image_1920') for i in v.product_variant_image_ids.sorted(lambda i: (i.sequence, i.id))]
        if own:
            return own
        tmpl = v.product_tmpl_id
        refs = [(tmpl, 'image_1920')]
        if 'product_template_image_ids' in tmpl._fields:
            refs += [(i, 'image_1920') for i in tmpl.product_template_image_ids.sorted(lambda i: (i.sequence, i.id))]
        return refs

    def _details_rows(self):
        rows = super()._details_rows()
        v = self.request_id.sa_variant_id
        if not v:
            return rows
        # Product row names the exact variant; attribute rows show the chosen value only.
        attr_names = {l.attribute_id.name for l in v.product_tmpl_id.attribute_line_ids}
        out = []
        for en, zh, val in rows:
            if en == _('Product'):
                out.append((en, zh, self.request_id._sa_variant_name()))
            elif en in attr_names:
                continue
            else:
                out.append((en, zh, val))
        insert_at = min(3, len(out))
        chosen = set(v._sa_chosen_attribute_rows())   # already shown under the pictures
        for label, value in v._sa_spec_rows():
            if (label, value) in chosen:
                continue
            out.insert(insert_at, (label, label, value))
            insert_at += 1
        return out

    def _attribute_rows(self):
        v = self.request_id.sa_variant_id
        return v._sa_chosen_attribute_rows() if v else super()._attribute_rows()
