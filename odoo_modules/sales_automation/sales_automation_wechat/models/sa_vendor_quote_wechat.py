# -*- coding: utf-8 -*-
"""Chinese price replies: full-width digits, 元 / ¥ / RMB, 天 for days, and
the words that mean 'no stock'."""
import re
import unicodedata

from odoo import api, fields, models

_NO_WORDS = ('没有', '无货', '没货', '缺货', '没有货', '暂无', '无', 'no stock', 'not available',
             'out of stock', 'nil', 'no')
_CN_CURRENCY = re.compile(r'(人民币|元|块钱|块|￥|¥|rmb|cny)', re.IGNORECASE)
_CN_DAYS = re.compile(r'(\d+(?:\.\d+)?)\s*(?:个)?\s*(天|日)')
_CN_WEEKS = re.compile(r'(\d+(?:\.\d+)?)\s*(?:个)?\s*(周|星期|礼拜)')


class SaVendorQuoteWeChat(models.Model):
    _inherit = 'sa.vendor.quote'

    matched_by = fields.Selection(selection_add=[('wechat', 'WeChat Reply')],
                                  ondelete={'wechat': 'set default'})

    @api.model
    def _sa_normalise_cn(self, text):
        """Full-width digits to ASCII, Chinese money and time words to the
        shapes the existing parsers already read."""
        t = unicodedata.normalize('NFKC', text or '')
        t = _CN_WEEKS.sub(lambda m: '%s weeks' % m.group(1), t)
        t = _CN_DAYS.sub(lambda m: '%s days' % m.group(1), t)
        t = _CN_CURRENCY.sub(' ', t)
        t = t.replace('，', ', ').replace('。', '. ').replace('：', ': ')
        return t

    @api.model
    def _sa_is_no_reply(self, text):
        low = (text or '').strip().lower()
        if not low:
            return False
        if any(ch.isdigit() for ch in low):
            return False
        return any(w in low for w in _NO_WORDS)

    @api.model
    def _sa_parse_cn(self, text):
        """(price, delay_days_or_None, is_no) from a WeChat reply."""
        norm = self._sa_normalise_cn(text)
        if self._sa_is_no_reply(norm):
            return None, None, True
        price = self._parse_vendor_price(self._strip_reference(norm))
        delay = self._parse_delay(norm)
        return price, delay, False
