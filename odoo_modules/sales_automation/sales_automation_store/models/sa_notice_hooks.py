# -*- coding: utf-8 -*-
"""When a note is made. Nothing here changes the flow it listens to."""
from odoo import _, api, models


class SaGroupRequestNotice(models.Model):
    _inherit = 'sa.group.request'

    def _sa_notice_who(self):
        self.ensure_one()
        return self.requester_name or _("Customer")

    def _sa_notice_money(self, amount, currency):
        return '%s %.2f' % (currency.name or '', amount or 0.0)

    def _place_order(self):
        before = self.order_id
        res = super()._place_order()
        order = self.sudo().order_id
        if order and order != before:
            self.env['sa.notice']._tell(
                'order', _("New order"),
                _("%(order)s · %(who)s · %(total)s", order=order.name, who=self._sa_notice_who(),
                  total=self._sa_notice_money(order.amount_total, order.currency_id)),
                'order|%s' % order.id, request=self, order=order)
        return res

    def _sa_group_confirmed(self, order):
        told = self.sa_paid_told_on
        res = super()._sa_group_confirmed(order)
        if order and self.sa_paid_told_on and not told:
            order = order.sudo()
            self.env['sa.notice']._tell(
                'paid', _("Payment received"),
                _("%(who)s paid %(total)s · %(order)s", who=self._sa_notice_who(), order=order.name,
                  total=self._sa_notice_money(order.amount_total, order.currency_id)),
                'paid|%s' % order.id, request=self, order=order)
        return res


class SaVendorQuoteNotice(models.Model):
    _inherit = 'sa.vendor.quote'

    @api.model_create_multi
    def create(self, vals_list):
        quotes = super().create(vals_list)
        for quote in quotes:
            if quote.matched_by != 'manual' and quote.request_id:
                quote.sudo()._sa_notice_price()
        return quotes

    def _sa_notice_price(self):
        self.ensure_one()
        request, Notice = self.request_id, self.env['sa.notice']
        who = lambda q: q.partner_id.name or q.vendor_name or _("Vendor")  # noqa: E731
        ref = request.ref_code or request.id
        newest = {}
        for quote in request.quote_ids.sorted('id'):
            newest[quote._sa_who()] = quote
        prices = sorted(newest.values(), key=lambda q: (q.price, q.id))
        low = prices[0] if prices else self
        Notice._tell(
            'price', _("%(n)s prices for Ref %(ref)s", n=len(prices), ref=ref) if len(prices) > 1
            else _("Price for Ref %s", ref),
            _("Lowest %(who)s: %(price)s", who=who(low), price=request._sa_notice_money(low.price, low.currency_id)),
            'price|%s' % request.id, request=request)
        best = request.best_quote_id
        if best and best != self and request.sa_evaluated_on and best.currency_id == self.currency_id \
                and self.price < best.price - 0.004:
            Notice._tell(
                'cheaper', _("Cheaper vendor"),
                _("Ref %(ref)s · %(who)s: %(price)s, %(less)s less than %(best)s", ref=ref, who=who(self),
                  price=request._sa_notice_money(self.price, self.currency_id),
                  less=request._sa_notice_money(best.price - self.price, self.currency_id), best=who(best)),
                'cheaper|%s' % self.id, request=request)


class WhatsAppSessionNotice(models.Model):
    _inherit = 'whatsapp.session'

    def write(self, vals):
        was = {s.id: s.status for s in self} if 'status' in vals else {}
        res = super().write(vals)
        for session in self:
            if was.get(session.id) == 'connected' and session.status != 'connected' and session.active:
                self.env['sa.notice']._tell(
                    'whatsapp', _("WhatsApp number is off"), _("%s is not connected any more", session.sudo().name),
                    'whatsapp|%s|%s' % (session.id, self.env.cr.now().strftime('%Y%m%d%H')), session=session)
        return res
