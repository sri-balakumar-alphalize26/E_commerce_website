# -*- coding: utf-8 -*-
"""The product confirmation page: picture on top, details in a table, ACCEPT /
REJECT below. Public route; the token in the link is the whole credential
and is compared in constant time. Every open and press is logged.

`/scoped_app/c?db=<db>&t=<token>` is the short doorway (binds the database
first, then redirects), `/wa/confirm/<token>` the page, `/wa/confirm/<token>/image`
the picture, `/wa/confirm/<token>/accept|reject` the decision (POST only).
"""
import html
import logging

from odoo import http
from odoo.addons.web.controllers.home import Home
from odoo.addons.web.controllers.utils import ensure_db
from odoo.http import request
from odoo.tools import html_sanitize

_logger = logging.getLogger(__name__)

_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=5"><meta name="robots" content="noindex">
<meta name="theme-color" content="#0b4a6e"><title>%(title)s</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
 :root{--navy:#0b4a6e;--blue:#0a78ab;--btn-a:#0c86be;--btn-b:#08658f;--orange:#f7931e;--ink:#13212b;--muted:#6b7a86;--soft:#f4f6f8;--line:#e6ebef;--ok:#1a7f3c;--ok-bg:#e9f6ee;--err:#c8433a;--err-bg:#fdecea}
 *{box-sizing:border-box}
 body{margin:0;background:var(--soft);font:14px/1.5 "Inter",ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif;color:var(--ink);-webkit-font-smoothing:antialiased}
 .brand{display:flex;align-items:center;gap:10px;padding:10px 16px;background:#fff;border-bottom:1px solid var(--line);position:sticky;top:0;z-index:5}
 .brand img{height:34px;width:auto;display:block}.brand .badge{margin-left:auto;font-size:12px;font-weight:600;color:var(--muted);border:1px solid var(--line);border-radius:999px;padding:4px 10px}
 .wrap{max-width:1000px;margin:0 auto;padding:14px 16px 28px}
 .card{background:#fff;border:1px solid var(--line);border-radius:16px;padding:18px}
 h1{font-size:21px;font-weight:800;letter-spacing:-.02em;color:var(--navy);margin:0 0 2px;line-height:1.25}.sub{color:var(--muted);font-size:13px;margin-bottom:12px}.zh{color:var(--muted);font-weight:400;font-size:13px}
 .picbox{height:min(400px,82vw);border-radius:12px;background:var(--soft);border:1px solid var(--line);display:flex;align-items:center;justify-content:center;overflow:hidden}
 .pic{width:100%%;height:100%%;object-fit:contain;display:block;cursor:zoom-in}
 .grid{display:grid;gap:18px}@media(min-width:860px){.grid{grid-template-columns:1fr 1fr;gap:28px;align-items:start}.grid table{margin-top:0}}
 .trust{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:12px 0}.trust span{display:flex;gap:8px;align-items:center;background:var(--soft);border:1px solid var(--line);border-radius:10px;padding:8px 10px;font-size:13px;font-weight:600}
 .sec{border-top:1px solid var(--line);margin-top:18px;padding-top:14px}.sec h2{font-size:17px;font-weight:800;color:var(--navy);margin:0 0 8px}
 .rich{font-size:15px;line-height:1.6;overflow-wrap:anywhere}.rich ul,.rich ol{padding-left:22px;margin:6px 0}.rich li{margin:4px 0}.rich p{margin:6px 0}.rich img{max-width:100%%;height:auto}.rich a{color:var(--blue)}
 .show{display:grid;grid-template-columns:1fr 1fr}.show figure{margin:0;grid-column:span 2}.show figure.half{grid-column:span 1}.show figcaption{font-weight:700;font-size:15px;padding:10px 4px 6px}.show img{width:100%%;display:block}
 .nopic{padding:40px 10px;text-align:center;color:var(--muted);border:1px dashed #cfd8df;border-radius:12px}
 table{width:100%%;border-collapse:collapse;margin:14px 0 6px;font-size:15px}
 td{padding:9px 6px;border-bottom:1px solid var(--line);vertical-align:top}td:first-child{color:var(--muted);width:38%%;font-weight:600}
 .btn{display:block;width:100%%;min-height:44px;padding:12px 16px;border:0;border-radius:12px;font:inherit;font-size:17px;font-weight:700;margin:10px 0;cursor:pointer;text-align:center;color:#fff}
 .ok{background:linear-gradient(180deg,var(--btn-a),var(--btn-b));box-shadow:0 6px 14px -8px rgba(8,101,143,.7)}.no{background:#eef2f5;color:var(--ink)}
 .btn[disabled]{opacity:.45;cursor:not-allowed}
 .banner{padding:14px;border-radius:12px;margin:12px 0;font-weight:600}.banner.acc{background:var(--ok-bg);color:var(--ok)}.banner.rej{background:var(--err-bg);color:var(--err)}
 .foot{color:var(--muted);font-size:12px;text-align:center;margin-top:8px}
 .gal{display:flex;gap:8px;margin-top:8px;overflow-x:auto}.gal img{flex:1 0 76px;min-width:0;height:84px;object-fit:cover;border-radius:10px;border:2px solid var(--line);cursor:pointer;background:var(--soft)}
 .gal img.on{border-color:var(--blue)}.hint{color:var(--muted);font-size:12px;text-align:center;margin-top:4px}
 .attrs{display:flex;flex-wrap:wrap;gap:6px;justify-content:center;margin:10px 0 4px}.attrs span{background:var(--soft);border:1px solid var(--line);border-radius:999px;padding:4px 10px;font-size:13px}.attrs b{font-weight:700;color:var(--navy)}
 .ov{display:none;position:fixed;inset:0;background:rgba(0,0,0,.92);z-index:9;align-items:center;justify-content:center;overflow:auto;touch-action:pinch-zoom}
 .ov img{max-width:100%%;max-height:100%%;transition:transform .15s;cursor:zoom-in}.ov img.z{transform:scale(2.5);cursor:zoom-out}
 .ov .x{position:fixed;top:12px;right:16px;color:#fff;font-size:30px;line-height:1;cursor:pointer}
</style></head><body>
<header class="brand"><img src="%(logo)s" alt=""><span class="badge">&#128274; Secure</span></header>
<div class="wrap"><div class="card">%(body)s</div></div>
<div class="ov" id="ov" onclick="closeOv()"><span class="x">&#10005;</span><img id="ovimg" alt="" onclick="event.stopPropagation();this.classList.toggle('z')"></div>
<script>
function show(i){var m=document.getElementById('main');if(!m)return;m.src='/wa/confirm/'+m.dataset.t+'/image/'+i;m.dataset.i=i;
document.querySelectorAll('.gal img').forEach(function(t){t.classList.toggle('on',t.dataset.i==i)})}
function openOv(){var m=document.getElementById('main');if(!m)return;var o=document.getElementById('ovimg');o.classList.remove('z');o.src=m.src;document.getElementById('ov').style.display='flex'}
function closeOv(){document.getElementById('ov').style.display='none'}
</script></body></html>"""


def _page(title, body, status=200):
    logo = (request.env['ir.config_parameter'].sudo().get_param('sa.brand_logo_url', '')
            or '/sales_automation/static/src/img/369mart-logo.png')
    return request.make_response(_PAGE % {'title': title, 'body': body, 'logo': html.escape(logo)}, status=status,
                                 headers=[('Content-Type', 'text/html; charset=utf-8'),
                                          ('Cache-Control', 'no-store')])


_TRUST_ICON = {'returns': '&#8635;', 'warranty': '&#128737;', 'cod': '&#128176;', 'secure': '&#128274;'}


def _trust_html(badges):
    """The shop's badges under the price: [{key, text}] → a row of chips."""
    if not badges:
        return ''
    return '<div class="trust">%s</div>' % ''.join(
        '<span>%s %s</span>' % (_TRUST_ICON.get(b.get('key'), '&#10004;'), html.escape(b.get('text') or ''))
        for b in badges if b.get('text'))


def _shop_sections_html(parts, shown, zh):
    """The shop page's sections under the product, read-only: About this item,
    Product details (rows not already in the table above), Description, From
    the manufacturer. HTML is sanitised again here whatever its source."""
    out = []
    if parts.get('about_html'):
        out.append('<div class="sec"><h2>About this item%s</h2><div class="rich">%s</div></div>'
                   % (zh('商品简介'), html_sanitize(parts['about_html'], strip_style=True, strip_classes=True)))
    elif parts.get('about'):
        items = ''.join('<li>%s%s</li>' % ('<b>%s</b> — ' % html.escape(p.get('lead')) if p.get('lead') else '',
                                           html.escape(p.get('text') or '')) for p in parts['about'])
        out.append('<div class="sec"><h2>About this item%s</h2><div class="rich"><ul>%s</ul></div></div>'
                   % (zh('商品简介'), items))
    rows = [(label, value) for label, value in parts.get('details') or []
            if str(label).strip().lower() not in shown]
    if rows:
        out.append('<div class="sec"><h2>Product details%s</h2><table>%s</table></div>' % (zh('商品详情'), ''.join(
            '<tr><td>%s</td><td>%s</td></tr>' % (html.escape(str(label)), html.escape(str(value))) for label, value in rows)))
    if parts.get('description'):
        out.append('<div class="sec"><h2>Description%s</h2><div class="rich">%s</div></div>'
                   % (zh('描述'), html_sanitize(parts['description'], strip_style=True, strip_classes=True)))
    blocks = [b for b in parts.get('showcase') or [] if (b.get('src') or '').startswith('/')]
    if blocks:
        out.append('<div class="sec"><h2>From the manufacturer%s</h2><div class="show">%s</div></div>' % (zh('品牌介绍'), ''.join(
            '<figure class="%s">%s<img src="%s" alt="" loading="lazy"></figure>'
            % ('half' if b.get('width') == 'half' else 'full',
               '<figcaption>%s</figcaption>' % html.escape(b['caption']) if b.get('caption') else '',
               html.escape(b['src'])) for b in blocks)))
    return ''.join(out)


def _not_found():
    return _page('Not found', '<div class="nopic">This link is not valid.<br><span class="zh">此链接无效。</span></div>', 404)


def _client():
    req = request.httprequest
    ip = (req.headers.get('CF-Connecting-IP') or req.headers.get('X-Forwarded-For') or req.remote_addr or '')
    ip = ip.split(',')[0].strip()
    return ip, req.headers.get('User-Agent') or ''


class SaConfirmEntry(Home):
    """Short doorway: bind the database from `?db=`, then hand over."""

    @http.route()
    def web_client(self, s_action=None, **kw):
        if kw.get('subpath') != 'c':
            return super().web_client(s_action=s_action, **kw)
        ensure_db()
        if not request.db:
            return request.not_found()
        token = (kw.get('t') or '').strip()
        if not token or not all(c.isalnum() or c in '-_' for c in token) or len(token) > 64:
            return request.not_found()
        target = '/wa/confirm/%s' % token
        if str(kw.get('img') or '') == '1':
            target += '/image'
        return request.redirect(target, code=303)


class SaConfirmPage(http.Controller):

    def _link(self, token):
        return request.env['sa.confirm.link'].sudo()._by_token(token)

    def _render(self, link, outcome=None):
        req = link.request_id
        product = req.product_id
        bilingual = link.kind == 'vendor'
        zh = (lambda t: ' <span class="zh">%s</span>' % t) if bilingual else (lambda t: '')
        title = 'Confirm the product #%s' % (req.ref_code or '')
        head = ('<h1>%s%s</h1><div class="sub">%s</div>'
                % (html.escape('Please confirm this product' if link.kind == 'customer' else 'Is this the exact product you have?'),
                   zh('请确认此产品' if link.kind == 'customer' else '您有这个产品吗？'),
                   html.escape('%s · Ref #%s' % (request.env.company.name or '', req.ref_code or ''))))
        pictures = link._picture_items()
        if pictures:
            pic = ('<div class="picbox"><img class="pic" id="main" data-t="%s" data-i="0" src="/wa/confirm/%s/image/0" alt="%s" onclick="openOv()"></div>'
                   % (link.token, link.token, html.escape(product.name or '')))
            if len(pictures) > 1:
                pic += '<div class="gal">' + ''.join(
                    '<img src="/wa/confirm/%s/image/%d" data-i="%d" class="%s" onclick="show(%d)" alt="">'
                    % (link.token, i, i, 'on' if i == 0 else '', i) for i in range(len(pictures))) + '</div>'
            pic += '<div class="hint">Tap the picture to zoom%s</div>' % zh('点击图片放大')
            if link.image_source == 'generated':
                pic += '<div class="sub" style="margin-top:4px">Reference picture - the exact unit may differ%s</div>' % zh('参考图片，实物可能不同')
        else:
            pic = '<div class="nopic">No photo yet%s</div>' % zh('暂无图片')
        attrs = link._attribute_rows()
        if attrs:
            pic += '<div class="attrs">%s</div>' % ''.join(
                '<span>%s : <b>%s</b></span>' % (html.escape(label), html.escape(value)) for label, value in attrs)
        detail_rows = link._details_rows()
        rows =''.join('<tr><td>%s%s</td><td>%s</td></tr>' % (html.escape(en), zh(html.escape(cn)) if cn != en else '',
                                                               html.escape(str(val)).replace('\n', '<br>'))
                       for en, cn, val in detail_rows)
        table = '<table>%s</table>' % rows
        if link.decided:
            when = link.decided_on
            stamp = (when.strftime('%d %b %Y %H:%M') + ' UTC') if when else ''
            if link.decided == 'accept':
                banner = '<div class="banner acc">&#10004; Accepted%s<br><small>%s · %s</small></div>' % (
                    zh('已确认'), html.escape(stamp), html.escape(link.identity or ''))
            else:
                banner = '<div class="banner rej">&#10008; Rejected%s<br><small>%s · %s</small></div>' % (
                    zh('已拒绝'), html.escape(stamp), html.escape(link.identity or ''))
            if outcome == 'again':
                banner += '<div class="sub">Your answer was already recorded and cannot be changed.%s</div>' % zh('您的回复已记录，无法更改。')
            buttons = ('<button class="btn ok" disabled>&#10004; ACCEPT%s</button>'
                       '<button class="btn no" disabled>&#10008; REJECT%s</button>' % (zh('接受'), zh('拒绝')))
        else:
            banner = ''
            # saving() greys both buttons after the first press: a second tap
            # would send the answer again while the first is still saving.
            buttons = ('<script>function saving(f){if(window.__sent)return false;window.__sent=true;'
                       'document.querySelectorAll(".btn").forEach(function(b){b.disabled=true});'
                       'f.querySelector(".btn").innerHTML="Saving&hellip;";return true}</script>'
                       '<form method="post" action="/wa/confirm/%(t)s/accept" onsubmit="return saving(this)"><button class="btn ok" type="submit">&#10004; ACCEPT%(a)s</button></form>'
                       '<form method="post" action="/wa/confirm/%(t)s/reject" onsubmit="return confirm(\'Reject this product?\') &amp;&amp; saving(this)">'
                       '<button class="btn no" type="submit">&#10008; REJECT%(r)s</button></form>'
                       % {'t': link.token, 'a': zh('接受'), 'r': zh('拒绝')})
        foot = '<div class="foot">One answer only - the first press is final.%s</div>' % zh('只能回复一次，首次点击即为最终答复。')
        shown = {en.strip().lower() for en, _cn, _v in detail_rows} | {a.strip().lower() for a, _v in attrs}
        parts = link._shop_sections()
        badges = _trust_html(parts.get('trust'))
        body = ('<div class="grid"><div>%s</div><div>%s</div></div>'
                % (pic, table + badges + banner + buttons + foot)) + _shop_sections_html(parts, shown, zh)
        return _page(title, head + body)

    @http.route('/wa/confirm/<string:token>', type='http', auth='public', methods=['GET'], csrf=False)
    def page(self, token, **kw):
        link = self._link(token)
        if not link:
            # A well-formed token that is not there yet: the server may still be
            # finishing the send. Wait a moment and try once more.
            well_formed = token and 16 <= len(token) <= 64 and all(c.isalnum() or c in '-_' for c in token)
            tries = int(kw.get('r') or 0) if str(kw.get('r') or '').isdigit() else 0
            if well_formed and tries < 20:
                # up to a minute: the message arrives before the server has finished its work
                return _page('One moment', '<div class="nopic">Loading your product page&hellip;<br>'
                             '<span class="zh">正在加载&hellip;</span></div>'
                             '<script>setTimeout(function(){location.replace("/wa/confirm/%s?r=%d")},3000)</script>'
                             % (html.escape(token), tries + 1))
            return _not_found()
        ip, ua = _client()
        try:
            with request.env.cr.savepoint():
                link._decide('open', ip, ua)
        except Exception:  # noqa: BLE001 - the page still shows
            _logger.exception("Sales Automation: click log failed for link %s", link.id)
        return self._render(link)

    @http.route(['/wa/confirm/<string:token>/image', '/wa/confirm/<string:token>/image/<int:n>'],
                type='http', auth='public', methods=['GET'], csrf=False)
    def image(self, token, n=0, **kw):
        link = self._link(token)
        if not link:
            return request.not_found()
        pictures = link._picture_items()
        raw = pictures[n] if 0 <= n < len(pictures) else b''
        if isinstance(raw, str):
            # On the image server: the browser loads it from there.
            return request.redirect(raw, code=302, local=False)
        mimetype = 'image/jpeg'
        if not raw:
            return request.not_found()
        return request.make_response(raw, headers=[('Content-Type', mimetype or 'image/jpeg'),
                                                   ('Content-Length', str(len(raw))),
                                                   ('Cache-Control', 'private, max-age=600')])

    @http.route(['/wa/confirm/<string:token>/accept', '/wa/confirm/<string:token>/reject'],
                type='http', auth='public', methods=['POST'], csrf=False)
    def decide(self, token, **kw):
        link = self._link(token)
        if not link:
            return _not_found()
        action = 'accept' if request.httprequest.path.endswith('/accept') else 'reject'
        ip, ua = _client()
        outcome = link._decide(action, ip, ua)
        return self._render(link, outcome=outcome)
