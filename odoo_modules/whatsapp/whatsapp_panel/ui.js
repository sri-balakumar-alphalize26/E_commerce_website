'use strict';

/**
 * The look and the movement of every panel page: one stylesheet, one script.
 * No build step, no CDN. Every form still works with the script switched off;
 * the script only adds the pop-up, the spinner, the toast and the smooth tabs.
 *
 * No backslash and no backtick inside the two strings below.
 */

const CSS = `
:root{--bg:#0b0f12;--bg2:#0f1519;--card:#141b20;--card2:#192229;--line:#25313a;--line2:#34434e;--fg:#e8eef0;--muted:#8fa0aa;
--accent:#25d366;--accent2:#12b886;--bad:#ff7676;--warn:#f5b455;--radius:14px;--field:#0e1418;
--ease:cubic-bezier(.2,.8,.2,1);--shadow:0 1px 0 rgba(255,255,255,.03) inset,0 10px 30px -18px rgba(0,0,0,.9);color-scheme:dark}
*{box-sizing:border-box}
[hidden]{display:none!important}
html{scroll-behavior:smooth;scroll-padding-top:84px;interpolate-size:allow-keywords}
body{margin:0;min-height:100vh;color:var(--fg);font:15px/1.55 system-ui,Segoe UI,sans-serif;
background:radial-gradient(900px 420px at 85% -120px,rgba(37,211,102,.10),transparent 70%),radial-gradient(700px 380px at 0 0,rgba(18,184,134,.07),transparent 70%),var(--bg);background-attachment:fixed}
a{color:var(--accent);text-decoration:none;transition:color .15s}
a:hover{color:#6ff0a0}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
::selection{background:rgba(37,211,102,.35)}

header{position:sticky;top:0;z-index:20;display:flex;gap:16px;align-items:center;padding:11px 22px;flex-wrap:wrap;
background:rgba(15,21,25,.82);backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);border-bottom:1px solid var(--line)}
header .brand{display:flex;align-items:center;gap:10px;font-weight:700;letter-spacing:.2px;color:var(--fg)}
header .brand svg{width:28px;height:28px}
header .who{font-size:12px;color:var(--muted);border:1px solid var(--line);border-radius:999px;padding:2px 10px}
header nav{display:flex;gap:4px;margin-left:auto;align-items:center;flex-wrap:wrap}
header nav a{position:relative;padding:7px 12px;border-radius:9px;color:var(--muted);font-weight:550;transition:background .18s,color .18s}
header nav a:hover{color:var(--fg);background:var(--card2)}
header nav a[aria-current]{color:var(--fg);background:rgba(37,211,102,.13)}
header nav form{margin-left:8px!important}
main{max-width:1080px;margin:28px auto 60px;padding:0 18px}

h1{font-size:24px;line-height:1.25;letter-spacing:-.2px;margin:0 0 14px;text-wrap:balance}
h2{font-size:13px;margin:22px 0 10px;color:var(--muted);text-transform:uppercase;letter-spacing:.8px}
.card h2:first-child{margin-top:0}
h3{font-size:14px;margin:16px 0 8px}
.card{background:linear-gradient(180deg,var(--card2),var(--card) 90px);border:1px solid var(--line);border-radius:var(--radius);padding:20px;margin-bottom:18px;box-shadow:var(--shadow);transition:border-color .2s}
.card:hover{border-color:var(--line2)}
.card>p:first-child{margin-top:0}
.card>form+.btn{margin-top:10px}
.card.narrow{max-width:580px}
.card.danger{border-color:#4a262e;background:linear-gradient(180deg,#1d1619,var(--card) 90px)}
.card.warn{border-color:#5a4520}
label{display:block;margin:12px 0}
label .muted{display:block;font-size:12px;margin-top:4px}
input,select{width:100%;padding:10px 12px;border-radius:10px;border:1px solid var(--line);background:var(--field);color:var(--fg);font:inherit;font-size:14px;transition:border-color .18s,box-shadow .18s,background .18s}
input:hover,select:hover{border-color:var(--line2)}
input:focus,select:focus{outline:none;border-color:var(--accent);box-shadow:0 0 0 3px rgba(37,211,102,.16)}
input[readonly]{opacity:.7}
input[type=checkbox],input[type=radio]{accent-color:var(--accent);width:17px;height:17px;padding:0;flex:none}
label.check{display:flex;align-items:center;gap:9px;cursor:pointer}
label.check input{width:17px}

button,.btn{position:relative;display:inline-flex;align-items:center;justify-content:center;gap:7px;padding:8px 14px;border-radius:10px;border:1px solid var(--line);background:#1b242b;color:var(--fg);font:inherit;font-size:14px;font-weight:550;line-height:1.35;cursor:pointer;white-space:nowrap;
transition:transform .16s var(--ease),background .18s,border-color .18s,box-shadow .2s,opacity .18s,color .18s}
button:hover,.btn:hover{background:#222e36;border-color:var(--line2);color:var(--fg)}
button:active,.btn:active{transform:scale(.96)}
button.primary,.btn.primary{background:linear-gradient(180deg,#34e27a,var(--accent));border-color:transparent;color:#04210e;font-weight:650;box-shadow:0 6px 18px -10px rgba(37,211,102,.9)}
button.primary:hover,.btn.primary:hover{color:#04210e;background:linear-gradient(180deg,#4bee8d,#2bdc6e);box-shadow:0 8px 24px -8px rgba(37,211,102,.75)}
button.bad-btn{background:#33191f;border-color:#5c2b34;color:#ffb9b9}
button.bad-btn:hover{background:#45212a;border-color:#7d3a46;color:#ffd0d0}
button.busy{color:transparent!important;pointer-events:none}
button.busy::after{content:"";position:absolute;inset:0;margin:auto;width:16px;height:16px;border-radius:50%;border:2px solid rgba(255,255,255,.25);border-top-color:#fff;animation:spin .7s linear infinite}
button.primary.busy::after{border-color:rgba(4,33,14,.25);border-top-color:#04210e}
button.done{background:rgba(37,211,102,.16);border-color:rgba(37,211,102,.5);color:#7cf0a8;animation:pop .35s var(--ease)}

table{width:100%;border-collapse:separate;border-spacing:0;background:var(--card);border:1px solid var(--line);border-radius:var(--radius);overflow:hidden;margin-bottom:18px}
table.plain{background:none;border:none;border-radius:0}
th,td{text-align:left;padding:11px 13px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;font-weight:600}
table:not(.plain) th{background:rgba(255,255,255,.02)}
tr:last-child td,tr:last-child th{border-bottom:none}
table:not(.plain) tr:first-child th{border-bottom:1px solid var(--line)}
table:not(.plain) tr{transition:background .15s}
table:not(.plain) tr:hover td{background:rgba(37,211,102,.045)}
tr.off{opacity:.5}
.card.off{opacity:.65}
td.right,th.right,.right{text-align:right}
td.num{font-variant-numeric:tabular-nums}
code{background:var(--field);padding:2px 7px;border-radius:6px;font-size:13px;border:1px solid var(--line);word-break:break-all}
code.tok{display:block;padding:9px;margin-top:4px}
.muted{color:var(--muted)}
.bad{color:var(--bad)}
.warn-msg{color:var(--warn)}
.ok-msg{color:var(--accent)}
.pill{display:inline-flex;align-items:center;gap:6px;padding:2px 10px;border-radius:999px;font-size:12px;font-weight:600;white-space:nowrap}
.pill.ok{background:#10301f;color:#62e595}
.pill.no{background:#37222a;color:#ff9a9a}
.pill.warn{background:#3a2f16;color:#f5b455}
.pill.dim{background:#212b32;color:#93a3ad}
.num-row .pill::before,.card .pill.live::before{content:"";width:7px;height:7px;border-radius:50%;background:currentColor}
.num-row .pill.ok::before{animation:live 2s infinite}
.num-row .pill.warn::before{animation:blink 1.1s infinite}
.row{display:flex;align-items:center;gap:10px}
.row.between{justify-content:space-between;flex-wrap:wrap}
.num-row .row{flex-wrap:wrap}
.row.gap{gap:10px;margin:12px 0}
.row.gap input{flex:1}
.big{font-size:20px;font-weight:700;letter-spacing:.4px;font-variant-numeric:tabular-nums}
.checks label{margin:6px 0}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin:16px 0}
.tile{background:linear-gradient(180deg,var(--card2),var(--card));border:1px solid var(--line);border-radius:var(--radius);padding:16px 18px;box-shadow:var(--shadow);transition:transform .22s var(--ease),border-color .2s}
.tile:hover{transform:translateY(-2px);border-color:var(--line2)}
.tile b{display:block;font-size:26px;line-height:1.2;font-variant-numeric:tabular-nums}.tile span{color:var(--muted);font-size:13px}
.tabs{position:relative;display:flex;gap:2px;border-bottom:1px solid var(--line);margin:20px 0 18px;overflow-x:auto;scrollbar-width:none}
.tabs a{padding:11px 15px;color:var(--muted);font-weight:600;white-space:nowrap;border-bottom:3px solid transparent;transition:color .18s}
.tabs a:hover{color:var(--fg)}
.tabs a.on{color:var(--fg);border-bottom-color:var(--accent)}
.tabs.slide a.on{border-bottom-color:transparent}
.tabs .ink{position:absolute;bottom:0;left:0;height:3px;border-radius:3px 3px 0 0;background:var(--accent);transition:transform .32s var(--ease),width .32s var(--ease)}
section.tab[hidden]{display:none}
section.tab .card.narrow{max-width:640px}

.num-row{border:1px solid var(--line);border-radius:12px;padding:15px;margin:12px 0;background:rgba(255,255,255,.012);transition:border-color .2s,background .2s,opacity .25s}
.num-row:hover{border-color:var(--line2);background:rgba(255,255,255,.025)}
.num-row.is-off{opacity:.65;border-style:dashed}
.num-row:target{border-color:var(--accent);animation:ring 1.6s ease-out}
.num-free{display:flex;align-items:center;justify-content:space-between;gap:12px;border:1px solid var(--line);border-radius:12px;padding:12px 14px;margin:8px 0;transition:border-color .2s}
.num-free:hover{border-color:var(--accent)}
.num-no{display:inline-block;min-width:26px;height:26px;line-height:26px;text-align:center;border-radius:999px;background:#212b32;color:var(--muted);font-weight:700;font-size:13px;margin-right:8px}
.key-line{display:flex;align-items:center;gap:10px;margin-top:12px}
.key-line code{flex:1;min-width:0;max-height:3.4em;overflow:auto;transition:border-color .2s,box-shadow .2s}
.key-line.copied code{border-color:var(--accent);box-shadow:0 0 0 3px rgba(37,211,102,.14)}
details summary{cursor:pointer;color:var(--muted);margin-top:10px;transition:color .15s}
details summary:hover{color:var(--fg)}
details summary.btn.primary{display:inline-flex;color:#04210e;list-style:none}
details summary.btn.primary::-webkit-details-marker{display:none}
details::details-content{height:0;opacity:0;overflow:clip;transition:height .3s var(--ease),opacity .25s,content-visibility .3s allow-discrete}
details[open]::details-content{height:auto;opacity:1}
details.num-add{margin:16px 0}
.odoo-steps ol{margin:10px 0 4px;padding-left:22px}
.odoo-steps li{margin:6px 0;padding-left:4px}
.odoo-steps li::marker{color:var(--accent);font-weight:700}
.odoo-steps b{color:var(--fg)}
.own-max{display:flex;align-items:center;gap:10px;flex-wrap:wrap;border-top:1px solid var(--line);padding-top:12px}
.own-max label{display:flex;align-items:center;gap:10px;margin:0}
.own-max input{width:90px}
.own-max select{width:auto;min-width:200px}

.phone{margin:12px 0}
.ph-box{display:flex;align-items:stretch;border:1px solid var(--line);border-radius:10px;overflow:hidden;background:var(--field);transition:border-color .18s,box-shadow .18s}
.ph-box:focus-within{border-color:var(--accent);box-shadow:0 0 0 3px rgba(37,211,102,.16)}
.phone.good .ph-box{border-color:var(--accent)}
.ph-box .ph-dial{display:flex;align-items:center;padding:0 12px;background:#1b242b;font-weight:700}
.ph-box input.ph-num{flex:1;min-width:0;border:0;border-radius:0;font-size:17px;font-weight:600;letter-spacing:.5px;box-shadow:none}
.ph-box .ph-count{display:flex;align-items:center;padding:0 12px;color:var(--muted);font-size:12px}
.phone.good .ph-hint{color:var(--accent)}

.qr{display:block;width:280px;max-width:100%;margin:0 auto;padding:10px;background:#fff;color:#333;border-radius:14px}
.qr-box{position:relative;width:280px;max-width:100%;margin:18px auto;border-radius:14px;overflow:hidden;box-shadow:0 0 0 1px var(--line),0 18px 50px -22px rgba(37,211,102,.6)}
.qr-box::after{content:"";position:absolute;left:0;right:0;top:0;height:34%;pointer-events:none;background:linear-gradient(180deg,transparent,rgba(37,211,102,.28));border-bottom:2px solid rgba(18,160,80,.85);animation:scan 2.8s ease-in-out infinite}
.qr-time{height:3px;max-width:280px;margin:0 auto 12px;border-radius:3px;background:var(--line);overflow:hidden}
.qr-time i{display:block;height:100%;background:var(--accent);transform-origin:left;animation:drain 12s linear forwards}

/* sign in */
body.auth{display:grid;place-items:center;overflow-x:hidden}
body.auth main{width:100%;max-width:980px;margin:0 auto;padding:28px 18px}
.auth-wrap{display:grid;grid-template-columns:1.05fr 1fr;gap:56px;align-items:center}
.auth-side h1{font-size:34px;letter-spacing:-.8px;margin:18px 0 8px}
.auth-side p{color:var(--muted);margin:0 0 26px;max-width:38ch}
.auth-logo{position:relative;width:74px;height:74px}
.auth-logo svg{position:relative;width:74px;height:74px;animation:float 5s ease-in-out infinite}
.auth-logo i{position:absolute;inset:6px;border-radius:24px;border:2px solid rgba(37,211,102,.5);animation:wave 2.8s ease-out infinite}
.auth-logo i+i{animation-delay:1.4s}
.bubbles{display:grid;gap:10px;justify-items:start}
.bubbles>span{padding:10px 15px;border-radius:16px 16px 16px 5px;background:var(--card2);border:1px solid var(--line);font-size:14px;animation:bubble .6s var(--ease) both}
.bubbles>span:nth-child(1){animation-delay:.35s}
.bubbles>span:nth-child(2){animation-delay:.8s;margin-left:34px;border-radius:16px 16px 5px 16px;background:#0f3d28;border-color:#17563a}
.bubbles>span:nth-child(3){animation-delay:1.25s}
.bubbles .dots{display:inline-flex;gap:5px}
.bubbles .dots i{width:7px;height:7px;border-radius:50%;background:var(--muted);animation:dot 1.2s infinite}
.bubbles .dots i:nth-child(2){animation-delay:.16s}.bubbles .dots i:nth-child(3){animation-delay:.32s}
.auth-card.card{padding:30px;max-width:none;margin:0;border-radius:20px;animation:rise .55s var(--ease) both}
.auth-card h2{font-size:22px;color:var(--fg);text-transform:none;letter-spacing:-.2px;margin:0 0 4px}
.auth-card .field{margin:16px 0}
.auth-card .field label{margin:0 0 6px;font-weight:600;font-size:13px}
.auth-card .in{position:relative}
.auth-card .in svg{position:absolute;left:13px;top:50%;width:18px;height:18px;margin-top:-9px;color:var(--muted);pointer-events:none;transition:color .18s}
.auth-card .in:focus-within svg{color:var(--accent)}
.auth-card .in input{padding:12px 14px 12px 41px;font-size:15px}
.auth-card .in input[name=password]{padding-right:48px}
.pw{position:relative;display:block}
.row.gap .pw{flex:1}
.pw input{padding-right:46px}
.eye{position:absolute;right:5px;top:50%;transform:translateY(-50%);width:36px;height:34px;padding:0;background:none;border-color:transparent;color:var(--muted)}
.eye:active{transform:translateY(-50%) scale(.95)}
.eye svg,.auth-card .in .eye svg{position:static;width:19px;height:19px;margin:0;color:inherit}
.eye .slash{display:none}
.eye[aria-pressed=true] .slash{display:inline}
input[type=password]::-ms-reveal{display:none}
.auth-card .hint{display:block;font-size:12px;color:var(--muted);margin-top:5px}
.auth-card .caps{color:var(--warn)}
.auth-card button.primary{width:100%;padding:12px;font-size:15px;margin-top:8px}
.auth-card .wrong{background:#33191f;border:1px solid #5c2b34;color:#ffc0c0;border-radius:10px;padding:9px 13px;margin:14px 0 0}
.auth-card.shake{animation:shake .5s .1s both}

/* toast, pop-up, loading line, connected */
#wap-bar{position:fixed;left:0;top:0;height:3px;width:100%;z-index:60;background:linear-gradient(90deg,var(--accent2),var(--accent));transform:scaleX(0);transform-origin:left;opacity:0;pointer-events:none}
#wap-bar.go{opacity:1;transform:scaleX(.88);transition:transform 9s cubic-bezier(.05,.75,.1,1)}
#wap-toasts{position:fixed;right:18px;bottom:18px;z-index:70;display:grid;gap:10px;max-width:min(400px,calc(100vw - 36px))}
.toast{display:flex;gap:11px;align-items:flex-start;padding:13px 16px;border-radius:13px;background:#1c272e;border:1px solid var(--line2);box-shadow:0 18px 50px -18px #000;animation:toast .35s var(--ease) both}
.toast.out{animation:toastout .25s ease-in both}
.toast svg{width:20px;height:20px;flex:none;margin-top:1px;color:var(--accent)}
.toast.err{border-color:#6b313b}.toast.err svg{color:var(--bad)}
dialog.ask{width:min(440px,calc(100vw - 32px));padding:24px;border:1px solid var(--line2);border-radius:18px;background:#171f25;color:var(--fg);box-shadow:0 30px 90px -20px #000}
dialog.ask[open]{animation:pop .26s var(--ease) both}
dialog.ask::backdrop{background:rgba(4,8,10,.66);backdrop-filter:blur(3px);animation:fade .2s both}
dialog.ask p{margin:0 0 20px;font-size:15px}
dialog.ask .row{justify-content:flex-end;flex-wrap:wrap}
.linked{position:fixed;inset:0;z-index:80;display:grid;place-content:center;justify-items:center;gap:14px;background:rgba(6,12,10,.9);animation:fade .25s both;font-size:20px;font-weight:700}
.linked svg{width:110px;height:110px}
.linked circle{fill:none;stroke:var(--accent);stroke-width:5;stroke-dasharray:290;stroke-dashoffset:290;animation:draw .6s ease-out forwards}
.linked path{fill:none;stroke:var(--accent);stroke-width:7;stroke-linecap:round;stroke-linejoin:round;stroke-dasharray:90;stroke-dashoffset:90;animation:draw .4s .5s ease-out forwards}

.js main>*{animation:rise .42s var(--ease) both}
.js main>*:nth-child(2){animation-delay:.04s}.js main>*:nth-child(3){animation-delay:.08s}
.js main>*:nth-child(4){animation-delay:.12s}.js main>*:nth-child(5){animation-delay:.16s}.js main>*:nth-child(n+6){animation-delay:.2s}
.js section.tab:not([hidden])>*{animation:rise .34s var(--ease) both}
.js body.auth main>*{animation:none}
@keyframes rise{from{opacity:0;transform:translateY(10px)}}
@keyframes fade{from{opacity:0}}
@keyframes pop{from{opacity:0;transform:scale(.93)}}
@keyframes spin{to{transform:rotate(1turn)}}
@keyframes live{0%{box-shadow:0 0 0 0 rgba(98,229,149,.55)}70%,100%{box-shadow:0 0 0 7px rgba(98,229,149,0)}}
@keyframes blink{50%{opacity:.25}}
@keyframes ring{0%{box-shadow:0 0 0 0 rgba(37,211,102,.5)}100%{box-shadow:0 0 0 14px rgba(37,211,102,0)}}
@keyframes scan{0%{transform:translateY(-100%)}100%{transform:translateY(300%)}}
@keyframes drain{to{transform:scaleX(0)}}
@keyframes float{50%{transform:translateY(-6px)}}
@keyframes wave{from{transform:scale(.9);opacity:.9}to{transform:scale(1.65);opacity:0}}
@keyframes bubble{from{opacity:0;transform:translateY(14px) scale(.94)}}
@keyframes dot{0%,60%,100%{transform:none;opacity:.5}30%{transform:translateY(-4px);opacity:1}}
@keyframes shake{20%,60%{transform:translateX(-8px)}40%,80%{transform:translateX(8px)}}
@keyframes toast{from{opacity:0;transform:translateY(16px) scale(.96)}}
@keyframes toastout{to{opacity:0;transform:translateX(30px)}}
@keyframes draw{to{stroke-dashoffset:0}}
@media (max-width:820px){.auth-wrap{grid-template-columns:1fr;gap:24px}.auth-side{display:grid;justify-items:center;text-align:center}.auth-side .bubbles{display:none}.auth-side h1{font-size:26px}.auth-side p{margin:0}}
@media (max-width:720px){main table:not(.plain){display:block;overflow-x:auto}}
@media (max-width:620px){.key-line{flex-wrap:wrap}.key-line code{flex-basis:100%}header{position:static;padding:11px 14px}header nav{width:100%;margin-left:0}main{padding:0 14px;margin-top:20px}.card{padding:16px}}
@media (prefers-reduced-motion:reduce){*,*::before,*::after,::backdrop{animation-duration:.01ms!important;animation-delay:0s!important;animation-iteration-count:1!important;transition-duration:.01ms!important;scroll-behavior:auto!important}.qr-box::after{display:none}}
`;

const LOGO = '<svg viewBox="0 0 48 48" aria-hidden="true"><rect width="48" height="48" rx="15" fill="#25d366"/><path d="M13 14h22a4 4 0 0 1 4 4v11a4 4 0 0 1-4 4H23l-8 6v-6h-2a4 4 0 0 1-4-4V18a4 4 0 0 1 4-4z" fill="#fff"/><g fill="#12a150"><circle cx="17.5" cy="23.5" r="2.3"/><circle cx="24" cy="23.5" r="2.3"/><circle cx="30.5" cy="23.5" r="2.3"/></g></svg>';

const SCRIPT = `<script>
(function () {
  var doc = document, body = doc.body;
  function el(tag, cls, text) { var e = doc.createElement(tag); if (cls) { e.className = cls; } if (text) { e.textContent = text; } return e; }
  var TICK = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M8 12.5l2.7 2.7L16 9.5"/></svg>';
  var WARN = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 7.5v5.5M12 16.4v.1"/></svg>';

  // ---- toast
  var holder = el('div'); holder.id = 'wap-toasts'; holder.setAttribute('role', 'status'); holder.setAttribute('aria-live', 'polite'); body.appendChild(holder);
  window.wapToast = function (text, bad) {
    var t = el('div', 'toast' + (bad ? ' err' : ''));
    t.innerHTML = bad ? WARN : TICK;
    t.appendChild(el('div', '', text));
    holder.appendChild(t);
    setTimeout(function () { t.classList.add('out'); setTimeout(function () { t.remove(); }, 300); }, bad ? 7000 : 3600);
  };
  // the message a page came back with: "Saved." goes by as a toast, an error also stays on the page
  var q = new URLSearchParams(location.search);
  ['ok', 'bad'].forEach(function (k) {
    if (!q.has(k) || body.classList.contains('auth')) { return; }
    var found = null;
    doc.querySelectorAll(k === 'ok' ? 'main p.ok-msg' : 'main p.bad').forEach(function (p) { if (!found && (p.textContent.trim() === q.get(k).trim() || q.get(k) === '1')) { found = p; } });
    if (found) { window.wapToast(found.textContent.trim(), k === 'bad'); if (k === 'ok') { found.remove(); } }
  });
  if ((q.has('ok') || q.has('bad')) && !body.classList.contains('auth')) {
    q.delete('ok'); q.delete('bad');
    var rest = q.toString();
    history.replaceState(null, '', location.pathname + (rest ? '?' + rest : '') + location.hash);
  }

  // ---- loading line
  var bar = el('div'); bar.id = 'wap-bar'; body.appendChild(bar);
  function loading() { bar.classList.add('go'); }
  doc.addEventListener('click', function (e) {
    var a = e.target.closest && e.target.closest('a[href]');
    if (!a || e.defaultPrevented || e.button || e.ctrlKey || e.metaKey || e.shiftKey || a.target || a.origin !== location.origin) { return; }
    if (a.pathname === location.pathname && a.search === location.search && a.hash) { return; }
    loading();
  });

  // ---- "are you sure": the browser's own box when <dialog> is missing
  var canAsk = typeof HTMLDialogElement === 'function' && HTMLDialogElement.prototype.showModal && HTMLFormElement.prototype.requestSubmit;
  function ask(text, yes, danger) {
    return new Promise(function (done) {
      var d = el('dialog', 'ask'), p = el('p', '', text), row = el('div', 'row'), no = el('button', '', 'Cancel'), go = el('button', danger ? 'bad-btn' : 'primary', yes);
      p.id = 'wap-ask'; d.setAttribute('aria-labelledby', 'wap-ask'); no.type = go.type = 'button';
      row.appendChild(no); row.appendChild(go); d.appendChild(p); d.appendChild(row); body.appendChild(d);
      var answer = false;
      no.onclick = function () { d.close(); };
      go.onclick = function () { answer = true; d.close(); };
      d.addEventListener('click', function (e) { if (e.target === d) { var r = d.getBoundingClientRect(); if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) { d.close(); } } });
      d.addEventListener('close', function () { d.remove(); done(answer); });
      d.showModal(); no.focus();
    });
  }
  if (canAsk) {
    var head = "return confirm('", tail = "')";
    doc.querySelectorAll('form[onsubmit]').forEach(function (f) {
      var code = f.getAttribute('onsubmit').trim();
      if (code.indexOf(head) !== 0 || code.slice(-tail.length) !== tail) { return; }
      f.dataset.ask = code.slice(head.length, -tail.length);
      f.removeAttribute('onsubmit');
    });
    doc.addEventListener('submit', function (e) {
      var f = e.target, by = e.submitter || null;
      if (!f.dataset.ask || f.wapSure) { return; }
      e.preventDefault(); e.stopImmediatePropagation();
      ask(f.dataset.ask, by && by.textContent.trim() || 'Yes', !by || !by.classList.contains('primary')).then(function (yes) {
        if (!yes) { return; }
        f.wapSure = true; f.requestSubmit(by); f.wapSure = false;
      });
    }, true);
  }

  // ---- a pressed button shows it is working, and is not sent twice
  doc.addEventListener('submit', function (e) {
    var f = e.target;
    if (e.defaultPrevented) { return; }
    if (f.wapBusy) { e.preventDefault(); return; }
    f.wapBusy = true; loading();
    var b = e.submitter || f.querySelector('button:not([type=button])');
    if (b) { b.classList.add('busy'); }
    setTimeout(function () { f.wapBusy = false; if (b) { b.classList.remove('busy'); } bar.classList.remove('go'); }, 30000);
  });
  window.addEventListener('pageshow', function (e) {
    if (!e.persisted) { return; }
    bar.classList.remove('go');
    doc.querySelectorAll('.busy').forEach(function (b) { b.classList.remove('busy'); });
    doc.querySelectorAll('form').forEach(function (f) { f.wapBusy = false; });
  });

  // ---- where we are in the menu
  var here = location.pathname, best = null;
  doc.querySelectorAll('header nav a').forEach(function (a) {
    var p = a.pathname;
    var mine = here === p || (p === '/' && /^[/](database|server)/.test(here)) || (p === '/numbers' && here.indexOf('/number') === 0) || (p === '/companies' && here.indexOf('/compan') === 0);
    if (mine && !best) { best = a; a.setAttribute('aria-current', 'page'); }
  });

  // ---- the line under the open tab slides
  var tabs = doc.querySelector('.tabs');
  if (tabs) {
    var ink = el('i', 'ink'); tabs.appendChild(ink); tabs.classList.add('slide');
    var slide = function () { var on = tabs.querySelector('a.on'); if (on) { ink.style.width = on.offsetWidth + 'px'; ink.style.transform = 'translateX(' + on.offsetLeft + 'px)'; } };
    new MutationObserver(slide).observe(tabs, { subtree: true, attributes: true, attributeFilter: ['class'] });
    window.addEventListener('resize', slide); slide();
  }

  // ---- whole numbers in the tiles count up
  if (!matchMedia('(prefers-reduced-motion: reduce)').matches) {
    doc.querySelectorAll('.tile b').forEach(function (b) {
      var to = b.textContent.trim();
      if (!/^[0-9]+$/.test(to) || +to < 2) { return; }
      var t0 = performance.now();
      (function step(t) { var k = Math.min(1, Math.max(0, (t - t0) / 650)); b.textContent = k < 1 ? Math.round(+to * (1 - Math.pow(1 - k, 3))) : to; if (k < 1) { requestAnimationFrame(step); } })(t0);
    });
  }

  // ---- every password: an eye to show and hide it
  doc.querySelectorAll('input[type=password]').forEach(function (f) {
    var box = f.closest('.in'), b = el('button', 'eye');
    if (!box) { box = el('span', 'pw'); f.parentNode.insertBefore(box, f); box.appendChild(f); }
    b.type = 'button';
    b.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7-10-7-10-7z"/><circle cx="12" cy="12" r="3"/><path class="slash" d="M4 4l16 16"/></svg>';
    function set(shown) {
      f.type = shown ? 'text' : 'password';
      b.title = shown ? 'Hide password' : 'Show password';
      b.setAttribute('aria-label', 'Show password');
      b.setAttribute('aria-pressed', String(shown));
    }
    b.addEventListener('click', function (e) { e.preventDefault(); set(f.type === 'password'); f.focus(); });
    if (f.form) { f.form.addEventListener('submit', function () { set(false); }); }
    set(false);
    box.appendChild(b);
  });

  // ---- sign in: caps lock
  var pw = doc.querySelector('.auth-card input[name=password]');
  if (pw) {
    var caps = doc.querySelector('.caps');
    ['keydown', 'keyup'].forEach(function (n) { pw.addEventListener(n, function (e) { caps.hidden = !(e.getModifierState && e.getModifierState('CapsLock')); }); });
  }

  // ---- QR page: the code renews itself without the whole page blinking
  var live = doc.getElementById('qr-live');
  if (live) {
    var again = function () {
      if (doc.hidden) { setTimeout(again, 3000); return; }
      fetch(location.pathname, { credentials: 'same-origin' }).then(function (r) {
        if (r.redirected || !r.ok) { throw new Error('reload'); }
        return r.text();
      }).then(function (html) {
        var fresh = new DOMParser().parseFromString(html, 'text/html');
        var next = fresh.getElementById('qr-live');
        if (!next) {
          if (!fresh.getElementById('qr-open')) { location.reload(); return; }
          var ok = el('div', 'linked');
          ok.innerHTML = '<svg viewBox="0 0 100 100" aria-hidden="true"><circle cx="50" cy="50" r="44"/><path d="M30 52l14 14 27-30"/></svg>';
          ok.appendChild(el('div', '', 'Connected')); ok.setAttribute('role', 'status');
          body.appendChild(ok);
          setTimeout(function () { location.reload(); }, 1500);
          return;
        }
        live.innerHTML = next.innerHTML;
        setTimeout(again, 12000);
      }).catch(function () { setTimeout(function () { location.reload(); }, 4000); });
    };
    setTimeout(again, 12000);
  }
})();
</script>`;

module.exports = { CSS, LOGO, SCRIPT };
