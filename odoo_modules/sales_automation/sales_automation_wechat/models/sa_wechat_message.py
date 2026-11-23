# -*- coding: utf-8 -*-
"""The WeChat outbox and inbox.

Every price check to a WeChat vendor is one `out` row the bridge PC claims,
sends and reports on; every vendor reply is one `in` row the bridge posts
and this model turns into a vendor quote. The counter screen shows the rows
nobody could send when the bridge is down.
"""
import hashlib
import logging
import re
import time
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

_REF = re.compile(r'#\s*([0-9A-Za-z]{1,6})')


class SaWeChatMessage(models.Model):
    _name = 'sa.wechat.message'
    _description = 'WeChat message (vendor price checks)'
    _order = 'id desc'

    direction = fields.Selection([('out', 'To vendor'), ('in', 'From vendor')], required=True, index=True)
    state = fields.Selection([
        ('queued', 'Queued'), ('claimed', 'Claimed by the bridge'), ('sent', 'Sent'),
        ('failed', 'Failed'), ('received', 'Received'), ('relayed', 'Sent by hand'),
    ], default='queued', required=True, index=True)
    partner_id = fields.Many2one('res.partner', 'Vendor', index=True, ondelete='set null')
    wechat_name = fields.Char('WeChat remark', index=True)
    text = fields.Text('Text')
    request_id = fields.Many2one('sa.group.request', 'Enquiry', index=True, ondelete='set null')
    quote_id = fields.Many2one('sa.vendor.quote', 'Quote', ondelete='set null')
    claimed_on = fields.Datetime('Claimed on')
    sent_on = fields.Datetime('Sent on')
    received_at = fields.Datetime('Received at')
    error = fields.Char('Error')
    bridge_id = fields.Char('Bridge')
    wx_id = fields.Char('WeChat message id', index=True)
    wx_token = fields.Char('Answer-page token', index=True, copy=False,
                           help="The price check's link for this vendor: /sa/wx/<token>. One per price "
                                "check and vendor; it stays valid so the vendor can change the answer.")
    wx_step = fields.Selection([('ask', 'Step 1: do you have it?'), ('price', 'Step 2: your price'),
                                ('days', 'Step 3: delivery time'), ('info', 'Reply / thanks')], 'Step', index=True,
                               help="What this outgoing message asks the vendor. The vendor's next reply is "
                                    "read against the last step sent.")
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)

    # ------------------------------------------------------------------
    # Outbox: what the bridge sends
    # ------------------------------------------------------------------
    @api.model
    def _sa_queue(self, request, partner, text, step='ask'):
        return self.sudo().create({
            'direction': 'out', 'state': 'queued', 'partner_id': partner.id,
            'wechat_name': (partner.sa_wechat_name or '').strip(), 'text': text,
            'request_id': request.id, 'wx_step': step,
        })

    def _sa_page_url(self):
        """The button page for this price check and vendor, on the public
        address and through the database doorway (as the pay links)."""
        self.ensure_one()
        if not self.wx_token:
            import secrets
            self.sudo().write({'wx_token': secrets.token_urlsafe(18)})
        from urllib.parse import quote
        params = self.env['ir.config_parameter'].sudo()
        base = (params.get_param('sa_delivery.public_base_url') or params.get_param('web.base.url') or '').rstrip('/')
        return '%s/scoped_app/wx?db=%s&t=%s' % (base, quote(self.env.cr.dbname), self.wx_token)

    @api.model
    def _sa_page_answer(self, ask_row, answer, price, days_opt):
        """An answer from the button page. Recorded exactly like a typed
        reply (an 'in' row, the same yes / no / quote bookkeeping), and the
        thanks goes to the chat as well."""
        req, partner = ask_row.request_id, ask_row.partner_id
        answer = (answer or '').strip().lower()
        opt = req._WX_DAYS.get((days_opt or '').strip())
        try:
            price_f = float(str(price or '').replace(',', '.'))
        except ValueError:
            price_f = 0.0
        if answer == 'no':
            text = '[page] No stock / 没有'
        elif answer == 'yes' and price_f > 0 and opt:
            text = '[page] In stock, %s, %s / 有货，%s，%s' % (price_f, opt[1], price_f, opt[2])
        elif answer == 'yes' and price_f > 0:
            text = '[page] In stock, %s / 有货，%s' % (price_f, price_f)
        else:
            return {'ok': False, 'result': 'incomplete'}
        row = self.sudo().create({
            'direction': 'in', 'state': 'received', 'partner_id': partner.id,
            'wechat_name': (partner.sa_wechat_name or '').strip(), 'text': text,
            'request_id': req.id, 'received_at': fields.Datetime.now(),
            'wx_id': 'page-%s-%s' % (ask_row.id, int(time.time())),
        })
        if answer == 'no':
            Quote = self.env['sa.vendor.quote'].sudo()
            Quote.search([('request_id', '=', req.id), ('partner_id', '=', partner.id)]).unlink()
            self._sa_record_no(row, req, partner)
            return {'ok': True, 'result': 'no_stock'}
        Quote = self.env['sa.vendor.quote'].sudo()
        old = Quote.search([('request_id', '=', req.id), ('partner_id', '=', partner.id)])
        if old:
            old.unlink()
        vals = {}
        if partner in req.sa_vendor_no_ids:
            vals['sa_vendor_no_ids'] = [(3, partner.id)]
        if partner not in req.sa_vendor_yes_ids:
            vals['sa_vendor_yes_ids'] = [(4, partner.id)]
        if vals:
            req.write(vals)
        days = opt[0] if opt else None
        if opt:
            # Record with the days, and make the thanks name the range.
            quote, cur = self._sa_new_quote(row, req, partner, text, price_f, days)
            self._sa_queue(req, partner, req._sa_wechat_thanks_text(price_f, days, label=(opt[1], opt[2]), cur=cur), step='info')
            self._sa_notify(req)
            _logger.info("WeChat page: quote %.2f %s from %s on enquiry %s", price_f, cur, partner.name, req.id)
            return {'ok': True, 'result': 'quoted', 'price': price_f, 'days': days,
                    'days_en': opt[1], 'days_zh': opt[2], 'cur': cur}
        res = self._sa_record_quote(row, req, partner, text, price_f, None)
        res.update({'days_en': '', 'days_zh': ''})
        return res

    @api.model
    def _sa_new_quote(self, row, req, partner, text, price, days):
        """(quote, currency code) for a WeChat price: in the currency written,
        else the vendor's own, converted by `_sa_take_price`. An empty quote:
        no current rate, held for the counter."""
        Quote = self.env['sa.vendor.quote'].sudo()
        # the page's own words carry no currency
        said = '' if (text or '').startswith('[page]') else _REF.sub(' ', text or '')
        cur = Quote._sa_currency_in(said, req._sa_vendor_currency(partner.phone, partner))
        quote = Quote._sa_take_price(req, price, cur, {
            'vendor_phone': partner.phone or '', 'vendor_name': partner.name or row.wechat_name,
            'partner_id': partner.id, 'raw_text': text, 'delay_days': days or 0,
            'response_minutes': req._minutes_since_broadcast(), 'matched_by': 'wechat',
            'message_ref': 'wx%s' % row.id})
        row.write({'quote_id': quote.id or False, 'error': False})
        req._sa_vendor_price_in(quote)
        return quote, cur

    @api.model
    def _claim_outbox(self, limit=20, peek=False, bridge_id=''):
        """Rows to send now. A claimed row nobody reported on for two minutes
        is offered again (the bridge died mid-send)."""
        limit = max(1, min(int(limit or 20), 50))
        stale = fields.Datetime.now() - timedelta(minutes=2)
        rows = self.sudo().search(['&', ('direction', '=', 'out'), '|', ('state', '=', 'queued'),
                                   '&', ('state', '=', 'claimed'), ('claimed_on', '<', stale)],
                                  order='id asc', limit=limit)
        if not peek and rows:
            rows.write({'state': 'claimed', 'claimed_on': fields.Datetime.now(), 'bridge_id': bridge_id or False})
        return [{'id': r.id, 'to': r.wechat_name or '', 'text': r.text or '',
                 'ref': r.request_id.ref_code or ''} for r in rows]

    @api.model
    def _mark_sent(self, msg_id, ok, error='', bridge_id=''):
        row = self.sudo().browse(int(msg_id or 0)).exists()
        if not row or row.direction != 'out':
            return False
        if ok:
            row.write({'state': 'sent', 'sent_on': fields.Datetime.now(), 'error': False,
                       'bridge_id': bridge_id or row.bridge_id})
        else:
            row.write({'state': 'failed', 'error': (error or 'send failed')[:200],
                       'bridge_id': bridge_id or row.bridge_id})
            try:
                row.request_id._sa_enquiry_notify()
            except Exception:  # noqa: BLE001
                pass
        return True

    # ------------------------------------------------------------------
    # Inbox: what a vendor wrote
    # ------------------------------------------------------------------
    @api.model
    def _sa_find_partner(self, name):
        name = (name or '').strip()
        if not name:
            return self.env['res.partner']
        Partner = self.env['res.partner'].sudo()
        p = Partner.search([('sa_wechat_name', '=ilike', name)], limit=1)
        return p or Partner.search([('sa_wechat_name', 'ilike', name)], limit=1)

    @api.model
    def _sa_find_request(self, partner, text):
        """The enquiry this reply answers: the code in the text, else the
        newest price check still open for this vendor, else one stalled in
        the last day."""
        Req = self.env['sa.group.request'].sudo()
        m = _REF.search(text or '')
        if m:
            req = Req.search([('ref_code', '=ilike', m.group(1))], limit=1)
            if req:
                return req
        if not partner:
            return Req
        # The enquiry whose question this vendor was asked last.
        last_out = self.sudo().search([('direction', '=', 'out'), ('partner_id', '=', partner.id),
                                       ('request_id', '!=', False), ('wx_step', 'in', ('ask', 'price', 'days'))],
                                      order='id desc', limit=1)
        if last_out and (last_out.request_id.state == 'sourcing' or last_out.wx_step in ('price', 'days')):
            # Mid-conversation (price or days asked) the answer belongs to
            # that enquiry even when sourcing already closed: the live test
            # of 24 Sep sent a "2" for the delivery time to an older enquiry.
            return last_out.request_id
        req = Req.search([('sourcing_vendor_ids', 'in', partner.ids), ('state', '=', 'sourcing'),
                          ('sa_price_stalled', '=', False)], order='id desc', limit=1)
        if req:
            return req
        since = fields.Datetime.now() - timedelta(hours=24)
        return Req.search([('sourcing_vendor_ids', 'in', partner.ids), ('sa_price_stalled', '=', True),
                           ('write_date', '>=', since)], order='id desc', limit=1)

    @api.model
    def _sa_ingest(self, from_name, text, wx_id='', at=None, bridge_id=''):
        """One vendor message from the bridge. Returns a small dict the bridge
        logs; never raises for a message it cannot use."""
        text = (text or '').strip()
        from_name = (from_name or '').strip()
        wx_id = (wx_id or '').strip() or hashlib.sha1(
            ('%s|%s|%s' % (from_name, text, fields.Datetime.now().strftime('%Y%m%d%H%M'))).encode('utf-8')).hexdigest()
        if self.sudo().search_count([('wx_id', '=', wx_id)]):
            return {'ok': True, 'duplicate': True}
        partner = self._sa_find_partner(from_name)
        row = self.sudo().create({
            'direction': 'in', 'state': 'received', 'partner_id': partner.id or False,
            'wechat_name': from_name, 'text': text, 'wx_id': wx_id, 'bridge_id': bridge_id or False,
            'received_at': fields.Datetime.now(),
        })
        if not partner:
            row.error = 'unknown sender'
            _logger.info("WeChat: message from unknown remark %r kept as row %s", from_name, row.id)
            return {'ok': True, 'id': row.id, 'result': 'unknown_sender'}
        req = self._sa_find_request(partner, text)
        if not req:
            row.error = 'no open price check'
            return {'ok': True, 'id': row.id, 'result': 'no_request'}
        row.request_id = req.id
        return self._sa_answer_step(row, req, partner, text)

    _YES = ('1', '有', '有货', 'yes', 'y', '是', 'ok', 'in stock', '在', '可以', '能')
    _NO = ('2', '没有', '没货', '无货', '缺货', '没', 'no', 'n', 'no stock', '无', '不能')
    # Phrases anywhere in the reply. NO is tested first: "not available" and
    # "don't have" contain the yes words.
    _NO_PHRASES = ('no stock', 'not in stock', 'out of stock', 'not available', 'unavailable',
                   "don't have", 'dont have', 'do not have', 'not have', 'no have', 'sold out',
                   'cannot', "can't", 'not possible', '没有', '没货', '无货', '缺货', '卖完', '断货', '没了')
    _YES_PHRASES = ('have it', 'i have', 'we have', 'has it', 'available', 'in stock', 'yes', 'got it',
                    'can do', 'possible', 'ready stock', '有货', '有的', '现货', '可以')

    @api.model
    def _sa_says_no(self, low):
        return low in self._NO or any(ph in low for ph in self._NO_PHRASES)

    @api.model
    def _sa_says_yes(self, low):
        return low in self._YES or any(ph in low for ph in self._YES_PHRASES)

    # "45" or "45 3" (price, then days) - what step 2 asks for.
    _PLAIN_PRICE = re.compile(r'^\s*([0-9]+(?:[.,][0-9]+)?)(?:\s+([0-9]{1,3}))?\s*$')

    @api.model
    def _sa_last_step(self, req, partner):
        """The step this vendor is on for this enquiry: 'ask', 'price', or
        'done' once they have answered (thanks / no-thanks sent)."""
        last = self.sudo().search([('direction', '=', 'out'), ('partner_id', '=', partner.id),
                                   ('request_id', '=', req.id), ('wx_step', '!=', False)],
                                  order='id desc', limit=1)
        if last.wx_step == 'info':
            return 'done'
        return last.wx_step or 'ask'

    @api.model
    def _sa_plain_price(self, text):
        m = self._PLAIN_PRICE.match((text or '').strip())
        if not m:
            return None, None
        price = float(m.group(1).replace(',', '.'))
        days = int(m.group(2)) if m.group(2) else None
        return (price or None), days

    @api.model
    def _sa_record_yes(self, row, req, partner):
        """They have it (said at any point, even after a no): ask the price."""
        vals = {}
        if partner in req.sa_vendor_no_ids:
            vals['sa_vendor_no_ids'] = [(3, partner.id)]
        if partner not in req.sa_vendor_yes_ids:
            vals['sa_vendor_yes_ids'] = [(4, partner.id)]
        if vals:
            req.write(vals)
        req._sa_wechat_extend_window()
        self._sa_queue(req, partner, req._sa_wechat_price_text(partner), step='price')
        row.error = False
        self._sa_notify(req)
        return {'ok': True, 'id': row.id, 'result': 'has_it'}

    @api.model
    def _sa_answer_step(self, row, req, partner, text):
        """Read the vendor's reply against the step they were on. Every
        reply gets an answer; a yes or a no is understood at any step."""
        Quote = self.env['sa.vendor.quote'].sudo()
        low = _REF.sub('', (text or '').strip().lower()).strip().rstrip('。.!！')
        step = self._sa_last_step(req, partner)
        price, delay, is_no = Quote._sa_parse_cn(text)
        plain_price, plain_days = self._sa_plain_price(_REF.sub('', text or ''))
        if plain_price and low not in ('1', '2'):
            price, delay = plain_price, (plain_days if plain_days is not None else delay)
        digits_only = low.isdigit()
        if step == 'days':
            return self._sa_answer_days(row, req, partner, text, low, price, delay, is_no)
        says_no = bool(is_no or self._sa_says_no(low))
        says_yes = not says_no and self._sa_says_yes(low)
        # A price with words around it ("45 each", "有货 45元") is a quote at
        # any step. A lone 1 / 2 is an answer, never a price.
        clear_price = bool(price) and not (digits_only and low in ('1', '2')) \
            and not (step == 'ask' and digits_only and len(low) <= 1)
        if says_no and not clear_price:
            return self._sa_record_no(row, req, partner)
        if clear_price:
            if partner not in req.sa_vendor_yes_ids:
                req.write({'sa_vendor_yes_ids': [(4, partner.id)]})
            return self._sa_record_quote(row, req, partner, text, price, delay)
        if says_yes:
            return self._sa_record_yes(row, req, partner)
        if step == 'done':
            # Already answered and this is neither a price nor a yes / no:
            # keep it for the desk, tell them how to continue.
            self._sa_queue(req, partner, req._sa_wechat_retry_text('done'), step='info')
            row.error = 'after the answer'
            return {'ok': True, 'id': row.id, 'result': 'no_price'}
        retry_step = 'price' if step == 'price' else 'ask'
        self._sa_queue(req, partner, req._sa_wechat_retry_text(retry_step), step=retry_step)
        row.error = 'unreadable at step %s' % (2 if retry_step == 'price' else 1)
        return {'ok': True, 'id': row.id, 'result': 'retry'}

    @api.model
    def _sa_record_no(self, row, req, partner):
        vals = {}
        if partner not in req.sa_vendor_no_ids:
            vals['sa_vendor_no_ids'] = [(4, partner.id)]
        if partner in req.sa_vendor_yes_ids:
            vals['sa_vendor_yes_ids'] = [(3, partner.id)]
        if vals:
            req.write(vals)
        self._sa_queue(req, partner, req._sa_wechat_no_thanks_text(), step='info')
        row.error = False
        self._sa_notify(req)
        return {'ok': True, 'id': row.id, 'result': 'no_stock'}

    @api.model
    def _sa_answer_days(self, row, req, partner, text, low, price, delay, is_no):
        """Step 3: the delivery-time menu (1-4), or typed days, on the quote
        just recorded. A new price here updates the quote and asks again."""
        Quote = self.env['sa.vendor.quote'].sudo()
        quote = Quote.search([('request_id', '=', req.id), ('partner_id', '=', partner.id)], order='id desc', limit=1)
        if not quote:
            # Nothing to attach the days to: read it as a fresh step-2 answer.
            self._sa_queue(req, partner, req._sa_wechat_price_text(partner), step='price')
            row.error = 'days without a quote'
            return {'ok': True, 'id': row.id, 'result': 'retry'}
        opt = req._WX_DAYS.get(low)
        if opt:
            quote.write({'delay_days': opt[0]})
            row.write({'quote_id': quote.id, 'error': False})
            typed, cur = quote.sa_typed_amount or quote.price, quote.sa_typed_currency or None
            self._sa_queue(req, partner, req._sa_wechat_thanks_text(typed, opt[0], label=(opt[1], opt[2]), cur=cur), step='info')
            self._sa_notify(req)
            return {'ok': True, 'id': row.id, 'result': 'quoted', 'price': typed, 'days': opt[0]}
        if delay is not None:
            quote.write({'delay_days': delay})
            row.write({'quote_id': quote.id, 'error': False})
            typed, cur = quote.sa_typed_amount or quote.price, quote.sa_typed_currency or None
            self._sa_queue(req, partner, req._sa_wechat_thanks_text(typed, delay, cur=cur), step='info')
            self._sa_notify(req)
            return {'ok': True, 'id': row.id, 'result': 'quoted', 'price': typed, 'days': delay}
        if is_no or self._sa_says_no(low):
            quote.unlink()
            return self._sa_record_no(row, req, partner)
        if price and not (low.isdigit() and len(low) <= 1):
            quote.unlink()
            return self._sa_record_quote(row, req, partner, text, price, None)
        self._sa_queue(req, partner, req._sa_wechat_retry_text('days'), step='days')
        row.error = 'unreadable at step 3'
        return {'ok': True, 'id': row.id, 'result': 'retry'}

    @api.model
    def _sa_record_quote(self, row, req, partner, text, price, delay):
        quote, cur = self._sa_new_quote(row, req, partner, text, price, delay)
        if delay is None and quote:
            # Price only: the delivery time comes from the step-3 menu.
            self._sa_queue(req, partner, req._sa_wechat_days_text(), step='days')
        else:
            self._sa_queue(req, partner, req._sa_wechat_thanks_text(price, delay or 0, cur=cur), step='info')
        self._sa_notify(req)
        _logger.info("WeChat: quote %.2f %s from %s on enquiry %s", price, cur, partner.name, req.id)
        return {'ok': True, 'id': row.id, 'result': 'quoted', 'price': price, 'days': delay or 0, 'cur': cur}

    @api.model
    def _sa_notify(self, req):
        try:
            req._sa_enquiry_notify()
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------
    # Counter screen: relay by hand
    # ------------------------------------------------------------------
    @api.model
    def sa_wechat_relay_rows(self):
        settings = self.env['sa.ai.settings'].sudo().get_settings()
        alive = settings._sa_wechat_alive()
        stale = fields.Datetime.now() - timedelta(minutes=max(1, settings.wechat_stale_minutes or 3))
        dom = [('direction', '=', 'out'), '|', ('state', '=', 'failed'),
               '&', ('state', 'in', ('queued', 'claimed')), ('create_date', '<', stale)]
        rows = self.sudo().search(dom, order='id asc', limit=30) if settings.wechat_enabled else self.sudo().browse()
        out = []
        for r in rows:
            if r.state in ('queued', 'claimed') and (alive or not settings.wechat_manual_when_down):
                continue
            req = r.request_id
            out.append({'id': r.id, 'vendor': r.partner_id.name or r.wechat_name, 'remark': r.wechat_name or '',
                        'text': r.text or '', 'state': r.state, 'error': r.error or '', 'step': r.wx_step or 'ask',
                        'request_id': req.id, 'ref': req.ref_code or '', 'product': req.product_id.name or req.raw_text or '',
                        'qty': req.qty or 0, 'partner_id': r.partner_id.id,
                        'minutes': int((fields.Datetime.now() - r.create_date).total_seconds() // 60)})
        return {'enabled': bool(settings.wechat_enabled), 'alive': alive,
                'manual_on': bool(settings.wechat_manual_when_down), 'rows': out}

    @api.model
    def sa_wechat_act(self, msg_id, action, cost=None, days=0):
        row = self.sudo().browse(int(msg_id)).exists()
        if not row:
            raise UserError(_("That message is no longer there."))
        if action == 'sent_by_hand':
            row.write({'state': 'relayed', 'sent_on': fields.Datetime.now(), 'error': False})
        elif action == 'price':
            req = row.request_id
            if not req:
                raise UserError(_("No enquiry on this message."))
            if req.state == 'sourcing' and not req.sa_price_stalled:
                Quote = self.env['sa.vendor.quote'].sudo()
                Quote.create({
                    'request_id': req.id, 'vendor_phone': row.partner_id.phone or '',
                    'vendor_name': row.partner_id.name or row.wechat_name, 'partner_id': row.partner_id.id,
                    'price': float(cost or 0), 'currency_id': req.currency_id.id,
                    'raw_text': _("typed at the counter (WeChat)"), 'delay_days': int(days or 0),
                    'response_minutes': req._minutes_since_broadcast(), 'matched_by': 'wechat'})
            else:
                req._sa_apply_manual_price(cost, vendor_id=row.partner_id.id or None, days=days,
                                           source=_("WeChat relay"))
            row.write({'state': 'relayed', 'sent_on': row.sent_on or fields.Datetime.now(), 'error': False})
            self._sa_notify(req)
        else:
            raise UserError(_("Unknown action."))
        return self.sa_wechat_relay_rows()

    def action_link_vendor(self):
        """From the inbox form: the unknown remark becomes this vendor's."""
        for row in self:
            if row.partner_id and row.wechat_name:
                row.partner_id.sudo().write({'sa_wechat_name': row.wechat_name, 'sa_via_wechat': True})
                row.error = False
        return True
