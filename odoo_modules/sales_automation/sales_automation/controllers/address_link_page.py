# -*- coding: utf-8 -*-
"""/wa/address/<token> - the private address form (owner, 21 Nov 2026).

The same form as the 369 Mart shop's Delivery Address page
(components/home/AddressForm.jsx): Home / Work / Other, country, full name,
mobile, alternate mobile, pincode (fills the city, state and areas), house,
road / area, city, state, landmark and "Pick on map" - with the shop's
required fields, its messages, and its "Is the postcode right?" check before
saving. Saving hands the address to the group flow, which moves on to the
read-back; the page then says Saved, with a button back to the group.
Public route: the token is the whole credential. See models/sa_address_link.py.
"""
import html
import json
import logging

from odoo import _, http
from odoo.http import request

_logger = logging.getLogger(__name__)

MAPLIBRE = 'https://unpkg.com/maplibre-gl@5.24.0/dist/maplibre-gl'
MAP_STYLE = 'https://tiles.openfreemap.org/styles/liberty'

_CSS = """
:root{--ink:#0f172a;--muted:#64748b;--line:#dbe2ea;--bg:#f4f6f9;--card:#fff;--blue:#0b6fb8;--blue-soft:#e8f2fb;
--ok:#15803d;--bad:#dc2626;--warn:#b45309;--warn-soft:#fff7ed;--radius:14px}
*{box-sizing:border-box}html,body{margin:0}
body{font-family:Inter,system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:var(--bg);color:var(--ink);
-webkit-text-size-adjust:100%}
header{background:#fff;border-bottom:1px solid var(--line);padding:10px 16px;display:flex;align-items:center;gap:12px}
header img{height:38px;width:auto}header .ref{margin-left:auto;color:var(--muted);font-size:13px;font-weight:600}
main{max-width:760px;margin:0 auto;padding:16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:18px}
h1{font-size:20px;margin:0 0 4px}p.sub{margin:0 0 16px;color:var(--muted);font-size:14px}
.chips{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px}
.chips label{border:1px solid var(--line);border-radius:999px;padding:9px 18px;font-weight:600;font-size:15px;cursor:pointer;
background:#fff;user-select:none}
.chips input{position:absolute;opacity:0;pointer-events:none}
.chips label:has(input:checked){border-color:var(--blue);background:var(--blue-soft);color:var(--blue)}
.grid{display:grid;grid-template-columns:1fr;gap:12px}
@media(min-width:600px){.grid{grid-template-columns:1fr 1fr}.span2{grid-column:span 2}}
.f{position:relative;border:1px solid var(--line);border-radius:var(--radius);background:#fff;padding:8px 14px 9px;min-height:60px}
.f:focus-within{border-color:var(--blue);box-shadow:0 0 0 3px var(--blue-soft)}
.f.bad{border-color:var(--bad)}
.f small{display:block;font-size:12px;color:var(--muted);font-weight:600;margin-bottom:2px}
.f input,.f select{border:0;outline:0;width:100%;font:inherit;font-size:16px;color:var(--ink);background:transparent;padding:2px 0}
.f .pre{display:flex;align-items:center;gap:10px}
.f .pre b{font-weight:600;padding-right:10px;border-right:1px solid var(--line);min-width:34px}
.err{color:var(--bad);font-size:13px;margin-top:4px}
.hint{font-size:13px;margin-top:4px;color:var(--muted)}.hint.good{color:var(--ok)}
.areas{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px;align-items:center}
.areas small{color:var(--muted);font-size:12px;width:100%}
.areas button{border:1px solid var(--line);background:#fff;border-radius:999px;padding:6px 12px;font:inherit;font-size:13px;cursor:pointer}
.spot{border:1px solid var(--line);border-radius:var(--radius);padding:12px 14px;display:flex;align-items:center;gap:12px}
.spot .ic{width:40px;height:40px;border-radius:50%;background:var(--bg);display:grid;place-items:center;flex:none;color:var(--muted)}
.spot .ic.on{background:var(--blue-soft);color:var(--blue)}
.spot .ic svg{width:20px;height:20px;fill:none;stroke:currentColor;stroke-width:2}
.spot .t{flex:1}.spot .t b{display:block;font-size:15px}.spot .t span{color:var(--muted);font-size:13px}
.btn{appearance:none;border:1px solid var(--line);background:#fff;color:var(--ink);border-radius:12px;padding:11px 16px;
font:inherit;font-weight:600;font-size:15px;cursor:pointer;text-decoration:none;display:inline-block;text-align:center}
.btn.primary{background:var(--blue);border-color:var(--blue);color:#fff}
.btn.wide{width:100%;padding:15px;font-size:16px}
.btn[disabled]{opacity:.6}
#picker{display:none}#picker.on{display:block}
#picker .help{font-size:14px;margin:0 0 8px}#picker .note{color:var(--muted);font-size:13px;margin:0 0 8px}
.mapwrap{position:relative;height:340px;border-radius:var(--radius);overflow:hidden;border:1px solid var(--line)}
#map{position:absolute;inset:0}
.centerpin{position:absolute;left:50%;top:50%;width:34px;height:34px;margin:-34px 0 0 -17px;pointer-events:none;z-index:2}
.centerpin svg{width:34px;height:34px;fill:var(--blue);stroke:#fff;stroke-width:1.5;filter:drop-shadow(0 2px 3px rgba(0,0,0,.3))}
.maptools{display:flex;gap:8px;margin-top:10px;flex-wrap:wrap}.maptools .grow{flex:1}
.search{display:flex;gap:8px;margin-bottom:8px}
.search input{flex:1;min-width:0;border:1px solid var(--line);border-radius:12px;padding:11px 14px;font:inherit;font-size:16px}
.search input:focus{outline:0;border-color:var(--blue);box-shadow:0 0 0 3px var(--blue-soft)}
.places{display:flex;flex-direction:column;gap:6px;margin-bottom:8px}
.places button{text-align:left;border:1px solid var(--line);background:#fff;border-radius:10px;padding:9px 12px;
font:inherit;font-size:14px;cursor:pointer}
.places button:hover{border-color:var(--blue);background:var(--blue-soft)}
.mismatch{background:var(--warn-soft);border:1px solid #fed7aa;color:var(--warn);border-radius:12px;padding:12px 14px;
margin-top:12px;font-size:14px}.mismatch b{display:block;margin-bottom:2px}
.formerr{color:var(--bad);font-size:14px;margin-top:12px}
.actions{margin-top:16px}
.done{text-align:center;padding:30px 18px}.done .big{font-size:54px;line-height:1}
.done h1{margin:12px 0 6px}.done .addr{background:var(--bg);border-radius:12px;padding:12px 14px;text-align:left;
margin:16px 0;white-space:pre-line;font-size:15px}
.muted{color:var(--muted);font-size:13px}.green{color:var(--ok)}
"""

_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex">
<meta name="theme-color" content="#0b6fb8"><title>%(title)s</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>%(css)s</style></head><body>
<header><img src="%(logo)s" alt="logo"/><span class="ref">%(ref)s</span></header>
<main>%(body)s</main>%(script)s</body></html>"""

PIN_SVG = ('<svg viewBox="0 0 24 24"><path d="M12 22s-7-6.2-7-12a7 7 0 0 1 14 0c0 5.8-7 12-7 12z"/>'
           '<circle cx="12" cy="10" r="2.6"/></svg>')


def _e(value):
    return html.escape(str(value or ''), quote=True)


def _client():
    req = request.httprequest
    ip = (req.headers.get('CF-Connecting-IP') or req.headers.get('X-Forwarded-For') or req.remote_addr or '')
    return ip.split(',')[0].strip(), req.headers.get('User-Agent') or ''


def _page(title, body, ref='', script='', status=200):
    logo = request.env['sa.brand'].sudo().logo_url()
    return request.make_response(
        _PAGE % {'title': _e(title), 'css': _CSS, 'logo': _e(logo), 'ref': _e(ref),
                 'body': body, 'script': script},
        status=status,
        headers=[('Content-Type', 'text/html; charset=utf-8'), ('Cache-Control', 'no-store'),
                 ('X-Robots-Tag', 'noindex')])


def _back_url(link):
    """The group's invite link when the shop gave one, else WhatsApp itself."""
    return link.request_id.sudo().group_id._sa_back_url()


def _gone(link):
    body = ('<div class="card done"><div class="big">&#8987;</div><h1>%s</h1><p class="muted">%s</p>'
            '<a class="btn primary wide" href="%s">%s</a></div>') % (
        _e(_("This link can't be used any more")),
        _e(_("It was already used, it expired, or the address was given in the group.")),
        _e(_back_url(link)), _e(_("Back to WhatsApp group")))
    return _page(_("Link expired"), body, ref='#%s' % link.request_id.sudo()._sa_book_ref(), status=410)


def _saved(link):
    addr = link.address_id.sudo()
    text = addr._sa_addr_title() if addr else ''
    has_pin = bool(addr and (addr.partner_latitude or addr.partner_longitude))
    # owner, 21 Nov 2026: a button back to the group instead of a line of text
    body = ('<div class="card done"><div class="big green">&#10004;</div><h1>%(t)s</h1>'
            '<div class="addr">%(addr)s\n&#128506; %(loc)s</div>'
            '<a class="btn primary wide" href="%(href)s">%(open)s</a>'
            '<p class="muted" style="margin-top:14px">%(once)s</p></div>') % {
        't': _e(_("Address updated") if link.mode == 'edit' else _("Address saved")), 'addr': _e(text),
        'loc': _e(_("Location on map: set") if has_pin else _("Location on map: not set")),
        'href': _e(_back_url(link)),
        'open': _e(_("Back to WhatsApp group")),
        'once': _e(_("This link can't be used again.")),
    }
    return _page(_("Address updated") if link.mode == 'edit' else _("Address saved"), body,
                 ref='#%s' % link.request_id.sudo()._sa_book_ref())


class SaAddressLinkPage(http.Controller):

    def _link(self, token):
        return request.env['sa.address.link'].sudo()._by_token(token)

    def _json(self, token, fn):
        link = self._link(token)
        if not link or not link._alive():
            return request.make_json_response({'ok': False}, status=404)
        return request.make_json_response(fn(link))

    @http.route('/wa/address/<string:token>', type='http', auth='public', methods=['GET', 'POST'],
                csrf=False, sitemap=False)
    def page(self, token, **post):
        link = self._link(token)
        if not link:
            return request.not_found()
        if link.used_on and link.address_id:
            return _saved(link)
        if not link._alive():
            return _gone(link)
        errors = {}
        if request.httprequest.method == 'POST':
            ip, ua = _client()
            try:
                addr, errors = link._submit(post, ip=ip, ua=ua)
            except Exception:  # noqa: BLE001 - say so instead of a server error page
                _logger.exception("Sales Automation: address link %s - saving failed", link.id)
                request.env.cr.rollback()
                errors = {'form': _("Could not save that address. Try again.")}
            if not errors:
                return _saved(link)
        else:
            link._note_open()
        return self._form(link, post if errors else {}, errors)

    # the form's helpers, the shop's /addresses/form, /pincode, /pincode-spot, /pincode-pin
    @http.route('/wa/address/<string:token>/meta', type='http', auth='public', methods=['GET'],
                csrf=False, sitemap=False)
    def meta(self, token, country=None, **kw):
        return self._json(token, lambda link: link._meta((country or '')[:3] or None))

    @http.route('/wa/address/<string:token>/pincode', type='http', auth='public', methods=['GET'],
                csrf=False, sitemap=False)
    def pincode(self, token, pin=None, **kw):
        return self._json(token, lambda link: link._pincode(pin))

    @http.route('/wa/address/<string:token>/spot', type='http', auth='public', methods=['GET'],
                csrf=False, sitemap=False)
    def spot(self, token, pin=None, **kw):
        return self._json(token, lambda link: link._spot(pin))

    @http.route('/wa/address/<string:token>/search', type='http', auth='public', methods=['GET'],
                csrf=False, sitemap=False)
    def search(self, token, q=None, country=None, **kw):
        return self._json(token, lambda link: link._search_place(q, country))

    @http.route('/wa/address/<string:token>/pin-check', type='http', auth='public', methods=['GET'],
                csrf=False, sitemap=False)
    def pin_check(self, token, pin=None, lat=None, lng=None, **kw):
        return self._json(token, lambda link: link._pin_check(pin, lat, lng))

    # ------------------------------------------------------------------
    def _form(self, link, post, errors):
        ctx = link._form_context()
        values = dict(ctx['values'])
        values.update({k: v for k, v in post.items() if isinstance(v, str)})
        meta = link._meta(values.get('country') or None)
        values['country'] = meta['country']['code']
        dial = (meta.get('phone') or {}).get('dial') or ''
        phone_len = (meta.get('phone') or {}).get('length') or 0
        pin_len = meta.get('pin_length') or 0
        val = lambda k: _e(values.get(k, ''))
        err = lambda k: ('<div class="err">%s</div>' % _e(errors[k])) if errors.get(k) else ''
        bad = lambda k: ' bad' if errors.get(k) else ''

        label = (values.get('label') or 'Home').capitalize()
        chips = ''.join(
            '<label><input type="radio" name="label" value="%s"%s/><span>%s</span></label>' % (
                k, ' checked' if label == k else '', _e(_(k)))
            for k in ('Home', 'Work', 'Other'))

        by_code = {c['code']: c for c in meta.get('countries') or []}
        opt = lambda c: '<option value="%s"%s>%s%s</option>' % (
            _e(c['code']), ' selected' if c['code'] == values['country'] else '', _e(c['name']),
            _e('  (%s)' % c['dial']) if c.get('dial') else '')
        suggested = [by_code[c] for c in meta.get('suggested') or [] if c in by_code]
        countries = ('<optgroup label="%s">%s</optgroup><optgroup label="%s">%s</optgroup>' % (
            _e(_("Suggested")), ''.join(opt(c) for c in suggested),
            _e(_("All countries")), ''.join(opt(c) for c in meta.get('countries') or [])))

        def text(name, title, ac='off', extra='', span=False, kind='text', prefix=None, maxlen=None):
            pre = ('<div class="pre"><b class="dial">%s</b>' % _e(prefix or '+')) if prefix is not None else ''
            return ('<div class="%s"><div class="f%s"><small>%s</small>%s<input name="%s" id="f_%s" type="%s" '
                    'value="%s" autocomplete="%s"%s%s/>%s</div>%s</div>') % (
                'span2' if span else '', bad(name), _e(title), pre, name, name, kind, val(name), ac,
                (' maxlength="%s"' % maxlen) if maxlen else '', extra,
                '</div>' if prefix is not None else '', err(name))

        states = ''.join('<option value="%s"%s>%s</option>' % (
            s['id'], ' selected' if str(s['id']) == str(values.get('state_id') or '') else '', _e(s['name']))
            for s in meta.get('states') or [])
        has_pin = bool(values.get('lat') and values.get('lng'))

        body = """
<div class="card">
<h1>%(h)s</h1><p class="sub">%(sub)s</p>
<form method="post" id="addr" novalidate>
<div class="chips" role="radiogroup">%(chips)s</div>
<div class="grid">
<div class="span2"><div class="f%(bad_country)s"><small>%(t_country)s</small>
<select name="country" id="f_country" autocomplete="country">%(countries)s</select></div>%(err_country)s</div>
%(name)s
%(phone)s
%(alt)s
<div>%(pin)s<div class="hint" id="pinhint"></div></div>
%(line)s
<div class="span2">%(area)s<div class="areas" id="areas"></div></div>
%(town)s
<div id="statebox"%(state_hide)s><div class="f%(bad_state)s"><small>%(t_state)s</small>
<select name="state_id" id="f_state_id"><option value="">%(t_pick_state)s</option>%(states)s</select></div>%(err_state)s</div>
%(landmark)s
<div class="span2">
<div class="spot" id="spotrow"><span class="ic%(spot_on)s" id="spotic">%(pin_svg)s</span>
<span class="t"><b id="spottitle">%(t_spot)s</b><span id="spotsub">%(t_spot_sub)s</span></span>
<button type="button" class="btn" id="pickmap">%(t_pick)s</button></div>
<div id="picker"><p class="help"><b>%(t_door)s</b> %(t_drag)s</p>
<div class="search"><input type="search" id="placeq" placeholder="%(t_search_ph)s" autocomplete="off" enterkeyhint="search"/>
<button type="button" class="btn" id="placego">%(t_search)s</button></div>
<div class="places" id="places"></div>
<p class="note" id="mapnote"></p>
<div class="mapwrap"><div id="map"></div><div class="centerpin">%(pin_svg)s</div></div>
<div class="maptools"><button type="button" class="btn" id="here">%(t_here)s</button><span class="grow"></span>
<button type="button" class="btn" id="mapcancel">%(t_cancel)s</button>
<button type="button" class="btn primary" id="mapuse">%(t_use)s</button></div></div>
</div>
</div>
<input type="hidden" name="lat" id="f_lat" value="%(lat)s"/><input type="hidden" name="lng" id="f_lng" value="%(lng)s"/>
<div class="formerr" id="formerr">%(form_err)s</div>
<div class="mismatch" id="mismatch" style="display:none"><b>%(t_right)s</b><span id="mismatchtxt"></span></div>
<div class="actions"><button type="submit" class="btn primary wide" id="save">%(t_save)s</button></div>
<p class="muted" style="text-align:center;margin:12px 0 0">%(t_once)s</p>
</form></div>""" % {
            'h': _e(_("Change address") if ctx['edit'] else _("Delivery address")),
            'sub': _e(_("Fill it in once and save.") if ctx['menu'] else
                      _("For order #%s. Fill it in once and save.") % ctx['ref']),
            'chips': chips, 'countries': countries,
            't_country': _e(_("Country")), 'bad_country': bad('country'), 'err_country': err('country'),
            'name': text('name', _("Full name"), 'name'),
            'phone': text('phone', _("Mobile number"), 'tel-national', ' inputmode="numeric"',
                          prefix=dial, maxlen=phone_len or 15),
            'alt': text('alt', _("Alternate mobile (optional)"), 'off', ' inputmode="numeric"',
                        prefix=dial, maxlen=phone_len or 15),
            'pin': text('pin', _("Postcode"), 'postal-code', ' inputmode="numeric"', maxlen=pin_len or 10),
            'line': text('line', _("House no., building, apartment"), 'address-line1', span=True),
            'area': text('area', _("Street or area"), 'address-line2'),
            'town': text('town', _("City / District / Town"), 'address-level2'),
            'state_hide': '' if meta.get('states') else ' style="display:none"',
            't_state': _e(_("State")), 't_pick_state': _e(_("Select state")), 'states': states,
            'bad_state': bad('state'), 'err_state': err('state'),
            'landmark': text('landmark', _("Landmark (optional)"), span=True),
            'spot_on': ' on' if has_pin else '', 'pin_svg': PIN_SVG,
            't_spot': _e(_("Location on map is set") if has_pin else _("Location on map")),
            't_spot_sub': _e(_("Riders use this pin to find you.") if has_pin else
                             _("Optional, but it shows if Quick delivery reaches you and helps the rider find you.")),
            't_pick': _e(_("Change") if has_pin else _("Pick on map")),
            't_door': _e(_("Put the pin on your door.")),
            't_drag': _e(_("Drag the map; the pin stays in the middle.")),
            't_here': _e(_("Use where I am now")), 't_cancel': _e(_("Cancel")), 't_use': _e(_("Use this spot")),
            't_search_ph': _e(_("Or type your area, street or landmark")), 't_search': _e(_("Search")),
            'lat': val('lat'), 'lng': val('lng'),
            'form_err': _e(errors.get('form') or ''),
            't_right': _e(_("Is the postcode right?")),
            't_save': _e(_("Save address")),
            't_once': _e(_("Only for you · works once")),
        }
        base = '/wa/address/%s' % link.sudo().token
        cfg = {
            'base': base, 'style': MAP_STYLE, 'lib': MAPLIBRE, 'meta': meta,
            'pinFilled': bool(values.get('town')),
            't': {
                'name': _("Enter the receiver's name"),
                'phoneN': _("Enter a %s-digit mobile number"), 'phone': _("Enter a valid mobile number"),
                'altN': _("Enter a %s-digit number, or leave it empty"), 'alt': _("Enter a valid number"),
                'altSame': _("Use a different number, or leave it empty"),
                'pinN': _("Enter a %s-digit postcode"), 'pin': _("Enter a valid postcode"),
                'line': _("Enter the house no., building or apartment"),
                'area': _("Enter the street or area"),
                'town': _("Enter the city, district or town"), 'state': _("Pick a state"),
                'finding': _("Finding your area…"), 'areasIn': _("Areas in %s"),
                'set': _("Location on map is set"), 'setSub': _("Riders use this pin to find you."),
                'change': _("Change"), 'showing': _("Showing %s. Zoom in and move the map to your door."),
                'noHere': _("Your location is not available - move the map to your door instead."),
                'asking': _("Allow location access to put the pin where you are…"),
                'hereNow': _("\U0001F4CD This is where you are now. Move the map if your door is somewhere else."),
                'locOff': _("Location is off. Turn on location (allow it for this page) and tap "
                            "“Use where I am now” - or type your area above."),
                'searching': _("Searching…"), 'noPlace': _("Nothing found - try a nearby area or landmark."),
                'searchFail': _("Search is not available just now - move the map to your door instead."),
                'mismatch': _("Postcode %(pin)s%(place)s, about %(km)s km from where your map pin is. "
                              "Please check the postcode, or save anyway if it's right."),
                'isIn': _(" is in %s"), 'saveAnyway': _("Save anyway"), 'save': _("Save address"),
                'saving': _("Saving…"),
            },
        }
        script = '<script>window.SA_ADDR=%s;</script><script>%s</script>' % (
            json.dumps(cfg).replace('</', '<\\/'), _JS)
        return _page(_("Change address") if ctx['edit'] else _("Delivery address"), body,
                     ref='#%s' % ctx['ref'], script=script)


_JS = r"""
(function(){
var C=window.SA_ADDR,T=C.t,M=C.meta,$=function(i){return document.getElementById(i)};
var fmt=function(s,v){return s.replace('%s',v)};
var get=function(u){return fetch(C.base+u,{credentials:'same-origin'}).then(function(r){return r.json()})};
var auto={town:false,state:false},lastPin=($('f_pin')||{}).value||'',mismatchPin=null,look=null;
function phoneLen(){return (M.phone&&M.phone.length)||0}
function pinLen(){return M.pin_length||0}
function digits(id,max){var el=$(id);if(!el)return;el.addEventListener('input',function(){
  var v=el.value.replace(/\D/g,'');if(max())v=v.slice(0,max());if(v!==el.value)el.value=v;});}
digits('f_phone',function(){return phoneLen()||15});digits('f_alt',function(){return phoneLen()||15});
digits('f_pin',function(){return pinLen()||10});
function setErr(k,msg){var el=$('f_'+(k==='state'?'state_id':k));if(!el)return;var box=el.closest('.f'),wrap=box.parentNode;
  var e=wrap.querySelector(':scope > .err');if(msg){box.classList.add('bad');if(!e){e=document.createElement('div');e.className='err';
  box.insertAdjacentElement('afterend',e);}e.textContent=msg;}else{box.classList.remove('bad');if(e)e.remove();}}
['name','phone','alt','pin','line','area','town','landmark'].forEach(function(k){var el=$('f_'+k);
  if(el)el.addEventListener('input',function(){setErr(k,'');$('formerr').textContent='';if(k==='town')auto.town=false;});});
$('f_state_id').addEventListener('change',function(){setErr('state','');auto.state=false;});
/* the country decides the prefix, the digit counts and the states */
function applyMeta(m){M=m;var dial=(m.phone&&m.phone.dial)||'+';document.querySelectorAll('.dial').forEach(function(b){b.textContent=dial});
  var s=$('f_state_id');s.innerHTML='<option value=""></option>';s.options[0].textContent=s.dataset.ph||'';
  (m.states||[]).forEach(function(x){var o=document.createElement('option');o.value=x.id;o.textContent=x.name;s.appendChild(o)});
  $('statebox').style.display=(m.states&&m.states.length)?'':'none';}
$('f_state_id').dataset.ph=$('f_state_id').options[0].textContent;
$('f_country').addEventListener('change',function(){var code=this.value;
  get('/meta?country='+encodeURIComponent(code)).then(function(m){if(!m||!m.ok)return;applyMeta(m);
    $('f_pin').value='';lastPin='';$('pinhint').textContent='';$('areas').innerHTML='';
    if(auto.town)$('f_town').value='';auto={town:false,state:false};
    ['pin','state','phone','alt','country'].forEach(function(k){setErr(k,'')});});});
/* a full pincode fills the city, the state and the areas */
$('f_pin').addEventListener('input',function(){var pin=this.value;
  if(!M.pin_lookup||pin.length!==pinLen()||pin===lastPin)return;lastPin=pin;
  var h=$('pinhint');h.className='hint';h.textContent=T.finding;
  get('/pincode?pin='+pin).then(function(r){if(pin!==$('f_pin').value)return;look=r;h.textContent='';$('areas').innerHTML='';
    if(!r||!r.ok)return;
    if(r.town&&(!$('f_town').value||auto.town)){$('f_town').value=r.town;auto.town=true;setErr('town','')}
    if(r.state_id&&(!$('f_state_id').value||auto.state)){$('f_state_id').value=String(r.state_id);auto.state=true;setErr('state','')}
    var place=[r.town,r.state].filter(Boolean).join(', ');if(place){h.className='hint good';h.textContent=place}
    var areas=(r.areas||[]).filter(function(a){return a!==$('f_area').value});
    if(areas.length){var box=$('areas'),t=document.createElement('small');t.textContent=fmt(T.areasIn,pin);box.appendChild(t);
      areas.forEach(function(a){var b=document.createElement('button');b.type='button';b.textContent=a;
        b.onclick=function(){$('f_area').value=a;setErr('area','');box.innerHTML=''};box.appendChild(b)});}
  }).catch(function(){h.textContent=''});});
/* the shop form's own checks, word for word */
function check(){var x={},pl=phoneLen(),nl=pinLen(),v=function(k){return ($('f_'+k).value||'').trim()};
  var ok=function(s){return pl?s.length===pl:/^\d{6,15}$/.test(s)};
  if(!v('name'))x.name=T.name;
  if(!ok(v('phone')))x.phone=pl?fmt(T.phoneN,pl):T.phone;
  if(v('alt')&&!ok(v('alt')))x.alt=pl?fmt(T.altN,pl):T.alt;
  if(v('alt')&&v('alt')===v('phone'))x.alt=T.altSame;
  if(nl?v('pin').length!==nl:!/^\d{3,10}$/.test(v('pin')))x.pin=nl?fmt(T.pinN,nl):T.pin;
  if(!v('line'))x.line=T.line;if(!v('area'))x.area=T.area;if(!v('town'))x.town=T.town;
  if((M.states||[]).length&&!$('f_state_id').value)x.state=T.state;return x;}
var form=$('addr'),saving=false;
form.addEventListener('submit',function(ev){if(saving)return;ev.preventDefault();
  var x=check();['name','phone','alt','pin','line','area','town','state'].forEach(function(k){setErr(k,x[k]||'')});
  var keys=Object.keys(x);if(keys.length){var first=$('f_'+(keys[0]==='state'?'state_id':keys[0]));if(first)first.focus();return;}
  var pin=$('f_pin').value,lat=$('f_lat').value,lng=$('f_lng').value,btn=$('save');
  var go=function(){saving=true;btn.disabled=true;btn.textContent=T.saving;form.submit();};
  if(lat&&lng&&mismatchPin!==pin){btn.disabled=true;
    get('/pin-check?pin='+encodeURIComponent(pin)+'&lat='+lat+'&lng='+lng).then(function(m){btn.disabled=false;
      if(m&&m.known&&!m.match){mismatchPin=pin;$('mismatchtxt').textContent=' '+T.mismatch.replace('%(pin)s',pin)
        .replace('%(place)s',m.place?fmt(T.isIn,m.place):'').replace('%(km)s',m.km);$('mismatch').style.display='';
        btn.textContent=T.saveAnyway;return;}go();}).catch(go);return;}
  go();});
$('f_pin').addEventListener('input',function(){if(mismatchPin!==this.value){$('mismatch').style.display='none';$('save').textContent=T.save;}});
/* Pick on map: the pin stays in the middle and the map moves under it */
var map=null,pending=null;
function note(t){$('mapnote').textContent=t||''}
function goTo(c,z){if(map){map.flyTo({center:c,zoom:z})}else{pending=[c,z]}}
/* the browser asks "Allow location?"; no answer or no: turn it on, or type */
function locate(){if(!navigator.geolocation){note(T.locOff);return}
  note(T.asking);
  navigator.geolocation.getCurrentPosition(function(p){goTo([p.coords.longitude,p.coords.latitude],17);note(T.hereNow)},
    function(){note(T.locOff)},{enableHighAccuracy:true,timeout:15000,maximumAge:0});}
function search(){var q=$('placeq').value.trim(),box=$('places');box.innerHTML='';if(q.length<3)return;
  note(T.searching);
  get('/search?q='+encodeURIComponent(q)+'&country='+encodeURIComponent($('f_country').value)).then(function(r){
    if(!r||!r.ok){note(T.searchFail);return}
    if(!r.places.length){note(T.noPlace);return}
    note('');r.places.forEach(function(p){var b=document.createElement('button');b.type='button';b.textContent=p.name;
      b.onclick=function(){box.innerHTML='';goTo([p.lng,p.lat],17);note('')};box.appendChild(b)});
    if(r.places.length===1){box.innerHTML='';goTo([r.places[0].lng,r.places[0].lat],17)}
  }).catch(function(){note(T.searchFail)});}
$('placego').addEventListener('click',search);
$('placeq').addEventListener('keydown',function(e){if(e.key==='Enter'){e.preventDefault();search()}});
function load(cb){if(window.maplibregl)return cb();var l=document.createElement('link');l.rel='stylesheet';l.href=C.lib+'.css';
  document.head.appendChild(l);var s=document.createElement('script');s.src=C.lib+'.js';s.onload=cb;document.head.appendChild(s);}
function open(){$('spotrow').style.display='none';$('picker').classList.add('on');
  var lat=parseFloat($('f_lat').value),lng=parseFloat($('f_lng').value);
  var start=function(center,zoom){load(function(){if(map){map.jumpTo({center:center,zoom:zoom});map.resize();return;}
    map=new maplibregl.Map({container:'map',style:C.style,center:center,zoom:zoom,maxZoom:19,dragRotate:false,touchPitch:false});
    map.addControl(new maplibregl.NavigationControl({showCompass:false}));
    if(pending){map.jumpTo({center:pending[0],zoom:pending[1]});pending=null}});};
  note('');$('places').innerHTML='';
  if(!isNaN(lat)&&!isNaN(lng))return start([lng,lat],15);
  /* no pin yet: ask for the location straight away (the pincode's area
     meanwhile), and the search box is there when it is off */
  locate();
  var pin=$('f_pin').value;
  if(pin)get('/spot?pin='+encodeURIComponent(pin)).then(function(s){if(s&&s.known){
      start([s.lng,s.lat],13);}else start([78.9629,22.5937],4);})
    .catch(function(){start([78.9629,22.5937],4)});
  else start([78.9629,22.5937],4);}
function closeP(){$('picker').classList.remove('on');$('spotrow').style.display='';}
$('pickmap').addEventListener('click',open);$('mapcancel').addEventListener('click',closeP);
$('here').addEventListener('click',locate);
$('mapuse').addEventListener('click',function(){if(!map)return;var c=map.getCenter();
  $('f_lat').value=c.lat.toFixed(6);$('f_lng').value=c.lng.toFixed(6);mismatchPin=null;$('mismatch').style.display='none';
  $('save').textContent=T.save;$('spottitle').textContent=T.set;$('spotsub').textContent=T.setSub;
  $('spotic').classList.add('on');$('pickmap').textContent=T.change;closeP();});
})();
"""
