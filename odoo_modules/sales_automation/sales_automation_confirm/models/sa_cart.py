# -*- coding: utf-8 -*-
"""Several items in one order: "➕ ADD ANOTHER ITEM" at the order summary.

One enquiry is still one product. At the order summary the customer can tap
ADD ANOTHER ITEM instead of CONFIRM: the item waits in their cart (state
`in_cart`) and they are asked "what are you looking for?" again. The next
item goes through the usual steps - search, variant, the ACCEPT page, price,
quantity - and its summary lists the whole cart. CONFIRM then raises ONE
order: the confirming enquiry creates it as before (it is the order's lead -
signature, payment and delivery all follow it) and every cart item is added
as a line of the same order, at its own price and quantity
(`_sa_order_extra_lines`, called by `_place_order` before the stock check,
the "Done!" and the details).

A cart item is kept for six hours; a cancel before CONFIRM clears the cart.
"""
import json
import logging
from datetime import timedelta

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

ADD_ITEM = "➕ ADD ANOTHER ITEM"
CART_HOURS = 6
CART_REMOVE = "➖ REMOVE AN ITEM"
CART_ALL = "✅ ALL ITEMS"
CART_BACK = "⬅ BACK"


class SaGroupRequestCart(models.Model):
    _inherit = 'sa.group.request'

    state = fields.Selection(selection_add=[('in_cart', 'In Cart')],
                             ondelete={'in_cart': 'set default'})
    sa_cart_queue = fields.Char(
        'Cart Items Still to Change', copy=False,
        help="ALL ITEMS on CHANGE QUANTITY / BETTER PRICE: the summary rows "
             "still to ask, as JSON lists of enquiry ids.")
    sa_cart_act = fields.Char('Cart Change Under Way', copy=False)

    # ------------------------------------------------------------------
    # The cart
    # ------------------------------------------------------------------
    def _sa_cart_items(self, include_self=False):
        """This customer's items waiting in the cart (this group, last six
        hours), oldest first."""
        self.ensure_one()
        who = self._sa_menu_sender_domain()
        if who is None or not self.group_id:
            return self.browse()
        since = fields.Datetime.now() - timedelta(hours=CART_HOURS)
        domain = [('group_id', '=', self.group_id.id), ('state', '=', 'in_cart'),
                  ('write_date', '>=', since)] + who
        if not include_self:
            domain.append(('id', '!=', self.id))
        return self.sudo().search(domain, order='id')

    def _sa_cart_name(self):
        self.ensure_one()
        if getattr(self, 'sa_variant_id', False) and hasattr(self, '_sa_variant_name'):
            return self._sa_variant_name() or self.product_id.name
        return self.product_id.name or self.ai_search_term or _("item")

    @staticmethod
    def _sa_cart_qty(qty):
        qty = qty or 1
        return int(qty) if float(qty).is_integer() else qty

    def _sa_cart_price(self):
        self.ensure_one()
        return self.agreed_price or self.quoted_price or 0.0

    def _sa_cart_variant(self):
        self.ensure_one()
        variant = self.sa_variant_id if 'sa_variant_id' in self._fields else False
        return variant or self.product_id.product_variant_id

    def _sa_cart_key(self):
        """The same item: the same variant at the same price. A different
        price (bargained) stays its own line."""
        self.ensure_one()
        return (self._sa_cart_variant().id, round(float(self._sa_cart_price()), 2))

    def _sa_menu_ask_note(self):
        items = self._sa_cart_items(include_self=True)
        if not items:
            return super()._sa_menu_ask_note()
        return _("\U0001F6D2 *Your cart* (%(n)d):\n%(lines)s",
                 n=len(items),
                 lines='\n'.join('• %s x %s' % (r._sa_cart_name(), self._sa_cart_qty(r.qty)) for r in items))

    # ------------------------------------------------------------------
    # The order summary: CONFIRM / ADD ANOTHER ITEM / CHANGE
    # ------------------------------------------------------------------
    def _ask_order_confirm(self):
        self.ensure_one()
        if self.order_id:
            # The "goods arrived" confirm of an existing order keeps its own.
            return super()._ask_order_confirm()
        if self.sa_cart_queue:
            # ALL ITEMS: this item is done, the next one is asked first.
            try:
                queue = json.loads(self.sa_cart_queue) or []
            except ValueError:
                queue = []
            self.sudo().write({'sa_cart_queue': False})
            if queue:
                act = self.sa_cart_act
                self.sudo().write({'state': 'in_cart', 'sa_cart_act': False})
                return self._sa_cart_focus_from(queue, act)
        if self.sa_cart_act:
            self.sudo().write({'sa_cart_act': False})
        items = self._sa_cart_items()
        price, qty = self._sa_cart_price(), self.qty or 1
        if items:
            # The same variant at the same price is one row, its quantities added.
            merged = {}
            for r in list(items) + [self]:
                row = merged.setdefault(r._sa_cart_key(), [r._sa_cart_name(), 0.0, r._sa_cart_price()])
                row[1] += r.qty or 1
            rows, total = [], 0.0
            for i, (name, q, p) in enumerate(merged.values(), 1):
                total += p * q
                rows.append('%d. %s x %s = %.2f' % (i, name, self._sa_cart_qty(q), p * q))
            body = _("\U0001F6D2 *Your order*\n\n%(rows)s\n\n*Total: %(total).2f*",
                     rows='\n'.join(rows), total=total)
        else:
            body = _("\U0001F4CB *Order summary*\n\n%(product)s\n%(qty)s x "
                     "%(price).2f\n*Total: %(total).2f*",
                     product=self._sa_cart_name(), qty=self._sa_cart_qty(qty),
                     price=price, total=price * qty)
        self._ask(body, [{'id': 'sa_yes', 'title': _('CONFIRM')},
                         {'id': 'sa_cart', 'title': ADD_ITEM},
                         {'id': 'sa_no', 'title': _('CHANGE')}])
        self.state = 'awaiting_order_confirm'
        return True

    def _sa_is_cart_add(self, text):
        key = self._sa_menu_key(text)
        return key in (self._sa_menu_key(ADD_ITEM), 'sacart', 'addanother', 'addmore', 'addanitem', 'additem')

    def _on_deal_reply(self, text):
        if self.state == 'awaiting_order_confirm' and not self.order_id and self._sa_is_cart_add(text):
            return self._sa_cart_add()
        if not self.order_id and self._sa_is_step_back(text):
            if self.state == 'awaiting_qty':
                return self._sa_back_to_price()
            if self.state in ('quoted', 'negotiating'):
                return self._sa_back_to_search()
        return super()._on_deal_reply(text)

    # ------------------------------------------------------------------
    # ⬅ BACK on every step (owner, 22 Nov 2026)
    # ------------------------------------------------------------------
    def _sa_is_step_back(self, text):
        return self._sa_menu_key(text) in (self._sa_menu_key(self.MENU_BACK), 'back', 'goback')

    def _sa_deal_options(self, allow_bargain=True):
        """ACCEPT / BETTER PRICE / CANCEL, and ⬅ BACK to choose another
        product."""
        options = super()._sa_deal_options(allow_bargain=allow_bargain)
        if not self.order_id:
            options.append({'id': 'sa_back', 'title': self.MENU_BACK})
        return options

    def _sa_ask_qty_poll(self, body):
        """1-6 / Other amount, and ⬅ BACK to the price."""
        self.ensure_one()
        if self.order_id:
            return super()._sa_ask_qty_poll(body)
        opts = [{'id': 'sa_qty_%d' % n, 'title': str(n)} for n in range(1, 7)]
        opts.append({'id': 'sa_qty_other', 'title': self.QTY_OTHER})
        opts.append({'id': 'sa_qty_back', 'title': self.MENU_BACK})
        self.state = 'awaiting_qty'
        return self._ask(body, opts)

    def _sa_back_to_price(self):
        """BACK on "how many?": the price again, with its answers."""
        self.ensure_one()
        price = self.agreed_price or self.quoted_price
        name = self._sa_cart_name()
        self.state = 'quoted'
        self._ask(_("\U0001F4E6 *%(product)s*\n\U0001F4B0 *%(price).2f*", product=name, price=price),
                  self._sa_deal_options())
        return True

    def _sa_back_to_search(self):
        """BACK on a product's own steps: this one is left, and the customer
        chooses again ("what are you looking for?"); the cart stays."""
        self.ensure_one()
        _logger.info("Sales Automation: enquiry %s - BACK, choosing another product", self.id)
        # The enquiry itself becomes the NEW ORDER screen again (a menu holder
        # is an enquiry in state 'new', as NEW ORDER from the main menu).
        vals = {'state': 'new', 'product_id': False, 'qty': 0, 'quoted_price': 0.0,
                'agreed_price': 0.0, 'bargain_count': 0, 'sa_menu_json': False,
                'sa_change_pending': False}
        if 'sa_variant_id' in self._fields:
            vals['sa_variant_id'] = False
        self.sudo().write(vals)
        return self._sa_menu_show('ask')

    def _sa_cart_add(self):
        """This item waits in the cart; ask for the next one."""
        self.ensure_one()
        same = self._sa_cart_items().filtered(lambda r: r._sa_cart_key() == self._sa_cart_key())[:1]
        if same:
            # Already in the cart: one line, the quantities added.
            total = (same.qty or 1) + (self.qty or 1)
            same.sudo().write({'qty': total})
            self.sudo().write({'state': 'dropped', 'drop_reason': 'stale', 'sa_menu_json': False})
            _logger.info("Sales Automation: enquiry %s merged into cart item %s (now x %s)",
                         self.id, same.id, total)
            self._say(_("\U0001F6D2 Added %(qty)s more: *%(item)s* - now x %(total)s in your cart",
                        qty=self._sa_cart_qty(self.qty), item=same._sa_cart_name(),
                        total=self._sa_cart_qty(total)))
            return same._sa_menu_show('ask')
        self.sudo().write({'state': 'in_cart', 'sa_menu_json': False})
        _logger.info("Sales Automation: enquiry %s (%s x %s) put in the cart", self.id,
                     self._sa_cart_name(), self.qty)
        self._say(_("\U0001F6D2 Added to your cart: *%(item)s* x %(qty)s",
                    item=self._sa_cart_name(), qty=self._sa_cart_qty(self.qty)))
        return self._sa_menu_show('ask')

    def _sa_menu_typed(self, text):
        """"cancel" typed while adding to the cart empties it."""
        self.ensure_one()
        if self._sa_is_cancel(text):
            items = self._sa_cart_items(include_self=True)
            if items:
                items.write({'state': 'dropped', 'drop_reason': 'declined', 'sa_menu_ask_at': False,
                             'sa_menu_json': False})
                self.sudo().write({'sa_menu_ask_at': False, 'sa_menu_json': False})
                self._say(_("\U0001F5D1 Your cart is cleared. Say *hi* whenever you need something."))
                return True
        return super()._sa_menu_typed(text)

    def _sa_done_item_name(self):
        """"1 x Demo laptop (8 GB, 512 GB SSD)" - the variant they picked."""
        self.ensure_one()
        variant = self.sa_variant_id if 'sa_variant_id' in self._fields else False
        return variant.display_name if variant else super()._sa_done_item_name()

    # ------------------------------------------------------------------
    # CONFIRM: the cart joins the order
    # ------------------------------------------------------------------
    def _sa_order_extra_lines(self, order):
        res = super()._sa_order_extra_lines(order)
        order = order.sudo()
        items = self._sa_cart_items()
        if not items:
            return res
        # This enquiry's own line first carries its exact variant and price,
        # so the "Done!" that reads the lines names it right.
        if hasattr(self, '_sa_variant_pin_line'):
            self._sa_variant_pin_line(order)
        self._sa_cart_pin_price(order, self.sa_variant_id if 'sa_variant_id' in self._fields else False,
                                self.product_id, self._sa_cart_price())
        Line = self.env['sale.order.line'].sudo()
        for r in items:
            variant = r._sa_cart_variant()
            if not variant:
                continue
            price = r._sa_cart_price()
            # The same variant at the same price already on the order (this
            # enquiry's own, or an earlier cart item): one line, more of it -
            # and stock is then read on the whole quantity.
            line = order.order_line.filtered(
                lambda l: not l.display_type and l.product_id == variant
                and abs((l.price_unit or 0.0) - float(price)) <= 0.005)[:1]
            if line:
                line.write({'product_uom_qty': (line.product_uom_qty or 0.0) + (r.qty or 1)})
            else:
                line = Line.create({'order_id': order.id, 'product_id': variant.id,
                                    'product_uom_qty': r.qty or 1})
            # Another module reprices a line on create (and on a quantity
            # change); the agreed price is the deal.
            if abs((line.price_unit or 0.0) - float(price)) > 0.005:
                line.write({'price_unit': price})
            r.sudo().write({'order_id': order.id, 'state': 'order_created',
                            'sa_menu_json': False, 'sa_menu_ask_at': False})
            _logger.info("Sales Automation: cart item %s (%s x %s at %.2f) added to %s",
                         r.id, variant.display_name, r.qty, price, order.name)
        return True

    @staticmethod
    def _sa_cart_pin_price(order, variant, template, price):
        """The agreed price on the first line of this product (a variant swap
        recomputes it)."""
        lines = order.order_line.filtered(
            lambda l: l.product_id and l.product_id.product_tmpl_id == template).sorted('id')[:1]
        for line in lines:
            if variant and line.product_id != variant:
                continue
            if abs((line.price_unit or 0.0) - float(price)) > 0.005:
                line.write({'price_unit': price})

    # ------------------------------------------------------------------
    # CHANGE with several items (owner, 22 Nov 2026): which item?
    # ------------------------------------------------------------------
    # The summary lists the whole cart, but CHANGE QUANTITY and BETTER PRICE
    # used to act on the last item only, and CANCEL ORDER was the only way
    # to drop one. With two or more items: "Which item?" (each item, ALL
    # ITEMS, BACK), and ➖ REMOVE AN ITEM. Each item is its own enquiry: the
    # one being changed becomes the active one (the others wait `in_cart`),
    # so the usual quantity and price steps run on it unchanged, and its
    # summary lists the whole cart again. ALL ITEMS walks them in turn
    # (`sa_cart_queue`). A single item works exactly as before.

    def _sa_cart_rows(self):
        """The summary's rows: [{'name', 'qty', 'price', 'ids'}], the same
        variant at the same price being one row (as `_ask_order_confirm`)."""
        self.ensure_one()
        rows = {}
        for r in list(self._sa_cart_items()) + [self]:
            row = rows.setdefault(r._sa_cart_key(), {'name': r._sa_cart_name(), 'qty': 0.0,
                                                     'price': r._sa_cart_price(), 'ids': []})
            row['qty'] += r.qty or 1
            row['ids'].append(r.id)
        return list(rows.values())

    def _sa_can_bargain(self):
        """Whether BETTER PRICE may still lower this item (the CHANGE menu's own rule)."""
        self.ensure_one()
        settings = self._settings()
        can = bool(settings.bargain_enabled)
        if can and hasattr(self, '_sa_qty_bargain_allowed'):
            can = self._sa_qty_bargain_allowed()
        if can and not (hasattr(self, '_sa_qty_tiered') and self._sa_qty_tiered()):
            can = self.bargain_count < (settings.bargain_max_steps or 0)
        return can

    def _sa_change_menu(self):
        self.ensure_one()
        if self.order_id or len(self._sa_cart_rows()) < 2:
            return super()._sa_change_menu()
        options = [self.CHANGE_QTY]
        if self._settings().bargain_enabled:
            options.append(self.CHANGE_PRICE)
        options += [CART_REMOVE, self.CHANGE_KEEP, self.CHANGE_CANCEL]
        self.write({'state': 'negotiating', 'sa_change_pending': True})
        self._ask(_("What would you like to change?"),
                  [{'id': 'sa_chg_%d' % i, 'title': o} for i, o in enumerate(options)])
        return True

    def _sa_change_answer(self, text):
        self.ensure_one()
        if not self.order_id and len(self._sa_cart_rows()) >= 2:
            key = self._sa_menu_key(text)
            act = {self._sa_menu_key(self.CHANGE_QTY): 'qty',
                   self._sa_menu_key(self.CHANGE_PRICE): 'price',
                   self._sa_menu_key(CART_REMOVE): 'remove'}.get(key)
            if act:
                self.sa_change_pending = False
                return self._sa_cart_which(act)
        return super()._sa_change_answer(text)

    def _sa_cart_which(self, act):
        """"Which item?" - each row, ALL ITEMS (quantity and price), BACK."""
        self.ensure_one()
        menu = {}
        for i, row in enumerate(self._sa_cart_rows()[:8], 1):
            label = '%d. %s x %s' % (i, (row['name'] or '')[:40], self._sa_cart_qty(row['qty']))
            menu[label] = {'kind': 'cart_pick', 'act': act, 'ids': row['ids']}
        if act in ('qty', 'price'):
            menu[CART_ALL] = {'kind': 'cart_all', 'act': act}
        menu[CART_BACK] = {'kind': 'cart_back'}
        self.write({'state': 'negotiating', 'sa_change_pending': False, 'sa_menu_json': json.dumps(menu)})
        body = {'qty': _("\U0001F522 Change the quantity of which item?"),
                'price': _("\U0001F4B0 A better price for which item?"),
                'remove': _("➖ Which item should I remove?")}[act]
        self._ask(body, [{'id': 'sa_cartw_%d' % i, 'title': label} for i, label in enumerate(menu)])
        return True

    def _sa_menu_tapped(self, item):
        kind = item.get('kind')
        if kind not in ('cart_pick', 'cart_all', 'cart_back'):
            return super()._sa_menu_tapped(item)
        self.ensure_one()
        self.sudo().write({'sa_menu_json': False})
        if kind == 'cart_back':
            return self._ask_order_confirm()
        act = item.get('act')
        if kind == 'cart_all':
            rows = [r['ids'] for r in self._sa_cart_rows()]
            return self._sa_cart_focus(rows[0], act, rows[1:])
        ids = [i for i in (item.get('ids') or []) if isinstance(i, int)]
        if not ids:
            return self._ask_order_confirm()
        if act == 'remove':
            return self._sa_cart_remove(ids)
        return self._sa_cart_focus(ids, act, [])

    def _sa_cart_focus(self, ids, act, queue):
        """Make the item `ids` (one summary row) the active enquiry and ask
        its new quantity or a better price; `queue` holds the rows still to
        do for ALL ITEMS."""
        self.ensure_one()
        rows = self.browse(ids).sudo().exists()
        if not rows:
            return self._sa_cart_next_or_summary(act, queue)
        target, dups = rows[:1], rows[1:]
        if dups:
            # One row was several enquiries of the same item: one carries it.
            target.qty = sum((r.qty or 1) for r in rows)
            dups.write({'state': 'dropped', 'drop_reason': 'stale', 'sa_menu_json': False})
        if target != self:
            self.sudo().write({'state': 'in_cart', 'sa_change_pending': False, 'sa_menu_json': False,
                               'sa_cart_queue': False, 'sa_cart_act': False})
        target.write({'sa_cart_queue': json.dumps(queue) if queue else False, 'sa_cart_act': act,
                      'sa_change_pending': False, 'sa_menu_json': False})
        name = target._sa_cart_name()
        if act == 'qty':
            target.qty = 0
            return target._sa_ask_qty_poll(_("\U0001F522 How many *%(item)s* do you need? Tap one \U0001F447",
                                             item=name))
        if not target._sa_can_bargain():
            target._say(_("\U0001F4B0 *%(item)s*: this is already our best price.", item=name))
            target.state = 'awaiting_order_confirm'
            return target._sa_cart_next_or_summary(act, queue)
        target.state = 'negotiating'
        return target._ask_their_price()

    def _sa_cart_focus_from(self, queue, act):
        """The next row of ALL ITEMS, asked from an item that is done (it is
        already back in the cart)."""
        self.ensure_one()
        first = self.browse(queue[0]).sudo().exists()[:1]
        if not first:
            return self._sa_cart_focus_from(queue[1:], act) if queue[1:] else self._ask_order_confirm()
        first.write({'state': 'negotiating'})
        return first._sa_cart_focus(queue[0], act, queue[1:])

    def _sa_cart_next_or_summary(self, act, queue):
        self.ensure_one()
        if queue:
            return self._sa_cart_focus(queue[0], act, queue[1:])
        self.sudo().write({'sa_cart_queue': False, 'sa_cart_act': False})
        return self._ask_order_confirm()

    def _sa_cart_remove(self, ids):
        """Take one row out of the order; the summary shows what is left."""
        self.ensure_one()
        gone = self.browse(ids).sudo().exists()
        name = gone[:1]._sa_cart_name() if gone else _("item")
        others = gone - self
        if others:
            others.write({'state': 'dropped', 'drop_reason': 'not_confirmed',
                          'sa_menu_json': False, 'sa_menu_ask_at': False})
        self._say(_("➖ Removed *%(item)s* from your order.", item=name))
        if self not in gone:
            return self._ask_order_confirm()
        rest = self._sa_cart_items()
        if not rest:
            return self._sa_cancel_deal()
        self.sudo().write({'state': 'dropped', 'drop_reason': 'not_confirmed', 'sa_menu_json': False,
                           'sa_change_pending': False, 'sa_cart_queue': False, 'sa_cart_act': False})
        lead = rest[-1]
        lead.write({'state': 'awaiting_order_confirm'})
        return lead._ask_order_confirm()

    # ------------------------------------------------------------------
    # Cancel before CONFIRM clears the cart too
    # ------------------------------------------------------------------
    def _sa_cancel_deal(self):
        self.ensure_one()
        if not self.order_id:
            items = self._sa_cart_items()
            if items:
                items.write({'state': 'dropped', 'drop_reason': 'declined',
                             'sa_menu_ask_at': False, 'sa_menu_json': False})
                _logger.info("Sales Automation: cancel cleared %d cart item(s) of enquiry %s",
                             len(items), self.id)
        return super()._sa_cancel_deal()


class SaSalesGroupInviteFetch(models.Model):
    _inherit = 'sa.sales.group'

    # One try per group per six hours: a number that is not a group admin is
    # refused every time, and the page must not wait on that.
    _SA_INVITE_TRIED = {}

    def _sa_back_url(self):
        group = self[:1]
        if group and 'invite_url' in group._fields and not (group.invite_url or '').strip():
            url = group._sa_fetch_invite_url()
            if url:
                group.sudo().write({'invite_url': url})
        parent = getattr(super(), '_sa_back_url', None)
        if parent:
            return parent()
        url = (group.invite_url or '').strip() if group and 'invite_url' in group._fields else ''
        return url if url.startswith('https://chat.whatsapp.com/') else 'https://wa.me/'

    def write(self, vals):
        """Switching sales automation on fetches the group's invite link
        right away, so "Back to <group>" works from the first order instead
        of after a slow first try on the customer's page (22 Nov 2026)."""
        res = super().write(vals)
        if vals.get('enabled') and not self.env.context.get('sa_no_invite_fetch'):
            self._sa_prefetch_invites()
        return res

    def _sa_prefetch_invites(self):
        for group in self:
            try:
                if 'invite_url' in group._fields and not (group.invite_url or '').strip() \
                        and group.group_jid and group.session_id:
                    url = group._sa_fetch_invite_url()
                    if url:
                        group.sudo().with_context(sa_no_invite_fetch=True).write({'invite_url': url})
            except Exception as err:  # noqa: BLE001 - never block switching a group on
                _logger.info("Sales Automation: invite link for group %s not fetched: %s", group.id, err)
        return True

    @api.model
    def _sa_cron_fetch_invites(self):
        """Once a day: switched-on customer groups still without an invite
        link try again (the shop's number may have been made admin since)."""
        groups = self.sudo().search([('enabled', '=', True), ('group_type', '=', 'customer'),
                                     ('invite_url', 'in', (False, ''))], limit=200)
        groups._sa_prefetch_invites()
        return True

    def _sa_fetch_invite_url(self):
        """The group's invite link from WhatsApp (works when the shop's number
        is a group admin); '' when it cannot be had."""
        self.ensure_one()
        import time
        key = (self.env.cr.dbname, self.id)
        if time.time() - self._SA_INVITE_TRIED.get(key, 0) < 6 * 3600:
            return ''
        self._SA_INVITE_TRIED[key] = time.time()
        # Tried in the last six hours (by this or the "Get invite link"
        # button): not again - the page must not wait on a known refusal.
        checked = getattr(self, 'invite_checked_on', False)
        if checked and fields.Datetime.now() - checked < timedelta(hours=6):
            return ''
        # The same ask as the group screen's "Get invite link" button
        # (sales_automation/models/sa_address_link.py), so the screen also
        # says why an automatic try failed.
        if hasattr(self, '_sa_invite_from_gateway'):
            url, error = self._sa_invite_from_gateway()
            vals = {}
            if 'invite_checked_on' in self._fields:
                vals['invite_checked_on'] = fields.Datetime.now()
            if 'invite_error' in self._fields:
                vals['invite_error'] = False if url else (error or '')[:500]
            if vals:
                self.sudo().write(vals)
            if not url:
                _logger.info("Sales Automation: invite link for group %s not available: %s", self.id, error)
            return url
        session = self.session_id.sudo()
        if not session or not self.group_jid or not session.instance_name:
            return ''
        try:
            body = session._gateway_call(
                'GET', '/group/inviteCode/%s?groupJid=%s' % (session.instance_name, self.group_jid), timeout=5)
        except Exception as err:  # noqa: BLE001 - the button falls back to WhatsApp
            _logger.info("Sales Automation: invite link for group %s not available: %s", self.id, err)
            return ''
        body = body if isinstance(body, dict) else {}
        url = str(body.get('inviteUrl') or '')
        code = str(body.get('inviteCode') or '')
        if not url.startswith('https://chat.whatsapp.com/') and code:
            url = 'https://chat.whatsapp.com/%s' % code
        return url if url.startswith('https://chat.whatsapp.com/') else ''
