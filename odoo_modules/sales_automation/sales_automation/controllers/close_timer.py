# -*- coding: utf-8 -*-
"""The page is finished: it counts ten seconds and closes its tab (owner, 24 Nov
2026). A browser closes only a tab that was opened for this page; where it
refuses, the words say what to do. A touch, a key or the wheel stops it, so
nobody loses a page they are reading."""

SECONDS = 10

CLOSE_TIMER = """<div id="bye" style="display:flex;flex-direction:column;align-items:center;gap:8px;margin:18px 0 0;text-align:center">
<svg id="byering" width="84" height="84" viewBox="0 0 84 84" role="img" aria-label="This page closes in 10 seconds">
<circle cx="42" cy="42" r="36" fill="none" stroke="#d7e6dc" stroke-width="6"/>
<circle id="byearc" cx="42" cy="42" r="36" fill="none" stroke="#1a7f3c" stroke-width="6" stroke-linecap="round"
 stroke-dasharray="226.2" stroke-dashoffset="0" transform="rotate(-90 42 42)"/>
<text id="byen" x="42" y="52" text-anchor="middle" font-size="28" font-weight="800" fill="#1a7f3c">10</text></svg>
<div id="byet" style="font-size:14px;color:#52616d">This page closes by itself</div>
<button type="button" id="byestay" style="border:1px solid #cfd8df;background:#fff;color:#13212b;border-radius:999px;padding:9px 18px;font:inherit;font-size:14px;font-weight:600;cursor:pointer">Stay on this page</button></div>
<script>(function(){var ALL=10000,end=Date.now()+ALL,g=function(i){return document.getElementById(i)},iv=setInterval(tick,100);
function stop(){clearInterval(iv);var b=g('bye');if(b)b.style.display='none';
['pointerdown','keydown','wheel','touchmove'].forEach(function(e){document.removeEventListener(e,stop)})}
['pointerdown','keydown','wheel','touchmove'].forEach(function(e){document.addEventListener(e,stop,{passive:true})});
function tick(){var left=Math.max(0,end-Date.now());g('byen').textContent=Math.ceil(left/1000);
g('byearc').setAttribute('stroke-dashoffset',String(226.2*(1-left/ALL)));
if(left>0)return;clearInterval(iv);window.close();
setTimeout(function(){g('byering').style.display='none';g('byestay').style.display='none';g('byet').textContent='You can close this page now.'},400)}
tick()})();</script>"""
