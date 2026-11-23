# -*- coding: utf-8 -*-
"""The vendor's price on the page (owner, 23 Nov 2026): after ACCEPT the same page
asks for the amount, in the vendor's own currency. One answer. Nothing else is
asked in the chat. The same on WhatsApp and on WeChat; a vendor asked on both is
one vendor: an answer on either counts on both.

Reminders, with the same link: to a vendor who pressed neither button, and to one
who pressed ACCEPT and gave no price. Sent now or not at all, never queued."""
import logging
import re
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import config

_logger = logging.getLogger(__name__)

LINK_DAYS = 7
_AMOUNT = re.compile(r'^[0-9]{1,9}(?:\.[0-9]{1,3})?$')


class SaAiSettingsVendorRemind(models.Model):
    _inherit = 'sa.ai.settings'

    vendor_remind_minutes = fields.Integer(
        'Remind the vendor after (minutes)', default=5,
        help="A vendor who did not press ACCEPT or REJECT, or pressed ACCEPT and gave no price, is "
             "reminded with the same link after this long, and again after the same time. 0 = never.")
    vendor_remind_max = fields.Integer('Reminders at most', default=2)


class SaConfirmLinkVendor(models.Model):
    _inherit = 'sa.confirm.link'

    price_amount = fields.Float('Vendor price', readonly=True)
    price_currency = fields.Char('Currency', readonly=True)
    price_on = fields.Datetime('Price given', readonly=True)
    chat_yes_on = fields.Datetime('Said yes in the chat', readonly=True)
    remind_ask_count = fields.Integer('Reminders: no answer', default=0, readonly=True)
    remind_price_count = fields.Integer('Reminders: no price', default=0, readonly=True)
    vendor_reminded_on = fields.Datetime('Vendor reminded', readonly=True)
    proof = fields.Char('Proof', readonly=True, help="Kept when the details of an old link are cleaned up.")

    # ------------------------------------------------------------ one vendor, both chats
    def _vendor_links(self):
        """This vendor's links on this enquiry: WhatsApp and WeChat."""
        self.ensure_one()
        if self.kind != 'vendor' or not self.partner_id:
            return self
        return self.sudo().search([('request_id', '=', self.request_id.id), ('kind', '=', 'vendor'),
                                   ('partner_id', '=', self.partner_id.id)])

    def _vendor_money(self):
        """(amount, currency) this vendor gave - on the page or in a chat."""
        self.ensure_one()
        done = self._vendor_links().filtered('price_on').sorted('price_on', reverse=True)[:1]
        req = self.request_id.sudo()
        quote = req.quote_ids.filtered(lambda q: self.partner_id and q.partner_id == self.partner_id and q.matched_by != 'manual').sorted('id')[-1:]
        if quote:
            return quote.sa_typed_amount or quote.price, quote.sa_typed_currency or quote.currency_id.name or ''
        if done:
            return done.price_amount, done.price_currency or ''
        held = req._sa_held_of(self.partner_id.id, self.phone)
        return (held.get('amount'), held.get('code') or '') if held else (0.0, '')

    def _vendor_state(self):
        """'ask', 'accepted', 'priced' or 'rejected'."""
        self.ensure_one()
        req, links = self.request_id.sudo(), self._vendor_links()
        if self._vendor_money()[0]:
            return 'priced'
        decided = links.filtered('decided').sorted('decided_on')[:1]
        if decided:
            # a NO typed later in the chat counts too
            if decided.decided == 'reject' or self.partner_id in req.sa_vendor_no_ids:
                return 'rejected'
            return 'accepted'
        if self.partner_id and self.partner_id in req.sa_vendor_no_ids:
            return 'rejected'
        return 'ask'

    def _vendor_price_open(self):
        """Is this enquiry still taking a price? The same enquiries whose price
        is read in the chat: waiting, or given up for want of an answer."""
        self.ensure_one()
        req = self.request_id.sudo()
        return req.state == 'sourcing' or (req.state == 'dropped' and req.drop_reason == 'no_vendor_reply')

    def _vendor_currency(self):
        self.ensure_one()
        return self.request_id.sudo()._sa_vendor_currency(self.phone or self.partner_id.phone, self.partner_id)

    # ------------------------------------------------------------ the price
    def _lock_vendor(self):
        ids = self._vendor_links().ids
        self.env.cr.execute('SELECT id FROM %s WHERE id IN %%s ORDER BY id FOR UPDATE' % self._table, (tuple(ids),))
        self.invalidate_recordset()

    def _vendor_price(self, text):
        """The amount typed on the page. '' when taken, else what to tell."""
        self.ensure_one()
        amount = (text or '').strip().replace(' ', '')
        # 1,500.50 -> 1500.50; 12,5 -> 12.5
        amount = re.sub(r',(?=[0-9]{3}(?:[,.]|$))', '', amount).replace(',', '.')
        if not _AMOUNT.match(amount) or float(amount) <= 0:
            return _("Please type the amount as a number, like 500.")
        amount = float(amount)
        if self.kind != 'vendor' or self._link_expired():
            return _("This link has expired.")
        self._lock_vendor()
        state = self._vendor_state()
        if state == 'priced':
            return ''
        if state != 'accepted':
            return _("Please press ACCEPT first.")
        if not self._vendor_price_open():
            return _("This price check is already closed. Thank you.")
        req, partner = self.request_id.sudo(), self.partner_id
        code = self._vendor_currency()
        Quote = self.env['sa.vendor.quote'].sudo()
        # one answered too late but still wanted: as in the chat
        from odoo.addons.sales_automation.controllers.group_webhook import WhatsAppWebhookGroups
        WhatsAppWebhookGroups._sa_revive(req)
        quote = Quote._sa_take_price(req, amount, code, {
            'vendor_phone': self.phone or partner.phone or '',
            'vendor_name': partner.name or self.wechat_name or self.phone or '',
            'partner_id': partner.id or False,
            'raw_text': _("Typed on the page: %(cur)s %(amount)s", cur=code, amount=amount),
            'response_minutes': req._minutes_since_broadcast(),
            'matched_by': 'wechat' if self.channel == 'wechat' else 'direct',
            'message_ref': 'link%s' % self.id})
        self._vendor_links().write({'price_amount': amount, 'price_currency': code,
                                    'price_on': fields.Datetime.now()})
        if self.channel == 'wechat':
            self.env['sa.wechat.message'].sudo().create({
                'direction': 'in', 'state': 'received', 'partner_id': partner.id,
                'wechat_name': (partner.sa_wechat_name or '').strip(), 'text': '[page] %s %s' % (code, amount),
                'request_id': req.id, 'received_at': fields.Datetime.now(), 'quote_id': quote.id or False,
                'wx_id': 'confirm-%s-price' % self.id})
        req._sa_vendor_price_in(quote)
        req._sa_enquiry_notify()
        _logger.info("Sales Automation: %s typed %s %.2f on the page for enquiry %s",
                     partner.name or self.phone, code, amount, req.id)
        return ''

    # ------------------------------------------------------------ a week
    def _link_expired(self):
        """A week after the answer; unanswered, a week after it was sent."""
        self.ensure_one()
        start = max([d for d in (self.decided_on, self.price_on) if d], default=False) \
            or self.sent_on or self.create_date
        return bool(start and start < fields.Datetime.now() - timedelta(days=LINK_DAYS))

    def _proof_line(self):
        self.ensure_one()
        bits = [self.identity or '', {'accept': 'accepted', 'reject': 'rejected'}.get(self.decided, 'no answer')]
        if self.decided_on:
            bits.append(fields.Datetime.to_string(self.decided_on) + ' UTC')
        if self.price_on:
            bits.append('%s %.2f, %s UTC' % (self.price_currency or '', self.price_amount,
                                             fields.Datetime.to_string(self.price_on)))
        bits.append('opened %s x' % (self.open_count or 0))
        return ' · '.join(b for b in bits if b)

    @api.model
    def _cron_links_clean(self):
        """Daily: an expired link keeps one line of proof; the log of its opens,
        the browser's text and the pictures made only for it go."""
        since = fields.Datetime.now() - timedelta(days=LINK_DAYS)
        links = self.sudo().with_context(active_test=False).search(
            [('proof', '=', False), ('create_date', '<', since)], limit=1000)
        for link in links.filtered(lambda l: l._link_expired()):
            link.write({'proof': link._proof_line()[:500], 'decided_ua': False})
            link.click_ids.sudo().unlink()
            link.picture_ids.sudo().filtered(lambda p: not p.product_tmpl_id).unlink()
        return True

    # ------------------------------------------------------------ reminders
    @api.model
    def _cron_vendor_remind(self):
        settings = self.env['sa.ai.settings'].sudo().get_settings()
        minutes, most = int(settings.vendor_remind_minutes or 0), int(settings.vendor_remind_max or 0)
        if minutes <= 0 or most <= 0 or not settings.confirm_vendor_enabled:
            return True
        now = fields.Datetime.now()
        due = now - timedelta(minutes=minutes)
        # what began long ago (before this existed, while disconnected) is left alone
        oldest = now - timedelta(minutes=minutes * most + 60)
        rows = self.sudo().search([
            ('kind', '=', 'vendor'), ('partner_id', '!=', False), ('request_id.state', '=', 'sourcing'),
            '|', ('vendor_reminded_on', '=', False), ('vendor_reminded_on', '<=', due),
            '|', '|', ('sent_on', '>=', oldest), ('decided_on', '>=', oldest), ('chat_yes_on', '>=', oldest),
        ], order='id')
        reached, online = set(), {}
        for link in rows:
            who = (link.channel, link.partner_id.id)
            if who in reached:
                continue
            try:
                step = link._remind_step(due, oldest, most)
                if not step:
                    continue
                # only one at a time: another price check of this vendor was
                # reminded just now
                if self.sudo().search_count([('kind', '=', 'vendor'), ('channel', '=', link.channel),
                                             ('partner_id', '=', link.partner_id.id), ('id', '!=', link.id),
                                             ('vendor_reminded_on', '>', due)], limit=1):
                    continue
                if not link._remind_online(online):
                    continue
                if not config['test_enable']:
                    # the counts so far are kept, and what was answered
                    # meanwhile is seen
                    self.env.cr.commit()
                    self.env.invalidate_all()
                with self.env.cr.savepoint():
                    link._lock_vendor()
                    if link._remind_step(due, oldest, most) != step:
                        continue
                    n = link['remind_%s_count' % step] + 1
                    link.write({'remind_%s_count' % step: n, 'vendor_reminded_on': now})
                    self.env.flush_all()
                    link._remind_send(step, n, most)
                reached.add(who)
            except Exception as err:  # noqa: BLE001 - next run
                _logger.warning("Vendor reminder for link %s not sent: %s", link.id, err)
        return True

    def _remind_step(self, due, oldest, most):
        """'ask', 'price' or '' - what this vendor still owes us."""
        self.ensure_one()
        req = self.request_id.sudo()
        if not req.exists() or req.state != 'sourcing' or req.quote_ids or self._link_expired():
            return ''
        state = self._vendor_state()
        if state in ('priced', 'rejected'):
            return ''
        said = min([d for d in (self.decided_on, self.chat_yes_on) if d], default=False)
        if state == 'accepted' or said:
            if not said or self.remind_price_count >= most:        # said on their other chat: reminded there
                return ''
            return 'price' if oldest <= said <= due else ''
        if self.partner_id in req.sa_vendor_yes_ids:
            return ''
        sent = self._remind_sent_on()
        if not sent or self.remind_ask_count >= most:
            return ''
        return 'ask' if oldest <= sent <= due else ''

    def _remind_sent_on(self):
        """When the price check really went out."""
        self.ensure_one()
        if self.channel != 'wechat':
            return self.sent_on
        row = self.env['sa.wechat.message'].sudo().search(
            [('wx_confirm_link_id', '=', self.id), ('direction', '=', 'out'), ('state', 'in', ('sent', 'relayed'))],
            order='id desc', limit=1)
        return row.sent_on or False

    def _remind_online(self, known):
        self.ensure_one()
        if self.channel == 'wechat':
            settings = self.env['sa.ai.settings'].sudo().get_settings()
            return bool(settings.wechat_enabled and settings._sa_wechat_alive()
                        and (self.partner_id.sa_wechat_name or '').strip())
        session = self._remind_session()
        if not session:
            return False
        if session.id not in known:
            session._refresh_state()
            known[session.id] = session.status == 'connected'
        return known[session.id]

    def _remind_session(self):
        group = self.request_id.sudo().group_id
        return group.employee_session_id.session_id or group.session_id

    def _remind_send(self, step, n, most):
        """Send now or not at all (raises: the caller's savepoint undoes it)."""
        self.ensure_one()
        req = self.request_id.sudo()
        name = req._sa_confirm_name() or req.product_id.name or _("this item")
        cur = self._vendor_currency()
        ref = req.ref_code or req.id
        if step == 'ask':
            body = _("⏰ Reminder %(n)s of %(most)s: Price check *#%(ref)s* - *%(product)s*\n"
                     "Please open and press ACCEPT or REJECT:\n%(url)s",
                     n=n, most=most, ref=ref, product=name, url=self._url())
        else:
            body = _("⏰ Reminder %(n)s of %(most)s: please type your price for *%(product)s* (*#%(ref)s*):\n%(url)s\n\n"
                     "(or just reply with the amount in %(cur)s)",
                     n=n, most=most, ref=ref, product=name, url=self._url(), cur=cur)
        if self.channel == 'wechat':
            zh = ('提醒 %s/%s：询价 #%s\n请打开链接，选择 ACCEPT（有货）或 REJECT（没有）。' if step == 'ask'
                  else '提醒 %s/%s：询价 #%s\n请打开链接填写价格，或直接回复数字。') % (n, most, ref)
            self.env['sa.wechat.message'].sudo()._sa_queue(
                req, self.partner_id, body.replace('*', '') + '\n\n' + zh, step=step)
            return True
        phone = ''.join(ch for ch in (self.phone or self.partner_id.phone or '') if ch.isdigit())
        if not phone:
            raise UserError(_("No number."))
        session = self._remind_session()
        Message = self.env['whatsapp.message'].sudo()
        last = Message.search([], order='id desc', limit=1).id or 0
        if not session.send_message(phone, body):
            raise UserError(_("WhatsApp did not take the reminder."))
        Message.search([('id', '>', last), ('direction', '=', 'outgoing'), ('status', '=', 'pending'),
                        ('session_id', '=', session.id), ('phone', 'like', phone[-9:])]).write({'status': 'failed'})
        # a swipe-reply to the reminder names the enquiry
        req._sa_tag_last_outgoing(phone)
        return True


class SaGroupRequestVendorPage(models.Model):
    _inherit = 'sa.group.request'

    def _sa_ask_vendor_price(self, session, phone):
        """A YES typed in the chat: when the vendor has a page, remember when."""
        self.ensure_one()
        link = self._sa_vendor_link_for(phone)
        if link and not link.decided and not link.chat_yes_on:
            link.sudo().write({'chat_yes_on': fields.Datetime.now()})
        return super()._sa_ask_vendor_price(session, phone)

    def _sa_vendor_asked_before(self, vendor):
        """A repeated request: this vendor's message went out, but the link in it
        was undone with the first try. Made again - the token is the same."""
        super()._sa_vendor_asked_before(vendor)
        phone = ''.join(ch for ch in (vendor.phone or '') if ch.isdigit())
        if not phone or not self._sa_confirm_settings().confirm_vendor_enabled:
            return
        mine = [('kind', '=', 'vendor'), ('partner_id', '=', vendor.id), ('channel', '=', 'whatsapp')]
        Link = self.env['sa.confirm.link'].sudo()
        if not Link.search_count([('request_id', '=', self.id)] + mine, limit=1):
            self._sa_confirm_new_link({'kind': 'vendor', 'channel': 'whatsapp', 'partner_id': vendor.id,
                                       'phone': phone, 'sent_on': fields.Datetime.now()}, mine)

    def _sa_vendor_window_again(self):
        """They have it: the window starts again, as `_sa_ask_vendor_price` does."""
        self.ensure_one()
        if self.state == 'sourcing' and not self.sa_price_stalled:
            window = max(1, self._settings().sourcing_window_minutes or 10)
            fresh = fields.Datetime.add(fields.Datetime.now(), minutes=window)
            if not self.sourcing_deadline or self.sourcing_deadline < fresh:
                self.write({'sourcing_deadline': fresh})
        return True

    def _sa_vendor_confirmed(self, phone):
        """ACCEPT on either of this vendor's pages."""
        if super()._sa_vendor_confirmed(phone):
            return True
        vendor = self._sa_vendor_by_phone(phone)
        return bool(vendor and self.env['sa.confirm.link'].sudo().search_count(
            [('request_id', '=', self.id), ('kind', '=', 'vendor'), ('partner_id', '=', vendor.id),
             ('decided', '=', 'accept')], limit=1))

    # ------------------------------------------------------------ ACCEPT, after the page moved on
    def _sa_after_accepted_work(self, ref, action):
        self.ensure_one()
        link = self.env['sa.confirm.link'].sudo().browse(ref or 0).exists()
        if not link or link.request_id != self:
            return True
        from odoo.addons.sales_automation.models.sa_after_order import SaNotConnected
        session = self.group_id.session_id
        session._refresh_state()
        if session.status != 'connected':
            raise SaNotConnected()
        return self._sa_after_part('answer', lambda: self._sa_confirm_link_decided(link, action) or True)


class SaWeChatMessagePage(models.Model):
    _inherit = 'sa.wechat.message'

    @api.model
    def _sa_page_confirm(self, link, action):
        """ACCEPT on the page: the price is asked there, nothing in the chat."""
        if action != 'accept':
            return super()._sa_page_confirm(link, action)
        req, partner = link.request_id, link.partner_id
        self.sudo().create({
            'direction': 'in', 'state': 'received', 'partner_id': partner.id,
            'wechat_name': (partner.sa_wechat_name or '').strip(), 'text': '[page] In stock / 有货',
            'request_id': req.id, 'received_at': fields.Datetime.now(), 'wx_id': 'confirm-%s-accept' % link.id})
        vals = {}
        if partner in req.sa_vendor_no_ids:
            vals['sa_vendor_no_ids'] = [(3, partner.id)]
        if partner not in req.sa_vendor_yes_ids:
            vals['sa_vendor_yes_ids'] = [(4, partner.id)]
        if vals:
            req.write(vals)
        req._sa_wechat_extend_window()
        self._sa_notify(req)
        return {'ok': True, 'result': 'has_it'}

    @api.model
    def _sa_last_step(self, req, partner):
        """Accepted on the page: a number typed in the chat is the price."""
        step = super()._sa_last_step(req, partner)
        if step == 'ask' and self.env['sa.confirm.link'].sudo().search_count(
                [('request_id', '=', req.id), ('kind', '=', 'vendor'), ('partner_id', '=', partner.id),
                 ('decided', '=', 'accept')], limit=1):
            return 'price'
        return step
