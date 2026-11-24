# -*- coding: utf-8 -*-
"""One card for every vendor asked (owner, 24 Nov 2026): the price with its date
and time, or "-" for who has not answered. The screens only show; the server
checks again who may be chosen."""
import re

from odoo import _, api, models
from odoo.exceptions import UserError

from .sa_boards import iso


# "#D8LR", "Ref 1GL"
CODE = re.compile(r'(?:#|\bRef\s+#?)([A-Za-z0-9]{2,8})\b')


class SaGroupRequestCards(models.Model):
    _inherit = 'sa.group.request'

    @api.model
    def _sa_tail(self, phone):
        return ''.join(ch for ch in (phone or '') if ch.isdigit())[-9:]

    def _sa_vendor_cards(self, bought=None):
        self.ensure_one()
        request = self.sudo()
        bought = request._sa_bought_map() if bought is None else bought
        newest = {}
        for quote in request.quote_ids.sorted('id'):
            if (quote.price or 0.0) > 0:
                newest[quote._sa_who()] = quote
        order = request._sa_rank_quotes(request.quote_ids.browse([q.id for q in newest.values()]), bought)
        low = round(order[0].price, 4) if len(order) > 1 else None
        deadline = request.sa_evaluated_on
        times = lambda partner: bought.get((request.product_id.id, partner.id), 0) if partner else 0  # noqa: E731
        cards = []
        for place, quote in enumerate(order, 1):
            arrived = quote._sa_arrived()
            cards.append({
                'key': 'q%s' % quote.id, 'phone': self._sa_tail(quote.partner_id.phone or quote.vendor_phone), 'vendor_id': quote.partner_id.id or 0, 'quote_id': quote.id, 'state': 'price',
                'vendor': quote.partner_id.name or quote.vendor_name or quote.vendor_phone or '',
                'price': quote.price, 'sell': quote.sa_sell_price, 'currency': quote.currency_id.name or request.currency_id.name or '',
                'replied_at': iso(arrived), 'bought': times(quote.partner_id), 'rank': place,
                'lowest': low is not None and round(quote.price, 4) == low,
                'late': quote.sa_late or bool(request.sa_vendor_choice_pending and deadline and arrived > deadline),
                'selected': bool(request.best_quote_id == quote and quote.is_best),
                'can_choose': request._sa_can_choose_vendor(), 'text': (quote.raw_text or '')[:300]})
        priced = order.partner_id
        held = {h.get('partner') for h in request._sa_held().values()}
        for partner in (request.sourcing_vendor_ids or request.shop_pick_vendor_ids) - priced:
            state = 'held' if partner.id in held else 'no' if partner in request.sa_vendor_no_ids \
                else 'yes' if partner in request.sa_vendor_yes_ids else 'waiting'
            cards.append({
                'key': 'v%s' % partner.id, 'phone': self._sa_tail(partner.phone), 'vendor_id': partner.id, 'quote_id': False, 'state': state, 'vendor': partner.name or '',
                'price': None, 'sell': None, 'currency': '', 'replied_at': None, 'bought': times(partner), 'rank': None,
                'lowest': False, 'late': False, 'selected': False, 'can_choose': False, 'text': ''})
        return cards

    def _sa_selected_words(self):
        self.ensure_one()
        if not self.sa_selected_by:
            return ''
        why = dict(self._fields['sa_selected_reason']._description_selection(self.env)).get(self.sa_selected_reason, '')
        return _("%(why)s (%(who)s)", why=why, who=self.sa_selected_user_id.name) if self.sa_selected_by == 'manual' and self.sa_selected_user_id else why

    def _sa_put_cards(self, rows):
        """On rows that are enquiries: {'id': ...}."""
        requests = self.sudo().browse([row['id'] for row in rows])
        bought = requests._sa_bought_map()
        for row, request in zip(rows, requests):
            row.update(cards=request._sa_vendor_cards(bought), selected_why=request._sa_selected_words())
        return rows

    @api.model
    def sa_enquiry_queue(self):
        data = super().sa_enquiry_queue()
        data['tracking'] = [row for row in data['tracking'] if not self.sudo().browse(row['id']).sa_vendor_choice_pending]
        self._sa_put_cards((data.get('tracking') or []) + (data.get('stalled') or []))
        for row in data.get('stalled') or []:
            row['pick_vendor'] = self.sudo().browse(row['id']).sa_vendor_choice_pending
        data['mode'] = self.env['sa.ai.settings'].sudo().get_settings().vendor_choice_mode
        return data

    @api.model
    def sa_enquiry_board(self, tab, search='', days=30, offset=0):
        data = super().sa_enquiry_board(tab, search=search, days=days, offset=offset)
        self._sa_put_cards(data['rows'])
        return data

    @api.model
    def sa_enquiry_detail(self, request_id):
        detail = super().sa_enquiry_detail(request_id)
        request = self.sudo().browse(int(request_id))
        self._sa_order_messages(request, detail)
        return self._sa_put_cards([detail])[0]

    @api.model
    def _sa_order_messages(self, request, detail):
        """The order to the vendor carries the order's code, not the enquiry's:
        it belongs to this chat as well. Nothing of other orders."""
        tails = {self._sa_tail(p.phone) for p in request.sourcing_vendor_ids | request.quote_ids.partner_id} - {''}
        codes = [c for c in request.order_id.picking_ids.mapped('sa_ref_code') if c] if request.order_id else []
        # a message with another order's or enquiry's code is not of this one
        own = {c.upper() for c in codes + [request.ref_code or ''] if c}

        def ours(text):
            named = {c.upper() for c in CODE.findall(text or '')}
            return not named or bool(named & own)
        detail['vendor_messages'] = [m for m in detail['vendor_messages'] if ours(m['text'])]
        if not tails or not codes:
            return
        names = {self._sa_tail(p.phone): p.name for p in request.sourcing_vendor_ids | request.quote_ids.partner_id}
        have = {(m['phone'], m['at'], m['text']) for m in detail['vendor_messages']}
        for code in codes:
            for msg in self.env['whatsapp.message'].sudo().search(
                    [('message', 'ilike', '#%s' % code), ('create_date', '>=', request.create_date)], order='id', limit=60):
                tail = self._sa_tail(msg.phone)
                row = {'who': 'vendor' if msg.direction == 'incoming' else 'us', 'name': names.get(tail, ''), 'direction': msg.direction,
                       'phone': msg.phone or '', 'text': (msg.message or '')[:400], 'status': msg.status or '', 'at': iso(msg.create_date)}
                if tail in tails and ours(row['text']) and (row['phone'], row['at'], row['text']) not in have:
                    detail['vendor_messages'].append(row)
                    have.add((row['phone'], row['at'], row['text']))
        detail['vendor_messages'].sort(key=lambda m: m['at'])

    @api.model
    def sa_vendor_choose(self, request_id, quote_id):
        """The counter's Choose button."""
        request = self.browse(int(request_id))
        if not request.exists():
            raise UserError(_("That enquiry is no longer there."))
        request.check_access('write')
        quote = self.env['sa.vendor.quote'].sudo().browse(int(quote_id))
        if not quote.exists() or quote.request_id.id != request.id:
            raise UserError(_("That price is no longer there. Look at the prices again."))
        request = request.sudo()
        request._sa_choose_vendor(quote)
        request._sa_enquiry_notify()
        return self.sa_enquiry_queue()


class StockPickingCards(models.Model):
    _inherit = 'stock.picking'

    def _sa_order_cards(self):
        self.ensure_one()
        request = self.sale_id._sa_group_enquiry() if self.sale_id else False
        if not request:
            return {'cards': [], 'selected_why': ''}
        request = request.sudo()
        return {'cards': request._sa_vendor_cards(), 'selected_why': request._sa_selected_words()}

    def _sa_board_extra(self):
        return dict(super()._sa_board_extra(), **self._sa_order_cards())

    @api.model
    def _sa_done_today(self, shop_id=None):
        rows = super()._sa_done_today(shop_id)
        for row in rows:
            row.update(self.sudo().browse(row['id'])._sa_order_cards())
        return rows
