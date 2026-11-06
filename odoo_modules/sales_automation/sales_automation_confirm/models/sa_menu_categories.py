# -*- coding: utf-8 -*-
"""NEW ORDER in the welcome menu opens the catalogue as polls.

NEW ORDER → the top-level categories (Laptop, Mobile, Computer parts …) plus
NOT LISTED. A category → its sub-categories, or its products, plus NOT
LISTED. A product → a fresh enquiry for it, straight to the picture + page
confirmation. NOT LISTED → "tell me what you need" and the typed flow as
before. Levels are 'categ:<id>' and 'prod:<id>'; BACK walks up.
"""
import json
import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

NOT_LISTED = "✏️ NOT LISTED"


class ProductCategoryMenu(models.Model):
    _inherit = 'product.category'

    sa_menu_sequence = fields.Integer('WhatsApp menu order', default=100,
                                      help="Lower comes first in the NEW ORDER category list.")
    sa_menu_hide = fields.Boolean('Hide from the WhatsApp menu', default=False,
                                  help="Test or internal categories: never listed under NEW ORDER (typed requests still work).")


class SaGroupRequestMenuCategories(models.Model):
    _inherit = 'sa.group.request'

    # ------------------------------------------------------------------
    # What to list
    # ------------------------------------------------------------------
    @api.model
    def _sa_menu_categories(self, parent=None):
        """Categories worth showing: with sale products (or vendors) below them."""
        Categ = self.env['product.category'].sudo()
        Prod = self.env['product.template'].sudo()
        domain = [('parent_id', '=', parent.id if parent else False), ('sa_menu_hide', '=', False)]
        out = []
        for c in Categ.search(domain, order='sa_menu_sequence, name'):
            has_products = Prod.search_count([('categ_id', 'child_of', c.id), ('sale_ok', '=', True)]) > 0
            has_vendors = bool(getattr(c, 'sa_vendor_ids', False))
            if has_products or has_vendors:
                out.append(c)
        return out

    PAGE = 6

    @api.model
    def _sa_menu_products(self, categ, page=0):
        """(products on this page, more pages after it)"""
        Prod = self.env['product.template'].sudo()
        # A product that may not be sold short and has no free stock is left
        # out (a domain, so the pages stay right).
        rows = Prod.search([('categ_id', 'child_of', categ.id), ('sale_ok', '=', True)] + self._sa_unsellable_domain(),
                           order='name', offset=page * self.PAGE, limit=self.PAGE + 1)
        return rows[:self.PAGE], len(rows) > self.PAGE

    @staticmethod
    def _sa_menu_clean(label, used):
        label = ' '.join(str(label or '').split())[:50] or '?'
        base, n = label, 2
        while label in used:
            label = '%s (%d)' % (base[:45], n)
            n += 1
        used.add(label)
        return label

    # ------------------------------------------------------------------
    # Levels
    # ------------------------------------------------------------------
    def _sa_menu_show(self, level):
        self.ensure_one()
        if not (level or '').startswith(('categ', 'prod:')):
            return super()._sa_menu_show(level)
        opts, used = [], set()
        parent_level = 'main'
        if level == 'categ':
            body = _("\U0001F195 *New order* - what are you looking for? Tap a category:")
            for c in self._sa_menu_categories()[:8]:
                opts.append((self._sa_menu_clean(c.name, used), {'kind': 'menu', 'level': 'categ:%d' % c.id}))
        else:
            bits = level.split(':')
            cid = int(bits[1] or 0)
            page = int(bits[2]) if len(bits) > 2 and bits[2].isdigit() else 0
            categ = self.env['product.category'].sudo().browse(cid).exists()
            if not categ:
                return super()._sa_menu_show('main')
            parent_level = ('categ:%d' % categ.parent_id.id) if categ.parent_id and level.startswith('categ:') else 'categ'
            if level.startswith('categ:'):
                subs = self._sa_menu_categories(parent=categ)
                if subs:
                    body = _("*%s* - tap a type:") % categ.name
                    for c in subs[:6]:
                        opts.append((self._sa_menu_clean(c.name, used), {'kind': 'menu', 'level': 'categ:%d' % c.id}))
                    direct = self.env['product.template'].sudo().search_count([('categ_id', '=', categ.id), ('sale_ok', '=', True)])
                    if direct:
                        opts.append((self._sa_menu_clean(_("All %s products") % categ.name, used), {'kind': 'menu', 'level': 'prod:%d' % categ.id}))
                else:
                    level = 'prod:%d' % categ.id
            if level.startswith('prod:'):
                body = _("*%s* - tap the product you want:") % categ.name
                products, more = self._sa_menu_products(categ, page)
                if page and not products:
                    return self._sa_menu_show('prod:%d' % categ.id)
                for p in products:
                    opts.append((self._sa_menu_clean(p.name, used), {'kind': 'prodpick', 'target': p.id}))
                if more:
                    opts.append((_("➡️ MORE"), {'kind': 'menu', 'level': 'prod:%d:%d' % (categ.id, page + 1)}))
                parent_level = ('prod:%d:%d' % (categ.id, page - 1)) if page else (
                    ('categ:%d' % categ.parent_id.id) if categ.parent_id else 'categ')
        opts.append((NOT_LISTED, {'kind': 'new'}))
        if level != 'categ':
            # The top level's "back" is the main menu itself.
            opts.append((self.MENU_BACK, {'kind': 'menu', 'level': parent_level}))
        opts.append((self.MENU_MAIN, {'kind': 'menu', 'level': 'main'}))
        menu = {}
        for label, item in opts[:10]:
            item = dict(item)
            item.setdefault('req', self.id)
            item['parent'] = level
            menu[label] = item
        self.sa_menu_json = json.dumps(menu)
        self._ask(body, [{'id': 'sa_menu_%d' % i, 'title': label} for i, label in enumerate(menu)])
        return True

    # ------------------------------------------------------------------
    # Taps
    # ------------------------------------------------------------------
    def _sa_menu_tapped(self, item):
        self.ensure_one()
        kind = item.get('kind')
        parent = item.get('parent') or 'main'
        if kind == 'new' and parent == 'main':
            # NEW ORDER on the main menu: the catalogue first.
            self._sa_close_open_deals()
            return self._sa_menu_show('categ')
        if kind == 'prodpick':
            product = self.env['product.template'].sudo().browse(item.get('target') or 0).exists()
            if not product:
                return self._sa_menu_show('categ')
            self._sa_close_open_deals()
            return self._sa_menu_start_enquiry(product)
        return super()._sa_menu_tapped(item)

    def _sa_menu_start_enquiry(self, product):
        """A fresh enquiry for the tapped product, confirmed on the page like a typed one."""
        self.ensure_one()
        req = self.sudo().create({
            'group_id': self.group_id.id,
            'requester_phone': self.requester_phone or '',
            'requester_lid': self.requester_lid or '',
            'requester_name': self.requester_name or '',
            'requester_partner_id': self.requester_partner_id.id or False,
            'raw_text': product.name, 'ai_search_term': product.name,
            'product_id': product.id, 'state': 'new',
        })
        self.sudo().write({'sa_menu_json': False})
        _logger.info("Sales Automation: menu pick -> enquiry %s for %r", req.id, product.name)
        return req.with_context(sa_reply_to=self.env.context.get('sa_reply_to'))._ask_confirmation()
