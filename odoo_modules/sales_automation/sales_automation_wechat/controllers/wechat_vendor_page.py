# -*- coding: utf-8 -*-
"""The vendor's answer page: real buttons for a chat that has none.

A personal WeChat chat cannot show buttons, but it opens links in its own
browser. The price check the bridge sends carries a tokened link to this
page: In stock / No stock, the amount, delivery time as four buttons, Send.
The vendor types only the amount. Typed chat replies keep working too.

Public route, no session: the token on the outgoing message is the whole
credential (one per price check and vendor). It shows the product, the
quantity and nothing else. The database is found through the same doorway
the pay and delivery links use.
"""
import html
import logging

from odoo import http
from odoo.addons.web.controllers.home import Home
from odoo.addons.web.controllers.utils import ensure_db
from odoo.http import request

_logger = logging.getLogger(__name__)

_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%(title)s</title>
<style>
 body{margin:0;background:#f3f4f6;font-family:-apple-system,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif;color:#111827}
 .card{max-width:480px;margin:16px auto;background:#fff;border-radius:14px;padding:20px;box-shadow:0 2px 10px rgba(0,0,0,.08)}
 h1{font-size:18px;margin:0 0 4px}.sub{color:#6b7280;font-size:14px;margin-bottom:16px}
 .item{font-size:20px;font-weight:700;margin:8px 0 2px}.qty{color:#374151;margin-bottom:18px}
 .btn{display:block;width:100%%;padding:16px;border:0;border-radius:12px;font-size:18px;font-weight:600;margin:8px 0;cursor:pointer}
 .yes{background:#16a34a;color:#fff}.no{background:#dc2626;color:#fff}.send{background:#2563eb;color:#fff}
 .opt{background:#e5e7eb;color:#111827;text-align:left}.opt.on{background:#111827;color:#fff}
 input{width:100%%;box-sizing:border-box;font-size:26px;padding:12px;border:2px solid #d1d5db;border-radius:12px;text-align:center}
 label{display:block;font-weight:600;margin:14px 0 6px}.hide{display:none}.zh{color:#6b7280;font-weight:400;font-size:14px}
 .ok{font-size:22px;text-align:center;padding:30px 0}.err{color:#dc2626;margin-top:8px}
</style></head><body><div class="card">%(body)s</div>
<script>
function pick(v){document.getElementById('days').value=v;document.querySelectorAll('.opt').forEach(function(b){b.classList.toggle('on',b.dataset.v===v)})}
function yes(){document.getElementById('a').value='yes';document.getElementById('s1').classList.add('hide');document.getElementById('s2').classList.remove('hide');document.getElementById('price').focus()}
function no(){document.getElementById('a').value='no';document.getElementById('f').submit()}
function send(){var p=document.getElementById('price').value;if(!p||isNaN(p)||Number(p)<=0){document.getElementById('e').textContent='Please type the price / 请输入价格';return}
if(!document.getElementById('days').value){document.getElementById('e').textContent='Please choose the delivery time / 请选择交货时间';return}document.getElementById('f').submit()}
</script></body></html>"""

_FORM = """<h1>Price check #%(ref)s <span class="zh">询价</span></h1>
<div class="sub">%(shop)s</div>
<div class="item">%(name)s</div><div class="qty">Quantity / 数量: <b>%(qty)s</b></div>
%(already)s
<form id="f" method="post" action="%(action)s">
<input type="hidden" name="answer" id="a" value=""><input type="hidden" name="days" id="days" value="">
<div id="s1">
 <button type="button" class="btn yes" onclick="yes()">✅ In stock <span class="zh" style="color:#dcfce7">有货</span></button>
 <button type="button" class="btn no" onclick="no()">❌ No stock <span class="zh" style="color:#fee2e2">没有</span></button>
</div>
<div id="s2" class="hide">
 <label>Your price per unit <span class="zh">单价</span> (%(cur)s)</label>
 <input type="number" step="0.01" min="0" inputmode="decimal" name="price" id="price" placeholder="45">
 <label>Delivery time <span class="zh">交货时间</span></label>
 <button type="button" class="btn opt" data-v="1" onclick="pick('1')">1 · Ready stock <span class="zh">现货</span></button>
 <button type="button" class="btn opt" data-v="2" onclick="pick('2')">2 · 1-3 days <span class="zh">1-3天</span></button>
 <button type="button" class="btn opt" data-v="3" onclick="pick('3')">3 · 4-7 days <span class="zh">4-7天</span></button>
 <button type="button" class="btn opt" data-v="4" onclick="pick('4')">4 · More than 7 days <span class="zh">7天以上</span></button>
 <div id="e" class="err"></div>
 <button type="button" class="btn send" onclick="send()">Send <span class="zh" style="color:#dbeafe">发送</span></button>
</div>
</form>"""


def _page(title, body, status=200):
    return request.make_response(_PAGE % {'title': title, 'body': body}, status=status,
                                 headers=[('Content-Type', 'text/html; charset=utf-8'),
                                          ('Cache-Control', 'no-store')])


def _row(token):
    if not token or len(token) < 10:
        return request.env['sa.wechat.message'].sudo()
    return request.env['sa.wechat.message'].sudo().search(
        [('wx_token', '=', token), ('direction', '=', 'out')], limit=1)


class WeChatVendorPageEntry(Home):
    """Doorway: bind the database from `?db=`, then send the vendor to the
    page. A cold public route on a multi-database server cannot find its
    database by itself (see sales_automation's wa_link_entry)."""

    @http.route()
    def web_client(self, s_action=None, **kw):
        if kw.get('subpath') != 'wx':
            return super().web_client(s_action=s_action, **kw)
        ensure_db()
        if not request.db:
            return request.not_found()
        token = (kw.get('t') or '').strip()
        if not token or not all(c.isalnum() or c in '-_' for c in token) or len(token) > 64:
            return request.not_found()
        return request.redirect('/sa/wx/%s' % token, code=303)


class WeChatVendorPage(http.Controller):

    @http.route('/sa/wx/<string:token>', type='http', auth='public', methods=['GET'], csrf=False)
    def vendor_page(self, token, **kw):
        row = _row(token)
        if not row or not row.request_id or not row.partner_id:
            return _page('Not found', '<div class="ok">This link is not valid.<br><span class="zh">此链接无效。</span></div>', 404)
        req = row.request_id
        name, qty = req._sa_wechat_item()
        quote = request.env['sa.vendor.quote'].sudo().search(
            [('request_id', '=', req.id), ('partner_id', '=', row.partner_id.id)], order='id desc', limit=1)
        already = ''
        if quote:
            already = ('<div class="sub">Already answered: %s %.2f. You can send a new answer below.'
                       '<br><span class="zh">已回复：%s %.2f。可在下方重新回复。</span></div>'
                       % (req.currency_id.symbol or '', quote.price, req.currency_id.symbol or '', quote.price))
        elif row.partner_id in req.sa_vendor_no_ids:
            already = '<div class="sub">Already answered: no stock. You can change it below.<br><span class="zh">已回复：没有。可在下方修改。</span></div>'
        if req.state not in ('sourcing',) and not req.sa_price_stalled:
            already += '<div class="sub">This price check is closed; a new answer is still recorded for the shop.<br><span class="zh">此询价已结束；新回复仍会记录。</span></div>'
        body = _FORM % {
            'ref': html.escape(req.ref_code or ''), 'shop': html.escape(request.env.company.name or ''),
            'name': html.escape(name), 'qty': html.escape(qty.replace(' x ', '') or '1'),
            'cur': html.escape(req.currency_id.symbol or req.currency_id.name or ''),
            'action': '/sa/wx/%s/answer' % token, 'already': already,
        }
        return _page('Price check #%s' % (req.ref_code or ''), body)

    @http.route('/sa/wx/<string:token>/answer', type='http', auth='public', methods=['POST'], csrf=False)
    def vendor_answer(self, token, **post):
        row = _row(token)
        if not row or not row.request_id or not row.partner_id:
            return _page('Not found', '<div class="ok">This link is not valid.<br><span class="zh">此链接无效。</span></div>', 404)
        try:
            result = request.env['sa.wechat.message'].sudo()._sa_page_answer(
                row, post.get('answer'), post.get('price'), post.get('days'))
        except Exception as err:  # noqa: BLE001
            _logger.exception("WeChat page answer failed for row %s", row.id)
            return _page('Error', '<div class="ok">Sorry, that did not work: %s<br><span class="zh">抱歉，提交失败。</span></div>'
                         % html.escape(str(err)), 500)
        if result.get('result') == 'no_stock':
            msg = 'No problem, thank you.<br><span class="zh">没关系，谢谢。</span>'
        elif result.get('result') == 'quoted':
            msg = ('Received: %s %.2f, %s. Thank you!<br><span class="zh">已收到：%s %.2f，%s。谢谢！</span>'
                   % (html.escape(result.get('cur') or ''), result['price'], html.escape(result.get('days_en') or ''),
                      html.escape(result.get('cur') or ''), result['price'], html.escape(result.get('days_zh') or '')))
        else:
            msg = 'Please choose In stock or No stock.<br><span class="zh">请选择有货或没有。</span>'
        back = '<a class="btn opt" style="text-align:center;text-decoration:none" href="/sa/wx/%s">Change my answer <span class="zh">修改回复</span></a>' % token
        return _page('Thank you', '<div class="ok">%s</div>%s' % (msg, back))
