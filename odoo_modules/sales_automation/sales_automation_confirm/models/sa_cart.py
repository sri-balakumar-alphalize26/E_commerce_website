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
import logging
from datetime import timedelta

from odoo import _, fields, models

_logger = logging.getLogger(__name__)

ADD_ITEM = "➕ ADD ANOTHER ITEM"
CART_HOURS = 6


class SaGroupRequestCart(models.Model):
    _inherit = 'sa.group.request'

    state = fields.Selection(selection_add=[('in_cart', 'In Cart')],
                             ondelete={'in_cart': 'set default'})

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
        return super()._on_deal_reply(text)

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
        return url if url.startswith('https://chat.whatsapp.com/') else 'whatsapp://'

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
