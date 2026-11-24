# -*- coding: utf-8 -*-
"""NEW ORDER in the welcome menu: "what are you looking for?" first.

A shop with many categories cannot fit them in one poll (ten options at
most), so NEW ORDER asks the customer to type what they want and searches
the catalogue for it:

  NEW ORDER → 'ask': "TYPE THE PRODUCT NAME" + ORDER AGAIN / BACK / MAIN
              MENU (21 Nov 2026: POPULAR NOW and ALL CATEGORIES are no longer
              offered).
  typed word → a category whose name matches opens ('categ:<id>'); several
              matching categories are offered ('findcat'); otherwise the
              matching products, page by page ('find:<page>'), out-of-stock
              ones included and not marked (a tap on one asks the vendors).
              Nothing found → "Sorry, we couldn't find anything for X - type
              the correct product name, or hi" (22 Nov 2026).
  ALL CATEGORIES → the category tree, every level paged with MORE, so no
              category is ever left out ('categ', 'categp:<page>',
              'categ:<id>[:<page>]', 'prod:<id>[:<page>]').
  A product → a fresh enquiry for it, straight to the picture + page
              confirmation. NOT LISTED → "tell me what you need" and the
              typed flow as before.

Typed words count as a search while the customer is on one of these screens
(`sa_menu_ask_at`, 15 minutes); after that typing is the ordinary flow again.
"""
import json
import logging
from datetime import timedelta

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

NOT_LISTED = "✏️ NOT LISTED"
MORE = "➡️ MORE"
ORDER_AGAIN = "\U0001F501 ORDER AGAIN"
POPULAR = "⭐ POPULAR NOW"
ALL_CATEGORIES = "\U0001F4C2 ALL CATEGORIES"

# Levels drawn here. Anything else goes up the stack (main, orders, more ...).
CATALOG_LEVELS = ('ask', 'categ', 'prod:', 'find', 'again', 'popular')
# How long after the last catalogue screen typed words are read as a search.
SEARCH_MINUTES = 15


class ProductCategoryMenu(models.Model):
    _inherit = 'product.category'

    sa_menu_sequence = fields.Integer('WhatsApp menu order', default=100,
                                      help="Lower comes first in the NEW ORDER category list.")
    sa_menu_hide = fields.Boolean('Hide from the WhatsApp menu', default=False,
                                  help="Test or internal categories: never listed under NEW ORDER (typed requests still work).")


class SaGroupRequestMenuCategories(models.Model):
    _inherit = 'sa.group.request'

    sa_menu_term = fields.Char(
        'Last menu search', readonly=True, copy=False,
        help="What the customer last typed after NEW ORDER - kept so MORE "
             "can page through the results.")
    sa_menu_handed_at = fields.Datetime(readonly=True, copy=False, help="When a menu search was handed to the ordinary enquiry.")
    sa_menu_ask_at = fields.Datetime(
        'Menu search open since', readonly=True, copy=False,
        help="Set while the customer is on a NEW ORDER screen: what they type "
             "then is searched in the catalogue. Cleared when they leave it.")

    # ------------------------------------------------------------------
    # What to list
    # ------------------------------------------------------------------
    PAGE = 6            # products per page
    CATEG_PAGE = 6      # top-level categories per page
    SUB_PAGE = 5        # sub-categories per page (an "All ... products" row may follow)

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

    @api.model
    def _sa_menu_products(self, categ, page=0):
        """(products on this page, more pages after it)"""
        Prod = self.env['product.template'].sudo()
        # A product that may not be sold short and has no free stock is left
        # out (a domain, so the pages stay right).
        rows = Prod.search([('categ_id', 'child_of', categ.id), ('sale_ok', '=', True)] + self._sa_unsellable_domain(),
                           order='name', offset=page * self.PAGE, limit=self.PAGE + 1)
        return rows[:self.PAGE], len(rows) > self.PAGE

    @api.model
    def _sa_menu_product_domain(self):
        """What the search, ORDER AGAIN and POPULAR may offer. The storefront
        bridge narrows it to published products."""
        return [('sale_ok', '=', True), ('active', '=', True)] + self._sa_unsellable_domain()

    def _sa_menu_company_domain(self):
        company = self._company_for(self.group_id) if self.group_id else self.env.company
        return ['|', ('company_id', '=', False), ('company_id', '=', company.id)]

    def _sa_menu_find_products(self, term, page=0):
        """(products matching the typed words on this page, more after it).

        Every word has to appear in the name, the internal reference or the
        category, so "hp laptop" finds HP laptops and not every HP product.
        Nothing that way → the spacing-blind search ("powerbank" finds
        "Power Bank"), which has no pages.
        """
        self.ensure_one()
        Prod = self.env['product.template'].sudo()
        base = self._sa_menu_product_domain() + self._sa_menu_company_domain()
        words = sorted(self._sa_words(term))
        if words:
            domain = list(base)
            for w in words:
                domain += ['|', '|', ('name', 'ilike', w), ('default_code', 'ilike', w),
                           ('categ_id.complete_name', 'ilike', w)]
            rows = Prod.search(domain, order='name', offset=page * self.PAGE, limit=self.PAGE + 1)
            if rows or page:
                return rows[:self.PAGE], len(rows) > self.PAGE
        loose = self._search_products_loose(term)
        if loose:
            loose = Prod.search([('id', 'in', loose.ids)] + base, order='name', limit=self.PAGE)
        return loose, False

    @api.model
    def _sa_menu_find_categories(self, term):
        """Listed categories whose name is the typed word ("laptop",
        "laptops", "mobile cover"). An exact name comes alone."""
        term = ' '.join((term or '').split())
        if len(term) < 3 or len(term) > 40:
            return self.env['product.category']
        Categ = self.env['product.category'].sudo()
        names = [term]
        if term.lower().endswith('s') and len(term) > 3:
            names.append(term[:-1])
        domain = ['|'] * (len(names) - 1) + [('name', 'ilike', n) for n in names]
        hits = Categ.search([('sa_menu_hide', '=', False)] + domain, order='sa_menu_sequence, name', limit=30)
        Prod = self.env['product.template'].sudo()
        prod_domain = self._sa_menu_product_domain()
        listed = Categ
        for c in hits:
            # A hidden parent hides the whole branch.
            if Categ.search_count([('id', 'parent_of', c.id), ('sa_menu_hide', '=', True)]):
                continue
            if getattr(c, 'sa_vendor_ids', False) or Prod.search_count(
                    [('categ_id', 'child_of', c.id)] + prod_domain, limit=1):
                listed |= c
        exact = listed.filtered(lambda c: (c.name or '').strip().lower() in [n.lower() for n in names])
        return exact[:1] if len(exact) == 1 else listed

    def _sa_menu_sender_domain(self):
        digits = ''.join(c for c in (self.requester_phone or '') if c.isdigit())
        tail = digits[-9:] if len(digits) >= 9 else ''
        lid = self.requester_lid or ''
        if tail and lid:
            return ['|', ('requester_phone', 'like', tail), ('requester_lid', '=', lid)]
        if tail:
            return [('requester_phone', 'like', tail)]
        if lid:
            return [('requester_lid', '=', lid)]
        return None

    def _sa_menu_again_products(self):
        """What this customer ordered before, newest first, once each."""
        self.ensure_one()
        who = self._sa_menu_sender_domain()
        if who is None:
            return self.env['product.template']
        past = self.sudo().search([('group_id', '=', self.group_id.id), ('state', '=', 'order_created'),
                                   ('product_id', '!=', False)] + who, order='id desc', limit=60)
        seen = []
        for r in past:
            if r.product_id.id not in seen:
                seen.append(r.product_id.id)
        if not seen:
            return self.env['product.template']
        Prod = self.env['product.template'].sudo()
        ok = set(Prod.search([('id', 'in', seen)] + self._sa_menu_product_domain()).ids)
        return Prod.browse([pid for pid in seen if pid in ok][:self.PAGE])

    def _sa_menu_popular_products(self):
        """The most-ordered products of the last 60 days."""
        self.ensure_one()
        since = fields.Datetime.now() - timedelta(days=60)
        groups = self.sudo()._read_group(
            [('state', '=', 'order_created'), ('product_id', '!=', False), ('create_date', '>=', since)],
            groupby=['product_id'], aggregates=['__count'], order='__count desc', limit=40)
        ranked = [product.id for product, __ in groups]
        if not ranked:
            return self.env['product.template']
        Prod = self.env['product.template'].sudo()
        ok = set(Prod.search([('id', 'in', ranked)] + self._sa_menu_product_domain()
                             + self._sa_menu_company_domain()).ids)
        return Prod.browse([pid for pid in ranked if pid in ok][:self.PAGE])

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
    def _sa_menu_post(self, level, body, opts):
        """Keep the options (by label) and post the poll - ten options at most."""
        menu = {}
        for label, item in opts[:10]:
            item = dict(item)
            item.setdefault('req', self.id)
            item['parent'] = level
            menu[label] = item
        self.sa_menu_json = json.dumps(menu)
        self._ask(body, [{'id': 'sa_menu_%d' % i, 'title': label} for i, label in enumerate(menu)])
        return True

    def _sa_all_stock(self):
        """These screens list out-of-stock products too; a tap on one asks the
        vendors (owner, 22 Nov 2026). Nothing says "in stock" or "out of
        stock" next to the names."""
        return self.with_context(sa_menu_all_stock=True)

    def _sa_menu_show(self, level):
        self.ensure_one()
        self = self._sa_all_stock()
        level = level or ''
        if level == 'main':
            # "...or just type the product you need": a word typed at the main
            # menu is searched straight away, no NEW ORDER tap needed.
            self.sudo().write({'sa_menu_ask_at': fields.Datetime.now()})
            return super()._sa_menu_show(level)
        if not level.startswith(CATALOG_LEVELS):
            # Off the catalogue: typed words are no longer a search.
            if self.sa_menu_ask_at:
                self.sudo().write({'sa_menu_ask_at': False})
            return super()._sa_menu_show(level)
        self.sudo().write({'sa_menu_ask_at': fields.Datetime.now()})
        if level == 'ask':
            return self._sa_menu_show_ask()
        if level == 'categ' or level.startswith('categp:'):
            return self._sa_menu_show_top(int(level.split(':')[1]) if ':' in level else 0)
        if level.startswith('find:'):
            return self._sa_menu_show_find(int(level.split(':')[1] or 0))
        if level == 'findcat':
            return self._sa_menu_show_findcat()
        if level in ('again', 'popular'):
            return self._sa_menu_show_shortlist(level)
        return self._sa_menu_show_branch(level)

    def _sa_menu_ask_note(self):
        """A line above "what are you looking for?" (the cart says what is in it)."""
        return ''

    def _sa_menu_show_ask(self):
        # Owner, 21 Nov 2026: the typing line stands out, and the screen is
        # always a poll - ORDER AGAIN when there is something, then BACK and
        # MAIN MENU (a poll needs two options). No POPULAR NOW, no ALL
        # CATEGORIES: the customer types what they want.
        body = _("\U0001F195 *New order* - what are you looking for?\n\n"
                 "✍️ *TYPE THE PRODUCT NAME* \U0001F447\n"
                 "for example *laptop*, *headphones* or *iPhone 15*\n\n"
                 "Or tap one:")
        note = self._sa_menu_ask_note()
        if note:
            body = '%s\n\n%s' % (note, body)
        opts = []
        if self._sa_menu_again_products():
            opts.append((ORDER_AGAIN, {'kind': 'menu', 'level': 'again'}))
        opts.append((self.MENU_BACK, {'kind': 'menu', 'level': 'main'}))
        opts.append((self.MENU_MAIN, {'kind': 'menu', 'level': 'main'}))
        return self._sa_menu_post('ask', body, opts)

    def _sa_menu_show_top(self, page):
        level = 'categp:%d' % page if page else 'categ'
        cats = self._sa_menu_categories()
        start = page * self.CATEG_PAGE
        if page and start >= len(cats):
            return self._sa_menu_show_top(0)
        used, opts = set(), []
        for c in cats[start:start + self.CATEG_PAGE]:
            opts.append((self._sa_menu_clean(c.name, used), {'kind': 'menu', 'level': 'categ:%d' % c.id}))
        if len(cats) > start + self.CATEG_PAGE:
            opts.append((MORE, {'kind': 'menu', 'level': 'categp:%d' % (page + 1)}))
        opts.append((NOT_LISTED, {'kind': 'new'}))
        back = ('categp:%d' % (page - 1) if page > 1 else 'categ') if page else 'ask'
        opts.append((self.MENU_BACK, {'kind': 'menu', 'level': back}))
        opts.append((self.MENU_MAIN, {'kind': 'menu', 'level': 'main'}))
        pages = (len(cats) + self.CATEG_PAGE - 1) // self.CATEG_PAGE
        body = _("\U0001F4C2 *Categories* - tap one (or just type what you need):")
        if pages > 1:
            body = _("\U0001F4C2 *Categories* (%(page)d/%(pages)d) - tap one (or just type what you need):",
                     page=page + 1, pages=pages)
        return self._sa_menu_post(level, body, opts)

    def _sa_menu_product_opts(self, products, used):
        return [(self._sa_menu_clean(p.name, used), {'kind': 'prodpick', 'target': p.id}) for p in products]

    def _sa_menu_show_find(self, page):
        term = self.sa_menu_term or ''
        products, more = self._sa_menu_find_products(term, page)
        if page and not products:
            return self._sa_menu_show_find(0)
        used = set()
        opts = self._sa_menu_product_opts(products, used)
        if more:
            opts.append((MORE, {'kind': 'menu', 'level': 'find:%d' % (page + 1)}))
        opts.append((NOT_LISTED, {'kind': 'new'}))
        # ⬅ BACK on the first page too (22 Nov 2026): back to "what are you
        # looking for?".
        opts.append((self.MENU_BACK, {'kind': 'menu', 'level': 'find:%d' % (page - 1) if page else 'ask'}))
        opts.append((self.MENU_MAIN, {'kind': 'menu', 'level': 'main'}))
        body = _("\U0001F50E Found for *%s* - tap the one you want (or type another word):") % term
        return self._sa_menu_post('find:%d' % page, body, opts)

    def _sa_menu_show_findcat(self):
        term = self.sa_menu_term or ''
        cats = self._sa_menu_find_categories(term)
        if not cats:
            return self._sa_menu_show_find(0)
        used, opts = set(), []
        for c in cats[:6]:
            opts.append((self._sa_menu_clean(c.complete_name or c.name, used),
                         {'kind': 'menu', 'level': 'categ:%d' % c.id}))
        if self._sa_menu_find_products(term, 0)[0]:
            opts.append((self._sa_menu_clean(_("\U0001F50E ALL \"%s\" PRODUCTS") % term.upper()[:30], used),
                         {'kind': 'menu', 'level': 'find:0'}))
        opts.append((NOT_LISTED, {'kind': 'new'}))
        opts.append((self.MENU_BACK, {'kind': 'menu', 'level': 'ask'}))
        opts.append((self.MENU_MAIN, {'kind': 'menu', 'level': 'main'}))
        body = _("\U0001F50E *%s* - which one? Tap it (or type another word):") % term
        return self._sa_menu_post('findcat', body, opts)

    def _sa_menu_show_shortlist(self, level):
        if level == 'again':
            products = self._sa_menu_again_products()
            body = _("\U0001F501 *Order again* - tap the product you want:")
        else:
            products = self._sa_menu_popular_products()
            body = _("⭐ *Popular now* - tap the product you want:")
        if not products:
            return self._sa_menu_show_ask()
        opts = self._sa_menu_product_opts(products, set())
        opts.append((NOT_LISTED, {'kind': 'new'}))
        opts.append((self.MENU_BACK, {'kind': 'menu', 'level': 'ask'}))
        opts.append((self.MENU_MAIN, {'kind': 'menu', 'level': 'main'}))
        return self._sa_menu_post(level, body, opts)

    def _sa_menu_show_branch(self, level):
        """'categ:<id>[:<page>]' (its sub-categories, or its products) and
        'prod:<id>[:<page>]' (its products)."""
        bits = level.split(':')
        cid = int(bits[1]) if len(bits) > 1 and bits[1].isdigit() else 0
        page = int(bits[2]) if len(bits) > 2 and bits[2].isdigit() else 0
        categ = self.env['product.category'].sudo().browse(cid).exists()
        if not categ:
            return self._sa_menu_show_ask()
        # a top category goes BACK to "what are you looking for?" - the full
        # category list is no longer offered (21 Nov 2026)
        up = ('categ:%d' % categ.parent_id.id) if categ.parent_id else 'ask'
        used, opts = set(), []
        if level.startswith('categ:'):
            subs = self._sa_menu_categories(parent=categ)
            start = page * self.SUB_PAGE
            if page and start >= len(subs):
                return self._sa_menu_show_branch('categ:%d' % categ.id)
            if subs:
                body = _("*%s* - tap a type:") % categ.name
                for c in subs[start:start + self.SUB_PAGE]:
                    opts.append((self._sa_menu_clean(c.name, used), {'kind': 'menu', 'level': 'categ:%d' % c.id}))
                if not page:
                    direct = self.env['product.template'].sudo().search_count(
                        [('categ_id', '=', categ.id), ('sale_ok', '=', True)])
                    if direct:
                        opts.append((self._sa_menu_clean(_("All %s products") % categ.name, used),
                                     {'kind': 'menu', 'level': 'prod:%d' % categ.id}))
                if len(subs) > start + self.SUB_PAGE:
                    opts.append((MORE, {'kind': 'menu', 'level': 'categ:%d:%d' % (categ.id, page + 1)}))
                back = ('categ:%d:%d' % (categ.id, page - 1)) if page else up
                level = 'categ:%d:%d' % (categ.id, page) if page else 'categ:%d' % categ.id
            else:
                level, page = 'prod:%d' % categ.id, 0
        if level.startswith('prod:'):
            body = _("*%s* - tap the product you want:") % categ.name
            products, more = self._sa_menu_products(categ, page)
            if page and not products:
                return self._sa_menu_show_branch('prod:%d' % categ.id)
            opts += self._sa_menu_product_opts(products, used)
            if more:
                opts.append((MORE, {'kind': 'menu', 'level': 'prod:%d:%d' % (categ.id, page + 1)}))
            back = ('prod:%d:%d' % (categ.id, page - 1)) if page else up
        opts.append((NOT_LISTED, {'kind': 'new'}))
        opts.append((self.MENU_BACK, {'kind': 'menu', 'level': back}))
        opts.append((self.MENU_MAIN, {'kind': 'menu', 'level': 'main'}))
        return self._sa_menu_post(level, body, opts)

    # ------------------------------------------------------------------
    # Taps
    # ------------------------------------------------------------------
    def _sa_menu_tapped(self, item):
        self.ensure_one()
        kind = item.get('kind')
        parent = item.get('parent') or 'main'
        if kind == 'new' and parent == 'main':
            # NEW ORDER on the main menu: "what are you looking for?" first.
            self._sa_close_open_deals()
            return self._sa_menu_show('ask')
        if kind == 'new':
            # NOT LISTED: what they type next is the ordinary enquiry, which
            # asks the vendors - not another catalogue search.
            self.sudo().write({'sa_menu_ask_at': False})
        if kind == 'prodpick':
            product = self.env['product.template'].sudo().browse(item.get('target') or 0).exists()
            if not product:
                return self._sa_menu_show('ask')
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
            # picked from the menu: out of stock is sourced, not refused
            # (`_assess_availability` below)
            'ai_source': 'menu',
        })
        self.sudo().write({'sa_menu_json': False, 'sa_menu_ask_at': False})
        _logger.info("Sales Automation: menu pick -> enquiry %s for %r", req.id, product.name)
        return req.with_context(sa_reply_to=self.env.context.get('sa_reply_to'))._ask_confirmation()

    # ------------------------------------------------------------------
    # Typed words while on a NEW ORDER screen
    # ------------------------------------------------------------------
    @api.model
    def _sa_typed_answer_hook(self, group, message, text):
        """A word typed on a NEW ORDER screen is searched in the catalogue."""
        res = super()._sa_typed_answer_hook(group, message, text)
        if res is not None:
            return res
        since = fields.Datetime.now() - timedelta(minutes=SEARCH_MINUTES)
        open_ = self.sudo().search([('group_id', '=', group.id), ('sa_menu_ask_at', '>=', since)],
                                   order='sa_menu_ask_at desc, id desc', limit=10)
        for req in open_:
            if req._sa_asked_of(message):
                return req._sa_menu_typed(text)
        return None

    def _sa_menu_typed(self, text):
        """True when the words were answered from the catalogue; None hands
        them on to the ordinary typed enquiry."""
        self.ensure_one()
        # A poll option typed out (the poll id went missing) is that tap.
        label = self._sa_menu_label(text)
        if label:
            return self._sa_menu_tapped(json.loads(self.sa_menu_json)[label])
        if self._sa_is_bare_answer(text) or self._sa_is_greeting(text):
            return None
        term = ' '.join((text or '').split())[:80]
        shown = self._sa_menu_search_show(term)
        if shown is not None:
            return shown
        # A typo ("latop"): the nearest words the shop sells, once.
        fixed = self._sa_menu_spell(term)
        if fixed:
            shown = self._sa_menu_search_show(fixed)
            if shown is not None:
                _logger.info("Sales Automation: menu search %r read as %r", term, fixed)
                return shown
        # Nothing found (out-of-stock products are listed, so this is not in
        # the catalogue): "couldn't find - type the correct product name, or
        # hi" (owner, 22 Nov 2026). The search stays open for the next try.
        # In the catalogue but not on the menu (not published on the website):
        # the ordinary enquiry, which asks the vendors. Between 22 and 23 Nov
        # 2026 these were told "couldn't find" (5,849 of 8,067 products).
        if self._sa_listed_unshown(term):
            self.sudo().write({'sa_menu_ask_at': False, 'sa_menu_handed_at': fields.Datetime.now()})
            _logger.info("Sales Automation: menu search %r is not on the menu - typed enquiry", term)
            return None
        self.sudo().write({'sa_menu_ask_at': fields.Datetime.now()})
        return self._sa_say_not_found(term)

    def _drop(self, reason):
        """Handed over by the menu and then "no product" ("mh" is inside "MHz"):
        the customer is on our menu, so silence is wrong (24 Nov 2026). The
        menu search is open again for the next words."""
        res = super()._drop(reason)
        if reason != 'not_product' or not self.group_id:
            return res
        since = fields.Datetime.now() - timedelta(minutes=2)
        mine = self._sa_id_tail(self.requester_phone)
        for menu in self.sudo().search([('group_id', '=', self.group_id.id), ('sa_menu_handed_at', '>=', since), ('id', '!=', self.id)],
                                       order='sa_menu_handed_at desc, id desc', limit=10):
            same = mine == self._sa_id_tail(menu.requester_phone) if mine else (
                self.requester_lid and self.requester_lid == menu.requester_lid)
            if same:
                menu.write({'sa_menu_handed_at': False, 'sa_menu_ask_at': fields.Datetime.now()})
                if self._settings().chatter_action != 'reply':      # else it was answered already
                    self._sa_say_not_found(self.raw_text)
                break
        return res

    def _sa_listed_unshown(self, term):
        """A sellable product of this company has every typed word in its name,
        reference or category. Stricter than `_sa_catalog_has` on purpose: a
        near miss or a sentence stays "couldn't find"."""
        self.ensure_one()
        return bool(self._sa_listed_ids(term, 1))

    def _finder_start(self):
        """A typed word goes through the shop's own categories first (owner,
        22 Nov 2026), for any word - laptop, toner, CCTV, mouse:
        a category with sub-categories (Laptop › Dell / HP) is a poll of
        those, one without is its products, and with no category the
        products whose names match are listed directly. No brand is guessed
        from product names. The guided finder (brand, then model) stays the
        fallback for what these screens cannot show - a product that is out
        of stock, or nothing on the shelf at all."""
        self.ensure_one()
        self = self._sa_all_stock()
        term = ' '.join((self.ai_search_term or self.raw_text or '').split())[:80]
        if self.group_id and len(term) >= 3:
            cats = self._sa_menu_find_categories(term)
            stocked = cats.filtered(lambda c: self._sa_menu_products(c)[0]) if cats else cats
            if stocked or self._sa_menu_find_products(term, 0)[0]:
                self._ensure_conversation()
                self.sudo().write({'sa_menu_ask_at': fields.Datetime.now()})
                if self._sa_menu_search_show(term) is not None:
                    _logger.info("Sales Automation: enquiry %s - %r shown from the shop's categories",
                                 self.id, term)
                    return True
                self.sudo().write({'sa_menu_ask_at': False})
        return super()._finder_start()

    def _sa_menu_search_show(self, term):
        """Show what `term` finds - a category, a choice of categories, or the
        products. None when it finds nothing."""
        self.ensure_one()
        self = self._sa_all_stock()
        self.sudo().write({'sa_menu_term': term})
        cats = self._sa_menu_find_categories(term)
        if len(cats) == 1:
            _logger.info("Sales Automation: menu search %r -> category %s", term, cats.name)
            return self._sa_menu_show('categ:%d' % cats.id)
        if cats:
            return self._sa_menu_show('findcat')
        if self._sa_menu_find_products(term, 0)[0]:
            return self._sa_menu_show('find:0')
        return None

    def _sa_menu_spell(self, term):
        """`term` with misspelt words replaced by the closest word the shop
        sells ("latop" → "laptop"); '' when nothing changed."""
        self.ensure_one()
        import difflib
        words = (term or '').split()
        if not words:
            return ''
        vocab = set(self._sa_catalog_vocabulary())
        for c in self._sa_menu_find_categories_all():
            vocab |= {w for w in self._sa_words(c.name or '') if len(w) >= 4}
        if not vocab:
            return ''
        vocab = sorted(vocab)
        out, changed = [], False
        for word in words:
            bare = word.strip('.,!?:;()*_-/').lower()
            if len(bare) >= 4 and bare not in vocab:
                hit = difflib.get_close_matches(bare, vocab, n=1, cutoff=0.75)
                if hit:
                    out.append(hit[0])
                    changed = True
                    continue
            out.append(word)
        return ' '.join(out) if changed else ''

    def _sa_name_typed_ok(self, text, pending):
        """"What should we call you?" answered with a product - misspelt too
        ("latop") - is an enquiry, not a name."""
        ok = super()._sa_name_typed_ok(text, pending)
        if ok and pending == 'ask':
            clean = ' '.join((text or '').split())
            try:
                if self._sa_all_stock()._sa_menu_find_categories(clean) or self._sa_menu_spell(clean):
                    return False
            except Exception as err:  # noqa: BLE001 - the name question still works
                _logger.info("Sales Automation: name check for %r skipped: %s", clean, err)
        return ok

    # ------------------------------------------------------------------
    # While an order waits for its details (sa_group_details.py)
    # ------------------------------------------------------------------
    @api.model
    def _sa_details_menu_newer(self, waiting, message):
        """This sender opened the menu / NEW ORDER (or was shown the
        catalogue) after the details question went out, in the last
        SEARCH_MINUTES: what they type is a search, not an answer."""
        floor = fields.Datetime.now() - timedelta(minutes=SEARCH_MINUTES)
        if waiting.profile_asked_on and waiting.profile_asked_on > floor:
            floor = waiting.profile_asked_on
        rows = self.sudo().search([('group_id', '=', waiting.group_id.id),
                                   ('sa_menu_ask_at', '>', floor)],
                                  order='sa_menu_ask_at desc, id desc', limit=10)
        return any(r._sa_asked_of(message) for r in rows)

    def _sa_menu_host(self):
        """A row of this customer's to post catalogue screens from - never the
        waiting order itself: every screen is a poll, and the order keeps only
        its last few poll ids, so its YES / NO poll would be pushed out. Like
        the first-hello row of `_sa_returning_menu`: closed, so nothing reads
        it as a request."""
        self.ensure_one()
        who = self._sa_menu_sender_domain()
        if who is not None:
            since = fields.Datetime.now() - timedelta(days=1)
            host = self.sudo().search([('group_id', '=', self.group_id.id), ('state', '=', 'dropped'),
                                       ('order_id', '=', False), ('create_date', '>=', since)] + who,
                                      order='id desc', limit=1)
            if host:
                return host
        return self.sudo().create({
            'group_id': self.group_id.id,
            'requester_phone': self.requester_phone or '',
            'requester_lid': self.requester_lid or '',
            'requester_name': self.requester_name or '',
            'requester_is_lid': self.requester_is_lid,
            'requester_partner_id': self.requester_partner_id.id or False,
            'raw_text': self.raw_text or '',
            'currency_id': self._company_for(self.group_id).currency_id.id,
            'state': 'dropped', 'drop_reason': 'not_product', 'ai_source': 'prefilter',
        })

    def _sa_details_catalog_show(self, term):
        """A product word typed on the details read-back: its catalogue
        screens, from the customer's menu row; the order keeps waiting."""
        self.ensure_one()
        host = self._sa_menu_host().with_context(sa_reply_to=self.env.context.get('sa_reply_to'),
                                                  sa_trigger_msg=self.env.context.get('sa_trigger_msg'))
        if self._sa_is_bare_answer(term) or self._sa_is_greeting(term):
            return None
        shown = host._sa_menu_search_show(term)
        if shown is not None:
            return shown
        fixed = host._sa_menu_spell(term)
        if fixed:
            shown = host._sa_menu_search_show(fixed)
            if shown is not None:
                _logger.info("Sales Automation: details-time search %r read as %r", term, fixed)
                return shown
        # the retry ("type the correct product name") is a search too
        host.sudo().write({'sa_menu_ask_at': fields.Datetime.now()})
        return None

    def _assess_availability(self, product, fresh=False):
        """Picked from the menu and out of stock: sellable - it is bought in
        from the vendors (owner, 22 Nov 2026), not refused."""
        sellable = super()._assess_availability(product, fresh=fresh)
        if not sellable and self.ai_source == 'menu':
            _logger.info("Sales Automation: enquiry %s - %s is out of stock, the vendors are asked",
                         self.id, product.display_name)
            return True
        return sellable

    @api.model
    def _sa_menu_find_categories_all(self):
        """Every category the menu could list, at any level (for spelling)."""
        Categ = self.env['product.category'].sudo()
        return Categ.search([('sa_menu_hide', '=', False)], limit=500)
