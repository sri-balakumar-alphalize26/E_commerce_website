# -*- coding: utf-8 -*-
"""The product confirmation page, laid out like the 369 Mart product page
(13 Nov 2026, design 1): photos, name, price, REJECT / ACCEPT - pinned to the
bottom of a phone screen - then the details. Public route; the token in the link is the whole credential
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
from odoo.tools.image import image_process

_logger = logging.getLogger(__name__)

_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=5"><meta name="robots" content="noindex">
<meta name="theme-color" content="#0b4a6e"><title>%(title)s</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet" media="print" onload="this.media='all'">
<style>
 /* 13 Nov 2026, design 1 "Shop page": the 369 Mart product page look. Phone first: one column,
    the two answers pinned at the bottom; from 860 px photos left, name/price/answers right. */
 :root{--navy:#0b4a6e;--blue:#0a78ab;--ink:#13212b;--muted:#52616d;--soft:#f6f8fa;--line:#e6ebef;--ok:#1a7f3c;--ok-bg:#e3f3e8;--err:#a3322a;--err-bg:#fbe9e7}
 *{box-sizing:border-box}
 html,body{overflow-x:hidden}
 body{margin:0;background:var(--soft);font:15px/1.5 "Inter",ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif;color:var(--ink);-webkit-font-smoothing:antialiased}
 .brand{display:flex;align-items:center;gap:10px;padding:10px 16px;background:#fff;border-bottom:1px solid var(--line);position:sticky;top:0;z-index:5}
 .brand img{height:32px;width:auto;display:block}
 .badge{margin-left:auto;display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:600;color:#3d4c58;border:1px solid #e3e9ee;border-radius:999px;padding:5px 10px;white-space:nowrap}
 .ask{display:flex;flex-wrap:wrap;align-items:baseline;gap:4px 10px;padding:10px 16px;background:#e5f2f9;color:var(--navy);font-weight:700;font-size:14px}
 .ask small{margin-left:auto;font-weight:500;color:#3d5c70;white-space:nowrap}
 .wrap{max-width:1120px;margin:0 auto;padding:14px 16px 28px;display:flex;flex-direction:column;gap:14px}
 .card{background:#fff;border:1px solid var(--line);border-radius:16px;padding:16px}
 .zh{color:var(--muted);font-weight:400;font-size:.85em}
 .top{display:grid;gap:14px}
 .picbox{height:min(360px,78vw);border-radius:18px;background:#fff;border:1px solid var(--line);display:flex;align-items:center;justify-content:center;overflow:hidden;position:relative}
 .pic{width:100%%;height:100%%;object-fit:contain;display:block;cursor:zoom-in}
 .zoom{position:absolute;right:10px;bottom:10px;font-size:12px;font-weight:600;color:#3d4c58;background:#fff;border:1px solid #e3e9ee;border-radius:999px;padding:5px 10px;pointer-events:none}
 .zoom .zh-hover{display:none}
 /* Hover zoom, like the storefront product page: a lens on the picture and a
    magnified pane over the right-hand column. Mouse only, 860 px and wider. */
 .media{position:relative;z-index:8}
 .lens{position:absolute;display:none;pointer-events:none;border-radius:8px;background:rgba(10,120,171,.12);border:1.5px solid rgba(10,120,171,.55);box-shadow:0 0 0 9999px rgba(255,255,255,.35)}
 .zp{display:none;position:absolute;top:0;left:calc(100%% + 20px);width:440px;height:440px;z-index:7;background:#fff no-repeat;border:1px solid var(--line);border-radius:20px;box-shadow:0 24px 50px -24px rgba(19,33,43,.45);pointer-events:none}
 @media(hover:hover) and (pointer:fine) and (min-width:860px){.zoom .zh-touch{display:none}.zoom .zh-hover{display:inline}}
 @media(max-width:859px){.lens,.zp{display:none !important}}
 .gal{display:flex;gap:8px;margin-top:10px;overflow-x:auto;padding-bottom:2px}
 .gal img{flex:0 0 64px;width:64px;height:64px;object-fit:contain;border-radius:12px;border:1.5px solid var(--line);cursor:pointer;background:#fff}
 .gal img.on{border-color:var(--blue)}
 .note{color:var(--muted);font-size:12.5px;margin-top:6px}
 .nopic{padding:40px 10px;text-align:center;color:var(--muted);border:1px dashed #cfd8df;border-radius:14px;background:#fff}
 .info{display:flex;flex-direction:column;gap:12px}
 .nm{margin:0;font-size:21px;font-weight:800;letter-spacing:-.01em;line-height:1.25;overflow-wrap:anywhere}
 .attrs{display:flex;flex-wrap:wrap;gap:6px}
 .attrs span{background:#fff;border:1px solid #e3e9ee;border-radius:999px;padding:5px 10px;font-size:13px;color:#3d4c58;overflow-wrap:anywhere}
 .attrs b{color:var(--ink)}
 .price{display:flex;flex-wrap:wrap;align-items:baseline;gap:4px 10px}
 .price b{font-size:24px;font-weight:800;color:var(--navy)}
 .price span{font-size:14px;color:var(--muted)}
 .price s{font-size:14px;color:var(--muted)}
 .price .off{font-style:normal;font-size:13px;font-weight:800;color:#fff;background:#e2552d;border-radius:6px;padding:2px 7px}
 .total{font-size:14px;color:#3d4c58}.total b{color:var(--ink);font-size:16px}
 .rate{display:inline-flex;align-items:center;gap:8px;text-decoration:none;font-size:13px;color:var(--muted);align-self:flex-start}
 .rate b{background:var(--ok);color:#fff;border-radius:6px;padding:2px 8px;font-size:13px}
 .dlv{display:inline-flex;align-items:center;gap:6px;align-self:flex-start;border-radius:999px;padding:6px 12px;font-size:13.5px;font-weight:700}
 .dlv-quick{background:#fff1de;color:#a35a00}
 .dlv-express{background:#e5f2f9;color:#0b4a6e}
 .stock{display:flex;align-items:center;gap:8px;font-size:14px;font-weight:700}
 .stock i{width:9px;height:9px;border-radius:50%%;flex:none}
 .st-ok{color:#17703a}.st-ok i{background:var(--ok)}
 .st-low{color:#8a4f00}.st-low i{background:#f7931e}
 .st-none{color:#8a4f00}.st-none i{background:#c3ccd3}
 .rbig{display:flex;align-items:baseline;gap:10px;margin-bottom:6px}
 .rbig b{font-size:30px;font-weight:800}.rbig small{color:var(--muted)}
 .sim-sub{margin:-2px 0 12px;font-size:14px;color:var(--muted)}
 .sim-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
 .sim-item{display:flex;flex-direction:column;gap:4px;padding:10px;border:1px solid var(--line);border-radius:14px;text-decoration:none;color:var(--ink);background:#fff;transition:transform .15s,box-shadow .15s}
 .sim-item:hover{transform:translateY(-2px);box-shadow:0 10px 20px -16px rgba(19,33,43,.5)}
 .sim-item img,.sim-noimg{width:100%%;height:110px;object-fit:contain;border-radius:10px;background:var(--soft);display:block}
 .sim-item b{font-size:13.5px;line-height:1.3;overflow-wrap:anywhere}
 .sim-item small{font-size:13px;font-weight:700;color:var(--navy)}
 .sim-item em{font-style:normal;font-size:12.5px;font-weight:700;color:var(--ok);margin-top:auto}
 @media(min-width:860px){.sim-grid{grid-template-columns:repeat(4,minmax(0,1fr))}}
 .rv-st{color:#f5a623;letter-spacing:1px}
 .rv{list-style:none;margin:0;padding:0}
 .rv li{padding:10px 0;border-top:1px solid #f0f3f5}
 .rv-hd{display:flex;flex-wrap:wrap;align-items:baseline;gap:4px 8px;font-size:13.5px}.rv-hd small{color:var(--muted)}
 .rv p{margin:4px 0 0;font-size:14px;color:#3d4c58;overflow-wrap:anywhere}
 .trust{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}
 .trust span{display:flex;align-items:center;gap:7px;font-size:13px;font-weight:600;color:#3d4c58;background:#fff;border:1px solid var(--line);border-radius:12px;padding:8px 10px;min-width:0;overflow-wrap:anywhere}
 .trust i{width:22px;height:22px;flex:none;border-radius:7px;background:var(--ok-bg);color:var(--ok);display:grid;place-items:center;font-style:normal;font-size:12px}
 .acts{display:flex;gap:10px}
 .acts form{margin:0;display:flex}
 .acts form.f-no{flex:1}.acts form.f-ok{flex:2}
 .btn{width:100%%;min-height:52px;padding:10px 14px;border-radius:12px;font:inherit;font-size:16px;font-weight:700;cursor:pointer;text-align:center;line-height:1.2}
 .ok{border:0;color:#fff;background:linear-gradient(180deg,#22924a,#17703a);box-shadow:0 10px 18px -12px rgba(23,112,58,.9)}
 .no{border:1.5px solid #e2b4b0;background:#fff;color:var(--err)}
 .btn[disabled]{opacity:.45;cursor:not-allowed}
 .btn .zh{color:inherit;opacity:.9}
 .foot{color:var(--muted);font-size:12px;text-align:center}
 .done{display:flex;gap:12px;align-items:center;border-radius:14px;padding:14px;font-weight:600}
 .done i{width:40px;height:40px;flex:none;border-radius:50%%;display:grid;place-items:center;font-style:normal;color:#fff;font-size:18px}
 .done b{display:block;font-size:16px}.done small{display:block;font-size:12.5px;font-weight:500;margin-top:2px;overflow-wrap:anywhere}
 .done.acc{background:var(--ok-bg);color:#17703a}.done.acc i{background:var(--ok)}
 .done.rej{background:var(--err-bg);color:var(--err)}.done.rej i{background:var(--err)}
 .lower{display:grid;gap:14px;grid-template-columns:minmax(0,1fr)}
 .top{grid-template-columns:minmax(0,1fr)}
 .top>*,.lower>*{min-width:0}
 .sec h2{font-size:16px;font-weight:800;margin:0 0 8px;color:var(--ink)}
 table.dt{width:100%%;border-collapse:collapse;font-size:14px;table-layout:fixed}
 table.dt td{padding:8px 0;border-bottom:1px solid #f0f3f5;vertical-align:top;overflow-wrap:anywhere;word-break:break-word}
 table.dt tr:last-child td{border-bottom:0}
 table.dt td:first-child{color:var(--muted);width:36%%;padding-right:12px}
 table.dt td:last-child{font-weight:600}
 .rich{font-size:15px;line-height:1.6;overflow-wrap:anywhere;color:#3d4c58}
 .rich ul,.rich ol{padding-left:22px;margin:6px 0}.rich li{margin:4px 0}.rich p{margin:6px 0}.rich a{color:var(--blue)}
 .rich img,.rich video,.rich iframe{max-width:100%%;height:auto}
 .rich .tw{overflow-x:auto;-webkit-overflow-scrolling:touch;margin:8px 0;border-radius:10px}
 .rich table{border-collapse:collapse;width:max-content;min-width:100%%;font-size:14px}
 .rich th,.rich td{border:1px solid var(--line);padding:7px 9px;text-align:left;vertical-align:top;overflow-wrap:normal;word-break:normal;min-width:5em;max-width:16em}
 .rich th{background:var(--soft);font-weight:700;color:var(--ink)}
 .show{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
 .show figure{margin:0;grid-column:span 2;min-width:0}
 .show figcaption{font-weight:700;font-size:15px;padding:0 2px 6px}
 .show img{width:100%%;display:block;border-radius:12px}
 @media(max-width:599px){.show figure.half{grid-column:span 2}}
 @media(min-width:600px){.show figure.half{grid-column:span 1}}
 @media(max-width:379px){.trust{grid-template-columns:minmax(0,1fr)}}
 @media(max-width:859px){
   body.open{padding-bottom:150px}
   .bar{position:fixed;left:0;right:0;bottom:0;z-index:6;background:#fff;border-top:1px solid var(--line);padding:8px 16px calc(14px + env(safe-area-inset-bottom));display:flex;flex-direction:column;gap:6px}
 }
 @media(min-width:860px){
   .wrap{padding-top:22px}
   .top{grid-template-columns:minmax(0,1fr) 440px;gap:20px;align-items:start}
   .picbox{height:440px}
   .info{background:#fff;border:1px solid var(--line);border-radius:20px;padding:22px}
   .nm{font-size:26px}
   .price b{font-size:28px}
   .bar{display:flex;flex-direction:column;gap:8px}
   .lower{grid-template-columns:repeat(2,minmax(0,1fr));align-items:start}
   .lower .wide{grid-column:span 2}
 }
 /* ---- motion (13 Nov 2026): the page opens in steps, the buttons press, the answer lands ---- */
 @keyframes sa-rise{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:none}}
 @keyframes sa-drop{from{opacity:0;transform:translateY(-100%%)}to{opacity:1;transform:none}}
 @keyframes sa-up{from{transform:translateY(110%%)}to{transform:none}}
 @keyframes sa-photo{from{opacity:0;transform:scale(.94)}to{opacity:1;transform:none}}
 @keyframes sa-pop{0%%{opacity:0;transform:scale(.6)}60%%{opacity:1;transform:scale(1.08)}100%%{transform:scale(1)}}
 @keyframes sa-draw{to{stroke-dashoffset:0}}
 @keyframes sa-ring{from{box-shadow:0 0 0 0 var(--ring)}to{box-shadow:0 0 0 18px rgba(0,0,0,0)}}
 @keyframes sa-shake{0%%,100%%{transform:none}20%%{transform:translateX(-6px)}40%%{transform:translateX(6px)}60%%{transform:translateX(-4px)}80%%{transform:translateX(3px)}}
 @keyframes sa-spin{to{transform:rotate(360deg)}}
 .ask{animation:sa-drop .45s cubic-bezier(.2,.8,.2,1) backwards}
 .pic{animation:sa-photo .6s cubic-bezier(.2,.8,.2,1) .05s backwards}
 .top>*,.lower>*,.info>*{animation:sa-rise .5s cubic-bezier(.2,.8,.2,1) backwards}
 .top>:nth-child(2){animation-delay:.08s}
 .info>:nth-child(1){animation-delay:.10s}.info>:nth-child(2){animation-delay:.15s}.info>:nth-child(3){animation-delay:.20s}
 .info>:nth-child(4){animation-delay:.25s}.info>:nth-child(5){animation-delay:.30s}.info>:nth-child(n+6){animation-delay:.35s}
 .lower>:nth-child(1){animation-delay:.30s}.lower>:nth-child(2){animation-delay:.38s}.lower>:nth-child(n+3){animation-delay:.46s}
 .gal img{animation:sa-rise .4s ease backwards}.gal img:nth-child(2){animation-delay:.06s}.gal img:nth-child(n+3){animation-delay:.12s}
 .btn{transition:transform .16s cubic-bezier(.2,.8,.2,1),filter .2s,opacity .25s,box-shadow .2s}
 .btn:hover:not([disabled]){transform:translateY(-1px);filter:brightness(1.05)}
 .btn:active:not([disabled]){transform:scale(.96)}
 .btn.busy{opacity:1 !important;cursor:progress}
 .btn.busy::before{content:"";display:inline-block;width:16px;height:16px;margin-right:8px;vertical-align:-3px;border:2.5px solid currentColor;border-right-color:transparent;border-radius:50%%;animation:sa-spin .7s linear infinite}
 .btn.dim{opacity:.35 !important;transform:scale(.97)}
 .done.fresh{animation:sa-pop .5s cubic-bezier(.2,.8,.2,1) backwards}
 .done.fresh i{animation:sa-ring .9s ease-out .25s backwards}
 .done.acc{--ring:rgba(26,127,60,.45)}.done.rej{--ring:rgba(163,50,42,.4)}
 .done.rej.fresh{animation:sa-pop .45s cubic-bezier(.2,.8,.2,1) backwards,sa-shake .45s ease .45s backwards}
 .done svg path{stroke-dasharray:30;stroke-dashoffset:0}
 .done.fresh svg path{stroke-dashoffset:30;animation:sa-draw .45s ease-out .3s forwards}
 @media(max-width:859px){.bar{animation:sa-up .45s cubic-bezier(.2,.8,.2,1) .35s backwards}}
 @media(prefers-reduced-motion:reduce){*,*::before,*::after{animation:none !important;transition:none !important}}
 .ov{display:none;position:fixed;inset:0;background:rgba(10,20,28,.95);z-index:9;overflow:auto;-webkit-overflow-scrolling:touch}
 .ov .in{min-width:100%%;min-height:100%%;display:flex}
 /* margin:auto centres without pushing a zoomed picture's left edge out of reach */
 .ov img{max-width:100vw;max-height:100vh;cursor:zoom-in;display:block;margin:auto;flex:none}
 .ov img.z{max-width:none;max-height:none;width:250vw;cursor:zoom-out}
 .ov .x{position:fixed;top:12px;right:14px;width:40px;height:40px;border-radius:50%%;background:rgba(255,255,255,.16);color:#fff;font-size:20px;line-height:40px;text-align:center;cursor:pointer;z-index:10}
 .ov .tip{position:fixed;left:0;right:0;bottom:16px;text-align:center;color:#c9d6df;font-size:13px;pointer-events:none}
</style></head><body class="%(body_class)s">
<header class="brand"><img src="%(logo)s" alt=""><span class="badge"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/></svg>Secure</span></header>
%(ask)s<main class="wrap">%(body)s</main>
<div class="ov" id="ov" onclick="closeOv()"><span class="x" role="button" aria-label="Close">&#10005;</span><div class="in"><img id="ovimg" alt="" onclick="event.stopPropagation();this.classList.toggle('z')"></div><div class="tip">Tap the picture to zoom in, then move around</div></div>
<script>
function show(i){var m=document.getElementById('main');if(!m)return;var t=document.querySelector('.gal img[data-i="'+i+'"]');
if(t){m.src=t.dataset.big;m.dataset.full=t.dataset.full}else{m.src='/wa/confirm/'+m.dataset.t+'/image/'+i+'.jpg?s=1024';m.dataset.full=''}m.dataset.i=i;
document.querySelectorAll('.gal img').forEach(function(t){t.classList.toggle('on',t.dataset.i==i)})}
function openOv(){var m=document.getElementById('main');if(!m)return;var o=document.getElementById('ovimg');o.classList.remove('z');
/* the page shows 1024 px; full screen shows the original, loaded only now */
o.src=m.src;if(m.dataset.full){var big=new Image();big.onload=function(){if(document.getElementById('ov').style.display==='flex')o.src=m.dataset.full};big.src=m.dataset.full}
document.getElementById('ov').style.display='flex'}
function closeOv(){document.getElementById('ov').style.display='none'}
(function(){
 var fine=window.matchMedia&&matchMedia('(hover: hover) and (pointer: fine)').matches;
 var m=document.getElementById('main'),lens=document.getElementById('lens'),zp=document.getElementById('zp');
 if(!fine||!m||!lens||!zp)return;
 var box=m.parentNode,Z=2.6;
 function hide(){lens.style.display='none';zp.style.display='none'}
 box.addEventListener('mouseleave',hide);
 box.addEventListener('mousemove',function(e){
  if(window.innerWidth<860||!m.naturalWidth){hide();return}
  var b=box.getBoundingClientRect(),s=Math.min(b.width/m.naturalWidth,b.height/m.naturalHeight);
  var w=m.naturalWidth*s,h=m.naturalHeight*s,x=b.left+(b.width-w)/2,y=b.top+(b.height-h)/2;
  if(e.clientX<x||e.clientX>x+w||e.clientY<y||e.clientY>y+h){hide();return}
  zp.style.display='block';lens.style.display='block';
  var pw=zp.clientWidth,ph=zp.clientHeight,lw=Math.min(pw/Z,w),lh=Math.min(ph/Z,h);
  var lx=Math.min(Math.max(e.clientX-lw/2,x),x+w-lw),ly=Math.min(Math.max(e.clientY-lh/2,y),y+h-lh);
  lens.style.left=(lx-b.left)+'px';lens.style.top=(ly-b.top)+'px';lens.style.width=lw+'px';lens.style.height=lh+'px';
  zp.style.backgroundImage='url("'+(m.currentSrc||m.src)+'")';
  zp.style.backgroundSize=(w*Z)+'px '+(h*Z)+'px';
  zp.style.backgroundPosition=(lw<w?-(lx-x)*Z:(pw-w*Z)/2)+'px '+(lh<h?-(ly-y)*Z:(ph-h*Z)/2)+'px';
 });
})();
</script></body></html>"""


def _page(title, body, status=200, ask='', body_class=''):
    # the logo uploaded in the 369 Mart console, else the old setting, else ours
    logo = request.env['sa.brand'].logo_url()
    return request.make_response(_PAGE % {'title': title, 'body': body, 'logo': html.escape(logo),
                                          'ask': ask, 'body_class': body_class}, status=status,
                                 headers=[('Content-Type', 'text/html; charset=utf-8'),
                                          ('Cache-Control', 'no-store')])


def _trust_html(badges):
    """The shop's badges under the price: [{key, text}] → a row of chips."""
    if not badges:
        return ''
    return '<div class="trust">%s</div>' % ''.join(
        '<span><i>&#10003;</i>%s</span>' % html.escape(b.get('text') or '')
        for b in badges if b.get('text'))


def _wrap_tables(rich):
    """A table pasted from a supplier scrolls sideways in its own box on a
    phone instead of pushing the whole page wider than the screen."""
    # str() first: html_sanitize gives Markup, whose replace() escapes its
    # arguments, so '<table' would never be found.
    return str(rich).replace('<table', '<div class="tw"><table').replace('</table>', '</table></div>')


def _shop_sections_html(parts, shown, zh):
    """The shop page's sections under the product, read-only: About this item,
    Product details (rows not already in the table above), Description, From
    the manufacturer. HTML is sanitised again here whatever its source."""
    out = []
    if parts.get('about_html'):
        out.append('<section class="card sec"><h2>About this item%s</h2><div class="rich">%s</div></section>'
                   % (zh('商品简介'), _wrap_tables(html_sanitize(parts['about_html'], strip_style=True, strip_classes=True))))
    elif parts.get('about'):
        items = ''.join('<li>%s%s</li>' % ('<b>%s</b> — ' % html.escape(p.get('lead')) if p.get('lead') else '',
                                           html.escape(p.get('text') or '')) for p in parts['about'])
        out.append('<section class="card sec"><h2>About this item%s</h2><div class="rich"><ul>%s</ul></div></section>'
                   % (zh('商品简介'), items))
    rows = [(label, value) for label, value in parts.get('details') or []
            if str(label).strip().lower() not in shown]
    if rows:
        out.append('<section class="card sec"><h2>Product details%s</h2><table class="dt">%s</table></section>' % (zh('商品详情'), ''.join(
            '<tr><td>%s</td><td>%s</td></tr>' % (html.escape(str(label)), html.escape(str(value))) for label, value in rows)))
    if parts.get('description'):
        out.append('<section class="card sec wide"><h2>Description%s</h2><div class="rich">%s</div></section>'
                   % (zh('描述'), _wrap_tables(html_sanitize(parts['description'], strip_style=True, strip_classes=True))))
    blocks = [b for b in parts.get('showcase') or [] if (b.get('src') or '').startswith('/')]
    if blocks:
        out.append('<section class="card sec wide"><h2>From the manufacturer%s</h2><div class="show">%s</div></section>' % (zh('品牌介绍'), ''.join(
            '<figure class="%s">%s<img src="%s" alt="" loading="lazy"></figure>'
            % ('half' if b.get('width') == 'half' else 'full',
               '<figcaption>%s</figcaption>' % html.escape(b['caption']) if b.get('caption') else '',
               html.escape(b['src'])) for b in blocks)))
    return ''.join(out)


# Rows the top of the page already shows (name, price, quantity) or that the
# blue strip shows (reference): matched on the untranslated Chinese label.
_TOP_ROWS = {'产品', '编号', '价格', '数量'}


def _not_found():
    return _page('Not found', '<div class="nopic">This link is not valid.</div>', 404)


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
        """Design 1 of 13 Nov 2026, "Shop page": photos, name, price and the
        two answers like the 369 Mart product page, the details underneath.
        On a phone the answers are pinned to the bottom of the screen."""
        req = link.request_id
        product = req.product_id
        # 13 Nov 2026, owner: English only, supplier links too (they used to
        # carry a Chinese line under each label). `zh` stays so the page is
        # built the same way; it just adds nothing.
        zh = lambda t: ''  # noqa: E731
        title = 'Confirm the product #%s' % (req.ref_code or '')
        ask = ('<div class="ask">%s%s<small>Ref #%s</small></div>'
               % (html.escape('Is this the product you want?' if link.kind == 'customer'
                              else 'Is this the exact product you have?'),
                  zh('请确认此产品' if link.kind == 'customer' else '您有这个产品吗？'),
                  html.escape(req.ref_code or '')))

        # Pictures by size (17 Nov 2026): 1024 px on the page, 256 px in the
        # strip, the original only in the full-screen view. Nothing is read
        # here - each picture is its own cached request.
        pictures = link._picture_entries()

        def pic(i, size=None):
            entry = pictures[i]
            return html.escape('/wa/confirm/%s/image/%d.jpg?%sv=%s' % (
                link.token, i, ('s=%d&' % size) if size else '', entry['version']))

        if pictures:
            media = ('<div class="picbox"><img class="pic" id="main" data-t="%s" data-i="0" src="%s" data-full="%s" '
                     'alt="%s" onclick="openOv()" fetchpriority="high" decoding="async">'
                     '<span class="lens" id="lens"></span>'
                     '<span class="zoom"><span class="zh-touch">Tap to zoom%s</span><span class="zh-hover">Hover to zoom · click for full screen%s</span></span></div>'
                     '<div class="zp" id="zp" aria-hidden="true"></div>'
                     % (link.token, pic(0, 1024), pic(0), html.escape(product.name or ''), zh('点击放大'), zh('悬停放大')))
            if len(pictures) > 1:
                media += '<div class="gal">' + ''.join(
                    '<img src="%s" data-big="%s" data-full="%s" data-i="%d" class="%s" onclick="show(%d)" alt="" '
                    'loading="lazy" decoding="async" width="64" height="64">'
                    % (pic(i, 256), pic(i, 1024), pic(i), i, 'on' if i == 0 else '', i)
                    for i in range(len(pictures))) + '</div>'
            if link.image_source == 'generated':
                media += '<div class="note">Reference picture - the exact unit may differ%s</div>' % zh('参考图片，实物可能不同')
        else:
            media = '<div class="nopic">No photo yet%s</div>' % zh('暂无图片')

        detail_rows = link._details_rows()
        by_cn = {cn: val for _en, cn, val in detail_rows}
        name = by_cn.get('产品') or product.name or ''
        attrs = link._attribute_rows()
        info = '<h1 class="nm">%s</h1>' % html.escape(str(name))
        if attrs:
            info += '<div class="attrs">%s</div>' % ''.join(
                '<span>%s: <b>%s</b></span>' % (html.escape(label), html.escape(value)) for label, value in attrs)
        qty = by_cn.get('数量')
        ex = link._page_extras()
        if ex.get('rating'):
            info += ('<a class="rate" href="#reviews"><b>&#9733; %.1f</b><span>%s rating%s</span></a>'
                     % (ex['rating'], ex['rating_count'], '' if ex['rating_count'] == 1 else 's'))
        if ex.get('price'):
            info += '<div class="price"><b>%s</b>%s<span>each%s</span></div>' % (
                html.escape(ex['price']),
                ('<s>%s</s><em class="off">%d%% OFF</em>' % (html.escape(ex['mrp']), ex['off'])) if ex.get('mrp') else '',
                (' · quantity %s' % ex['qty']) if ex.get('qty') else '')
            if ex.get('total'):
                info += '<div class="total">Total for %s: <b>%s</b></div>' % (ex['qty'], html.escape(ex['total']))
        elif by_cn.get('价格'):
            counted = str(qty or '').isdigit()
            info += '<div class="price"><b>%s</b><span>each%s</span></div>' % (
                html.escape(str(by_cn['价格'])), html.escape(' · quantity %s' % qty) if counted else '')
        elif qty:
            info += '<div class="price"><span>Quantity%s: <b style="font-size:18px">%s</b></span></div>' % (
                zh('数量'), html.escape(str(qty)))
        if ex.get('delivery'):
            mode, when = ex['delivery']
            icon = ('<path d="M13 2L4 14h7l-1 8 9-12h-7z"/>' if mode == 'quick' else
                    '<path d="M3 7h11v9H3z"/><path d="M14 10h4l3 3v3h-7"/><circle cx="7" cy="18" r="1.8"/><circle cx="17" cy="18" r="1.8"/>')
            info += ('<div class="dlv dlv-%s"><svg width="14" height="14" viewBox="0 0 24 24" fill="%s" stroke="currentColor" '
                     'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">%s</svg>%s%s</div>'
                     % (mode, 'currentColor' if mode == 'quick' else 'none', icon,
                        'Quick' if mode == 'quick' else 'Express', html.escape(' · %s' % when) if when else ''))
        if ex.get('stock'):
            tone, text = ex['stock']
            info += '<div class="stock st-%s"><i></i>%s</div>' % (tone, html.escape(text))
        parts = link._shop_sections()
        info += _trust_html(parts.get('trust'))

        if link.decided:
            when = link.decided_on
            stamp = (when.strftime('%d %b %Y %H:%M') + ' UTC') if when else ''
            accepted = link.decided == 'accept'
            # "fresh": the answer was given just now - the tick / cross draws itself.
            fresh = ' fresh' if outcome in ('accept', 'reject') else ''
            icon = ('<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" '
                    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="%s"/></svg>'
                    % ('M5 12l5 5L20 7' if accepted else 'M6 6l12 12M18 6L6 18'))
            info = ('<div class="done %s%s" role="status"><i>%s</i><span><b>%s%s</b><small>%s</small></span></div>'
                    % ('acc' if accepted else 'rej', fresh, icon,
                       'You accepted this product' if accepted else 'You rejected this product',
                       zh('已确认' if accepted else '已拒绝'),
                       html.escape(' · '.join(p for p in (stamp, link.identity or '') if p)))) + info
            if outcome == 'again':
                info += '<div class="foot">Your answer was already recorded and cannot be changed.%s</div>' % zh('您的回复已记录，无法更改。')
            info += '<div class="foot">Your answer is saved. We will carry on in WhatsApp.%s</div>' % zh('您的回复已保存。')
            bar, body_class = '', ''
        else:
            # saving() greys both buttons after the first press: a second tap
            # would send the answer again while the first is still saving.
            # The same words the chat and the manual use: "tap ✔ ACCEPT".
            yes = '&#10004; ACCEPT'
            # The pressed button spins while it saves, the other one fades back.
            bar = ('<div class="bar"><script>function saving(f){if(window.__sent)return false;window.__sent=true;'
                   'var me=f.querySelector(".btn");document.querySelectorAll(".btn").forEach(function(b){'
                   'b.classList.add(b===me?"busy":"dim");b.disabled=true});'
                   'me.innerHTML="Saving&hellip;";return true}</script>'
                   '<div class="acts">'
                   '<form class="f-no" method="post" action="/wa/confirm/%(t)s/reject" onsubmit="return confirm(\'Reject this product?\') &amp;&amp; saving(this)">'
                   '<button class="btn no" type="submit">&#10008; REJECT%(r)s</button></form>'
                   '<form class="f-ok" method="post" action="/wa/confirm/%(t)s/accept" onsubmit="return saving(this)">'
                   '<button class="btn ok" type="submit">%(y)s%(a)s</button></form></div>'
                   '<div class="foot">One answer only - the first tap is final.%(o)s</div></div>'
                   % {'t': link.token, 'y': yes, 'a': zh('接受'), 'r': zh('拒绝'),
                      'o': zh('只能回复一次，首次点击即为最终答复。')})
            body_class = 'open'

        rows = ''.join('<tr><td>%s%s</td><td>%s</td></tr>' % (html.escape(en), zh(html.escape(cn)) if cn != en else '',
                                                             html.escape(str(val)).replace('\n', '<br>'))
                       for en, cn, val in detail_rows if cn not in _TOP_ROWS)
        details = ('<section class="card sec"><h2>Details%s</h2><table class="dt">%s</table></section>'
                   % (zh('详情'), rows)) if rows else ''
        shown = {en.strip().lower() for en, _cn, _v in detail_rows} | {a.strip().lower() for a, _v in attrs}
        reviews = ''
        if ex.get('rating'):
            items = ''.join(
                '<li><div class="rv-hd"><span class="rv-st">%s</span><b>%s</b><small>%s</small></div><p>%s</p></li>'
                % ('&#9733;' * int(r.get('stars') or 0) + '&#9734;' * (5 - int(r.get('stars') or 0)),
                   html.escape(r.get('name') or 'Customer'), html.escape(r.get('when') or ''),
                   html.escape(r.get('text') or '')) for r in ex.get('reviews') or [])
            reviews = ('<section class="card sec" id="reviews"><h2>Ratings and reviews</h2>'
                       '<div class="rbig"><b>%.1f</b><span class="rv-st">%s</span><small>%s rating%s</small></div>%s</section>'
                       % (ex['rating'], '&#9733;' * int(round(ex['rating'])) + '&#9734;' * (5 - int(round(ex['rating']))),
                          ex['rating_count'], '' if ex['rating_count'] == 1 else 's',
                          ('<ul class="rv">%s</ul>' % items) if items else ''))
        # After Reject: products like it, each a WhatsApp "I want ..." link (13 Nov 2026).
        similar = ''
        if link.kind == 'customer' and link.decided == 'reject':
            items = link._similar_after_reject()
            if items:
                cards = ''.join(
                    '<a class="sim-item" href="%s" target="_blank" rel="noopener">%s<b>%s</b>%s<em>Ask on WhatsApp</em></a>'
                    % (html.escape(i['url']),
                       ('<img src="%s" alt="" loading="lazy">' % html.escape(i['image'])) if i['image'] else '<span class="sim-noimg"></span>',
                       html.escape(i['name']), ('<small>%s</small>' % html.escape(i['price'])) if i['price'] else '')
                    for i in items)
                similar = ('<section class="card sec wide sim"><h2>Not this one?</h2>'
                           '<p class="sim-sub">Tap one of these to ask us on WhatsApp. We are also looking for the right one for you.</p>'
                           '<div class="sim-grid">%s</div></section>' % cards)
        body = ('<div class="top"><div class="media">%s</div><div class="info">%s%s</div></div>'
                '<div class="lower">%s%s%s%s</div>'
                % (media, info, bar, similar, details, reviews, _shop_sections_html(parts, shown, zh)))
        return _page(title, body, ask=ask, body_class=body_class)

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
                return _page('One moment', '<div class="nopic">Loading your product page&hellip;</div>'
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

    # `.jpg`: Cloudflare caches by file extension, so the page asks for
    # /image/<n>.jpg; the addresses without it keep working.
    @http.route(['/wa/confirm/<string:token>/image', '/wa/confirm/<string:token>/image/<int:n>',
                 '/wa/confirm/<string:token>/image/<int:n>.jpg'],
                type='http', auth='public', methods=['GET'], csrf=False, readonly=True)
    def image(self, token, n=0, s=None, v=None, **kw):
        """One picture, at the size asked for (17 Nov 2026).

        `s=1024` the main picture, `s=256` a thumbnail, no `s` the original (the
        zoom view, and older links such as the WeChat file). Only picture `n` is
        read. `v` is the picture's checksum: an address that carries it never
        changes content, so phones and Cloudflare keep it for a year instead of
        coming back to the server for every picture."""
        link = self._link(token)
        if not link:
            return request.not_found()
        entries = link._picture_entries()
        if not 0 <= n < len(entries):
            return request.not_found()
        entry = entries[n]
        size = {'1024': 1024, '512': 512, '256': 256}.get(str(s or ''), 0)
        cache = ('public, max-age=31536000, immutable' if v and v == entry['version']
                 else 'public, max-age=600')
        if 'raw' in entry:
            raw = entry['raw']
            if size:
                try:
                    raw = image_process(raw, size=(size, size))
                except Exception:  # noqa: BLE001 - the original is still a picture
                    pass
            return request.make_response(raw, headers=[('Content-Type', 'image/jpeg'),
                                                       ('Content-Length', str(len(raw))),
                                                       ('Cache-Control', cache)])
        record, field = entry['record'], entry['field']
        # image.mixin keeps every size ready (image_1024, image_variant_256 ...)
        sized = field.replace('1920', str(size)) if size and '1920' in field else field
        if sized not in record._fields:
            sized = field
        # On the image server: the browser loads it from there (the smaller
        # copy's own address when it has one, else the original's - never
        # downloaded here to be shrunk).
        remote = link._picture_remote_url(link._picture_attachment(record, sized)) if sized != field else ''
        remote = remote or (entry['url'] if sized == field else '')
        if remote:
            return request.redirect(remote, code=302, local=False)
        try:
            stream = request.env['ir.binary'].sudo()._get_image_stream_from(
                record.sudo(), sized,
                width=size if sized == field else 0, height=size if sized == field else 0)
        except Exception:  # noqa: BLE001 - a missing picture is a 404, never a 500
            _logger.info("Sales Automation: picture %s of link %s not readable", n, link.id, exc_info=True)
            return request.not_found()
        response = stream.get_response()
        response.headers['Cache-Control'] = cache
        return response

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
