# -*- coding: utf-8 -*-
"""The sourcing hook and the vendor's messages, in steps.

A personal WeChat chat has no buttons, so the vendor answers with one
digit: step 1 asks whether they have it (1 / 2), step 2 asks the price
(a number, days optional). Every message carries English and Chinese.
"""
import logging

from odoo import _, fields, models

_logger = logging.getLogger(__name__)


class SaGroupRequestWeChat(models.Model):
    _inherit = 'sa.group.request'

    # ------------------------------------------------------------------
    # Texts (EN line, then its ZH line)
    # ------------------------------------------------------------------
    def _sa_wechat_item(self):
        self.ensure_one()
        name = self.product_id.name or self.ai_search_term or self.raw_text or _("this item")
        qty = int(self.qty or 0)
        return name, ((' x %d' % qty) if qty else '')

    # Step 3 delivery-time menu: option -> (days stored, EN label, ZH label)
    _WX_DAYS = {'1': (0, 'ready stock', '现货'), '2': (3, '1-3 days', '1-3天'),
                '3': (7, '4-7 days', '4-7天'), '4': (14, 'more than 7 days', '7天以上')}

    def _sa_wechat_ask_text(self, ask=None, link=None):
        """Step 1: do you have it? One line per item, the numbers in a column."""
        self.ensure_one()
        name, qty = self._sa_wechat_item()
        ref = self.ref_code or ''
        qty_n = int(self.qty or 0)
        return ("Price check #%(ref)s\n"
                "%(name)s\n"
                "Qty: %(qty)s\n"
                "\n"
                "Do you have it?\n"
                "1 = In stock\n"
                "2 = No stock\n"
                "\n"
                "询价 #%(ref)s\n"
                "%(name)s\n"
                "数量：%(qty)s\n"
                "有货吗？\n"
                "1 = 有货\n"
                "2 = 没有" % {'ref': ref, 'name': name, 'qty': qty_n or 1})

    def _sa_wechat_price_text(self, partner=None):
        """Step 2: the price, a number only, in the vendor's currency (the
        same as on WhatsApp, 23 Nov 2026)."""
        self.ensure_one()
        cur = self._sa_vendor_currency(partner.phone, partner) if partner else ''
        return ("Your price%(en)s?\n"
                "Reply the number only, e.g. 45\n"
                "\n"
                "单价%(zh)s？\n"
                "只回复数字，例如 45" % {'en': (' in %s' % cur) if cur else '', 'zh': ('（%s）' % cur) if cur else ''})

    def _sa_partner_currency(self, partner, phone=None, company=None):
        """A WeChat vendor with neither a country nor a phone prices in CNY."""
        partner = partner or self.env['res.partner']
        if (partner and partner._sa_wechat_reachable() and not partner.country_id
                and not (phone or partner.phone)
                and not (partner.street and self._sa_country_in_address(partner.street))):
            return 'CNY'
        return super()._sa_partner_currency(partner, phone, company)

    def _sa_wechat_days_text(self, sorry=False):
        """Step 3: delivery time as a numbered menu."""
        self.ensure_one()
        head = "Sorry, I did not understand.\n" if sorry else ""
        head_zh = "抱歉没看懂。\n" if sorry else ""
        return (head +
                "Delivery time?\n"
                "1 = Ready stock\n"
                "2 = 1-3 days\n"
                "3 = 4-7 days\n"
                "4 = More than 7 days\n"
                "\n" + head_zh +
                "交货时间？\n"
                "1 = 现货\n"
                "2 = 1-3天\n"
                "3 = 4-7天\n"
                "4 = 7天以上")

    def _sa_wechat_thanks_text(self, price, days, label=None, cur=None):
        self.ensure_one()
        cur = cur or self.currency_id.symbol or ''
        if label:
            en, zh = label
        elif days:
            en, zh = '%d days' % days, '%d天' % days
        else:
            en, zh = None, None
        text = ("Received ✔\n"
                "Price: %(cur)s %(price).2f\n" % {'cur': cur, 'price': price})
        if en:
            text += "Delivery: %s\n" % en
        text += ("Our store manager will contact you soon. Thank you!\n"
                 "\n"
                 "已收到 ✔\n"
                 "单价：%(cur)s %(price).2f\n" % {'cur': cur, 'price': price})
        if zh:
            text += "交货：%s\n" % zh
        text += "我们的店长会尽快联系您。谢谢！"
        return text

    def _sa_wechat_no_thanks_text(self):
        return "No problem, thank you.\n没关系，谢谢。"

    def _sa_wechat_retry_text(self, step):
        self.ensure_one()
        if step == 'days':
            return self._sa_wechat_days_text(sorry=True)
        if step == 'price':
            return ("Sorry, I did not understand.\n"
                    "Reply the price as a number only, e.g. 45\n"
                    "\n"
                    "抱歉没看懂。\n"
                    "只回复数字价格，例如 45")
        if step == 'done':
            return ("Thanks.\n"
                    "To change your answer:\n"
                    "1 = In stock (then your price)\n"
                    "2 = No stock\n"
                    "\n"
                    "谢谢。\n"
                    "如需修改：\n"
                    "1 = 有货（然后回复价格）\n"
                    "2 = 没有")
        return ("Sorry, I did not understand.\n"
                "1 = In stock\n"
                "2 = No stock\n"
                "\n"
                "抱歉没看懂。\n"
                "1 = 有货\n"
                "2 = 没有")

    # ------------------------------------------------------------------
    # The sourcing hook
    # ------------------------------------------------------------------
    def _sa_ask_via_wechat(self, vendor, ask, guard, trigger):
        """Queue step 1 when the vendor is ticked for WeChat. Returns True
        when the WhatsApp poll must be skipped for this vendor (WhatsApp
        not ticked or no phone), False when it must still go out."""
        self.ensure_one()
        if not hasattr(vendor, '_sa_wechat_reachable'):
            return False
        settings = self.env['sa.ai.settings'].sudo().get_settings()
        on_wechat = settings.wechat_enabled and vendor._sa_wechat_reachable()
        on_whatsapp = vendor._sa_whatsapp_reachable()
        if on_wechat:
            remark = (vendor.sa_wechat_name or '').strip()
            # The row itself says whether they were asked: it is undone with
            # a request that is repeated, where the outbox guard was not - the
            # repeat then asked nobody (23 Nov 2026).
            Msg = self.env['sa.wechat.message'].sudo()
            if not Msg.search_count([
                    ('request_id', '=', self.id), ('partner_id', '=', vendor.id), ('direction', '=', 'out'),
                    ('wx_step', '=', 'ask'),
                    ('create_date', '>=', fields.Datetime.subtract(fields.Datetime.now(), seconds=60))], limit=1):
                self.env['sa.wechat.message']._sa_queue(self, vendor, self._sa_wechat_ask_text(ask), step='ask')
                _logger.info("WeChat: price check for enquiry %s queued to %s", self.id, remark)
        return not on_whatsapp
