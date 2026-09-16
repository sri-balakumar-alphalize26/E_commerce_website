/** @odoo-module ignore */
/* ==========================================================================
   369 Mart — home page motion engine (vanilla, no dependencies, ~6 KB)
   Works in Next.js/React and in Odoo website templates alike.

   1. Mark your markup with data-mm="role" (see README), OR point MAP below
      at your existing class names — a selector that matches nothing is
      skipped silently.
   2. Load mart-motion.css + this file. It boots itself on DOMContentLoaded;
      call MartMotion.refresh() after client-side navigation.
   ========================================================================== */
(function () {
  "use strict";
  if (window.MartMotion) return;

  /* role -> selector. Edit the right-hand side to match your markup. */
  var MAP = {
    header:       '[data-mm="header"]',
    logo:         '[data-mm="logo"]',
    search:       '[data-mm="search"]',
    cart:         '[data-mm="cart"]',
    "cart-count": '[data-mm="cart-count"]',
    pills:        '[data-mm="pills"]',
    hero:         '[data-mm="hero"]',
    "hero-text":  '[data-mm="hero-text"]',
    "hero-cta":   '[data-mm="hero-cta"]',
    "hero-dots":  '[data-mm="hero-dots"]',
    cats:         '[data-mm="cats"]',
    "cat-icon":   '[data-mm="cat-icon"]',
    "sec-head":   '[data-mm="sec-head"]',
    "see-all":    '[data-mm="see-all"]',
    rail:         '[data-mm="rail"]',
    card:         '[data-mm="card"]',
    "card-img":   '[data-mm="card-img"]',
    badge:        '[data-mm="badge"]',
    add:          '[data-mm="add"]',
    oos:          '[data-mm="oos"]',
    "old-price":  '[data-mm="old-price"]',
    low:          '[data-mm="low"]',
    "search-panel":    '[data-mm="search-panel"]',
    "search-backdrop": '[data-mm="search-backdrop"]',
    "search-input":    '[data-mm="search-input"]',
    "search-close":    '[data-mm="search-close"]',
    "search-roll":     '[data-mm="search-roll"]',
    "sp-block":        '[data-mm="sp-block"]',
    "sp-stagger":      '[data-mm="sp-stagger"]'
  };

  var STAGGER = { pills: 45, cats: 60, rail: 55 };
  var MAX_CASCADE = 9;          /* cards past this index share the last delay */
  var ROOT_MARGIN = "0px 0px -6% 0px";
  var FAILSAFE_MS = 3000;

  var root = document.documentElement;
  var reduced = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
  var io, mo, booted = false;

  root.setAttribute("data-mm-js", "");

  function $all(sel, ctx) {
    try { return Array.prototype.slice.call((ctx || document).querySelectorAll(sel)); }
    catch (e) { return []; }
  }

  /* ---------- tagging ---------- */
  function tag(ctx) {
    Object.keys(MAP).forEach(function (role) {
      if (MAP[role] === '[data-mm="' + role + '"]') return;
      $all(MAP[role], ctx).forEach(function (el) {
        if (!el.hasAttribute("data-mm")) el.setAttribute("data-mm", role);
      });
    });
  }

  function rv(el, kind) {
    if (!el || el.hasAttribute("data-mm-rv") || el.hasAttribute("data-mm-skip")) return false;
    el.setAttribute("data-mm-rv", kind);
    return true;
  }

  function prepare(ctx) {
    ctx = ctx || document;
    tag(ctx);
    q("header", ctx).forEach(function (h) {
      rv(h, "fade");
      q("logo", h).forEach(function (e) { rv(e, "left"); watch(e); });
      q("search", h).forEach(function (e) { rv(e, "down"); watch(e, 120); });
      q("cart", h).forEach(function (e) { rv(e, "zoom"); watch(e, 220); });
      watch(h);
    });
    q("pills", ctx).forEach(function (p) { group(p, "down", STAGGER.pills); });
    q("hero", ctx).forEach(function (h) { rv(h, "up"); watch(h, 80); });
    q("cats", ctx).forEach(function (c) { group(c, "zoom", STAGGER.cats); });
    q("sec-head", ctx).forEach(function (s) { rv(s, "up"); watch(s); });
    q("rail", ctx).forEach(function (r) { group(r, "right", STAGGER.rail, true); edges(r); });
    /* cards injected into an already-revealed rail (ajax, React re-render) */
    q("card", ctx).forEach(function (c) {
      var rail = c.closest('[data-mm="rail"]');
      if (!rail) { if (rv(c, "up")) watch(c); return; }
      if (rail.hasAttribute("data-mm-in") && rv(c, "right")) show(c, 40);
    });
  }

  function q(role, ctx) {
    var sel = '[data-mm="' + role + '"]';
    var list = $all(sel, ctx);
    if (ctx && ctx.nodeType === 1 && ctx.matches && ctx.matches(sel)) list.unshift(ctx);
    return list;
  }

  /* a parent observed as one unit; its children cascade */
  function group(parent, kind, stagger, isRail) {
    parent.__mmStagger = stagger;
    parent.__mmRail = !!isRail;
    Array.prototype.forEach.call(parent.children, function (ch) { rv(ch, kind); });
    if (!parent.__mmWatched) { parent.__mmWatched = true; io && io.observe(parent); }
  }

  function watch(el, delay) {
    el.__mmDelay = delay || 0;
    io && io.observe(el);
  }

  /* ---------- reveal ---------- */
  function show(el, delay) {
    if (el.hasAttribute("data-mm-in")) return;
    delay = reduced ? 0 : delay || 0;
    if (delay) el.style.setProperty("--mm-delay", delay + "ms");
    el.setAttribute("data-mm-in", "");
    setTimeout(function () { el.setAttribute("data-mm-done", ""); }, reduced ? 0 : delay + 1000);
    if (el.getAttribute("data-mm") === "hero") playHero(el, delay);
  }

  function reveal(target) {
    if (target.__mmStagger != null) {
      target.setAttribute("data-mm-in", "");
      var i = 0;
      Array.prototype.forEach.call(target.children, function (ch) {
        if (!ch.hasAttribute("data-mm-rv")) return;
        show(ch, Math.min(i, MAX_CASCADE) * target.__mmStagger);
        i++;
      });
    } else {
      show(target, target.__mmDelay);
    }
  }

  function onIntersect(entries) {
    entries.forEach(function (en) {
      if (!en.isIntersecting) return;
      io.unobserve(en.target);
      reveal(en.target);
    });
  }

  /* ---------- hero ---------- */
  function playHero(hero, delay) {
    var text = q("hero-text", hero);
    setTimeout(function () { text.forEach(replay); }, delay || 0);
    var dotsList = q("hero-dots", hero);
    if (!dotsList.length) dotsList = q("hero-dots", document).slice(0, 1); /* dots rendered below the banner */
    dotsList.forEach(function (dots) {
      if (dots.__mmDots) return;
      dots.__mmDots = true;
      new MutationObserver(function () {
        var active = activeIndex(dots);
        if (active !== dots.__mmActive) {
          dots.__mmActive = active;
          q("hero-text", hero).forEach(replay);
        }
      }).observe(dots, { subtree: true, attributes: true, attributeFilter: ["class", "aria-current", "aria-selected", "data-active"] });
      dots.__mmActive = activeIndex(dots);
    });
  }
  function activeIndex(dots) {
    var kids = Array.prototype.slice.call(dots.children);
    return kids.findIndex(function (k) {
      return k.matches('.active,[aria-current="true"],[aria-selected="true"],[data-active="true"]');
    });
  }
  function replay(el) {
    el.removeAttribute("data-mm-play");
    void el.offsetWidth;
    el.setAttribute("data-mm-play", "");
  }

  /* ---------- rails: edge fades ---------- */
  function edges(rail) {
    if (rail.__mmEdges) return;
    rail.__mmEdges = true;
    var raf = 0;
    function update() {
      raf = 0;
      var max = rail.scrollWidth - rail.clientWidth;
      var x = Math.abs(rail.scrollLeft);
      rail.setAttribute("data-mm-edge", max < 4 ? "none" : x < 4 ? "start" : x > max - 4 ? "end" : "middle");
    }
    rail.addEventListener("scroll", function () { if (!raf) raf = requestAnimationFrame(update); }, { passive: true });
    window.addEventListener("resize", update);
    update();
  }

  /* ---------- cart ---------- */
  function flash(el, attr, ms) {
    if (!el) return;
    el.removeAttribute(attr);
    void el.offsetWidth;
    el.setAttribute(attr, "");
    clearTimeout(el["__mm" + attr]);
    el["__mm" + attr] = setTimeout(function () { el.removeAttribute(attr); }, ms);
  }

  function bumpCart() {
    var cart = document.querySelector('[data-mm="cart"]');
    if (cart && cart.animate && !reduced) {
      cart.animate(
        [{ transform: "scale(1)" }, { transform: "scale(1.18) rotate(-6deg)" }, { transform: "scale(0.96) rotate(3deg)" }, { transform: "scale(1)" }],
        { duration: 520, easing: "cubic-bezier(0.34,1.56,0.64,1)" }
      );
    }
    flash(document.querySelector('[data-mm="cart-count"]'), "data-mm-bump", 560);
  }

  function flyToCart(from, done) {
    var cart = document.querySelector('[data-mm="cart"]');
    if (!from || !cart || reduced || !document.body.animate) { bumpCart(); done && done(); return; }
    var a = from.getBoundingClientRect(), b = cart.getBoundingClientRect();
    var x0 = a.left + a.width / 2, y0 = a.top + a.height / 2;
    var x1 = b.left + b.width / 2, y1 = b.top + b.height / 2;
    var ox = document.createElement("div"), oy = document.createElement("div");
    ox.className = "mm-fly-x"; oy.className = "mm-fly-y";
    ox.appendChild(oy); document.body.appendChild(ox);
    var dur = Math.min(900, Math.max(520, Math.hypot(x1 - x0, y1 - y0) * 0.9));
    /* x travels linearly, y eases — together they draw an arc */
    ox.animate([{ transform: "translateX(" + x0 + "px)" }, { transform: "translateX(" + x1 + "px)" }], { duration: dur, easing: "cubic-bezier(0.45,0,0.55,1)", fill: "forwards" });
    var lift = Math.min(y0, y1) - 90;
    var anim = oy.animate([
      { transform: "translateY(" + y0 + "px) scale(1)" },
      { transform: "translateY(" + lift + "px) scale(1.15)", offset: 0.35, easing: "cubic-bezier(0.55,0,1,0.45)" },
      { transform: "translateY(" + y1 + "px) scale(0.45)", opacity: 0.9 }
    ], { duration: dur, easing: "cubic-bezier(0,0.55,0.45,1)", fill: "forwards" });
    anim.onfinish = function () { ox.remove(); bumpCart(); done && done(); };
  }

  function onClick(ev) {
    var add = ev.target.closest && ev.target.closest('[data-mm="add"]');
    if (add) {
      var card = add.closest('[data-mm="card"]');
      var blocked = add.disabled || add.getAttribute("aria-disabled") === "true" ||
        add.hasAttribute("data-mm-soldout") || (card && card.querySelector('[data-mm="oos"]'));
      if (blocked) { flash(card || add, "data-mm-shake", 440); return; }
      flash(add, "data-mm-added", 640);
      flyToCart(add);
      return;
    }
    var pill = ev.target.closest && ev.target.closest('[data-mm="pills"] > *');
    if (pill) flash(pill, "data-mm-press", 380);
  }

  /* ---------- search overlay ----------
     Tap the header search -> page dims, a panel grows out of the bar
     (clip-path, so text never stretches), its blocks and chips cascade in.
     Close: Esc, backdrop, [data-mm="search-close"] -> shrinks back into the bar.
     Emits mm:search-open / mm:search-close on document for app state. */
  var S = { open: false, anim: null, bAnim: null, trigger: null, lastClose: 0, word: 0 };

  function sEls() {
    var panel = document.querySelector('[data-mm="search-panel"]');
    return {
      trigger: S.trigger || document.querySelector('[data-mm="search"]'),
      panel: panel,
      backdrop: document.querySelector('[data-mm="search-backdrop"]'),
      input: panel && panel.querySelector('[data-mm="search-input"]')
    };
  }

  function insetOf(bar, p) {
    function c(v) { return Math.max(0, v).toFixed(1) + "px"; }
    return "inset(" + c(bar.top - p.top) + " " + c(p.right - bar.right) + " " + c(p.bottom - bar.bottom) + " " +
      c(bar.left - p.left) + " round " + (bar.height / 2).toFixed(1) + "px)";
  }

  function placePanel(panel, bar) {
    var vw = document.documentElement.clientWidth;
    if (!bar || vw < 600) { panel.setAttribute("data-mm-sheet", ""); return; }
    panel.removeAttribute("data-mm-sheet");
    var max = parseFloat(getComputedStyle(panel).getPropertyValue("--sp-max")) || 720;
    var w = Math.min(Math.max(max, bar.width + 24), vw - 32);
    var x = Math.min(Math.max(16, bar.left - 12), vw - 16 - w);
    panel.style.setProperty("--sp-x", x + "px");
    panel.style.setProperty("--sp-y", Math.max(8, bar.top - 10) + "px");
    panel.style.setProperty("--sp-w", w + "px");
  }

  function indexStagger(ctx) {
    $all('[data-mm="sp-block"]', ctx).forEach(function (b, i) { b.style.setProperty("--mm-b", i); });
    $all('[data-mm="sp-stagger"]', ctx).forEach(function (g) {
      Array.prototype.forEach.call(g.children, function (ch, i) { ch.style.setProperty("--mm-i", Math.min(i, 14)); });
    });
  }

  function openSearch(trigger) {
    if (trigger) S.trigger = trigger;
    var e = sEls();
    if (!e.panel || S.open) return;
    S.open = true;
    var bar = e.trigger ? e.trigger.getBoundingClientRect() : null;
    root.setAttribute("data-mm-search-open", "");
    if (e.backdrop) e.backdrop.hidden = false;
    e.panel.hidden = false;
    e.panel.removeAttribute("data-mm-sp-in");
    placePanel(e.panel, bar);
    indexStagger(e.panel);
    if (e.input) { try { e.input.focus({ preventScroll: true }); } catch (x) { e.input.focus(); } }

    if (S.anim) S.anim.cancel();
    if (S.bAnim) S.bAnim.cancel();
    if (!reduced && e.panel.animate) {
      var p = e.panel.getBoundingClientRect();
      var R = getComputedStyle(e.panel).borderTopLeftRadius || "0px";
      var from = bar ? insetOf(bar, p) : "inset(0px 0px 100% 0px round 16px)";
      S.anim = e.panel.animate(
        [{ clipPath: from, boxShadow: "0 0 0 rgba(0,0,0,0)" }, { clipPath: "inset(0px 0px 0px 0px round " + R + ")" }],
        { duration: 420, easing: "cubic-bezier(0.2, 0.9, 0.25, 1)" }
      );
      S.anim.onfinish = function () { S.anim = null; };
      if (e.backdrop) S.bAnim = e.backdrop.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 260, easing: "ease-out" });
    }
    requestAnimationFrame(function () { requestAnimationFrame(function () { if (S.open) e.panel.setAttribute("data-mm-sp-in", ""); }); });
    document.dispatchEvent(new CustomEvent("mm:search-open"));
  }

  function closeSearch() {
    var e = sEls();
    if (!e.panel || !S.open) return;
    S.open = false;
    S.lastClose = Date.now();
    e.panel.removeAttribute("data-mm-sp-in");
    function done() {
      e.panel.hidden = true;
      if (e.backdrop) e.backdrop.hidden = true;
      root.removeAttribute("data-mm-search-open");
      if (S.anim) { S.anim.cancel(); S.anim = null; }
      if (S.bAnim) { S.bAnim.cancel(); S.bAnim = null; }
      if (e.trigger) { try { e.trigger.focus({ preventScroll: true }); } catch (x) {} }
    }
    if (S.anim) S.anim.cancel();
    if (S.bAnim) S.bAnim.cancel();
    if (reduced || !e.panel.animate) { done(); }
    else {
      var p = e.panel.getBoundingClientRect();
      var bar = e.trigger ? e.trigger.getBoundingClientRect() : null;
      var R = getComputedStyle(e.panel).borderTopLeftRadius || "0px";
      S.anim = e.panel.animate(
        [{ clipPath: "inset(0px 0px 0px 0px round " + R + ")", opacity: 1 },
         { clipPath: bar ? insetOf(bar, p) : "inset(0px 0px 100% 0px round 16px)", opacity: 0.3 }],
        { duration: 260, easing: "cubic-bezier(0.5, 0, 0.75, 0)", fill: "forwards" }
      );
      if (e.backdrop) S.bAnim = e.backdrop.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 260, fill: "forwards" });
      S.anim.onfinish = done;
    }
    document.dispatchEvent(new CustomEvent("mm:search-close"));
  }

  /* re-run the cascade on a container whose children just changed (live results) */
  function staggerIn(container) {
    if (!container) return;
    Array.prototype.forEach.call(container.children, function (ch, i) { ch.style.setProperty("--mm-i", Math.min(i, 14)); });
    replayAttr(container, "data-mm-sp-replay");
  }
  function staggerOut(container, cb) {
    if (!container) { cb && cb(); return; }
    var n = container.children.length;
    Array.prototype.forEach.call(container.children, function (ch, i) { ch.style.setProperty("--mm-i", Math.min(i, 14)); });
    container.setAttribute("data-mm-sp-out", "");
    setTimeout(function () { container.removeAttribute("data-mm-sp-out"); cb && cb(); }, reduced ? 0 : Math.min(n, 14) * 22 + 260);
  }
  function replayAttr(el, attr) { el.removeAttribute(attr); void el.offsetWidth; el.setAttribute(attr, ""); }

  /* rolling "Search for '…'" words: every [data-mm="search-roll"] shares one clock */
  function startRoll() {
    var rolls = $all('[data-mm="search-roll"]').filter(function (r) { return r.children.length > 1; });
    if (!rolls.length || S.rollTimer) return;
    function paint() {
      rolls.forEach(function (r) {
        var kids = r.children, n = kids.length, cur = S.word % n, prev = (cur - 1 + n) % n;
        Array.prototype.forEach.call(kids, function (k, j) {
          k.setAttribute("data-mm-word", j === cur ? "in" : j === prev ? "out" : "");
        });
      });
    }
    paint();
    if (reduced) return;
    S.rollTimer = setInterval(function () { if (!document.hidden) { S.word++; paint(); } }, 2600);
  }

  function bindSearch() {
    if (!document.querySelector('[data-mm="search-panel"]')) return;
    document.addEventListener("click", function (ev) {
      var t = ev.target.closest && ev.target.closest('[data-mm="search"]');
      if (t && !t.closest('[data-mm="search-panel"]')) { ev.preventDefault(); openSearch(t); return; }
      if (S.open && ev.target.closest && ev.target.closest('[data-mm="search-close"],[data-mm="search-backdrop"]')) closeSearch();
    });
    document.addEventListener("focusin", function (ev) {
      var t = ev.target.closest && ev.target.closest('[data-mm="search"]');
      if (t && !S.open && Date.now() - S.lastClose > 450 && !t.closest('[data-mm="search-panel"]') && ev.target.matches("input")) openSearch(t);
    });
    document.addEventListener("keydown", function (ev) {
      var tag = (document.activeElement && document.activeElement.tagName) || "";
      if (!S.open) {
        if (ev.key === "/" && !/INPUT|TEXTAREA|SELECT/.test(tag) && !ev.metaKey && !ev.ctrlKey) { ev.preventDefault(); openSearch(); }
        return;
      }
      if (ev.key === "Escape") { ev.preventDefault(); closeSearch(); return; }
      if (ev.key === "Tab") {
        var f = $all('a[href],button:not([disabled]),input,[tabindex]:not([tabindex="-1"])', sEls().panel)
          .filter(function (el) { return el.offsetParent !== null; });
        if (!f.length) return;
        var first = f[0], last = f[f.length - 1];
        if (ev.shiftKey && document.activeElement === first) { ev.preventDefault(); last.focus(); }
        else if (!ev.shiftKey && document.activeElement === last) { ev.preventDefault(); first.focus(); }
      }
    });
  }

  /* ---------- failsafe ---------- */
  function failsafe() {
    $all("[data-mm-rv]:not([data-mm-in])").forEach(function (el) {
      var r = el.getBoundingClientRect();
      if (r.bottom > 0 && r.top < innerHeight && r.width) show(el, 0);
    });
    $all('html[data-mm-js] [data-mm="hero-text"]:not([data-mm-play])').forEach(replay);
  }

  /* ---------- boot ---------- */
  function init() {
    if (booted) return;
    booted = true;
    if (!("IntersectionObserver" in window)) { root.removeAttribute("data-mm-js"); return; }
    io = new IntersectionObserver(onIntersect, { rootMargin: ROOT_MARGIN, threshold: 0.12 });
    prepare(document);
    document.addEventListener("click", onClick, true);
    bindSearch();
    startRoll();
    mo = new MutationObserver(function (muts) {
      muts.forEach(function (m) {
        Array.prototype.forEach.call(m.addedNodes, function (n) {
          if (n.nodeType !== 1) return;
          var parentGroup = n.parentElement && n.parentElement.__mmStagger != null ? n.parentElement : null;
          prepare(n);
          if (parentGroup) {
            rv(n, parentGroup.__mmRail ? "right" : "zoom");
            if (parentGroup.hasAttribute("data-mm-in")) show(n, 40);
          }
        });
      });
    });
    mo.observe(document.body, { childList: true, subtree: true });
    setTimeout(failsafe, FAILSAFE_MS);
  }

  /* re-arm everything from scratch (used by the preview's Replay button) */
  function replayAll() {
    $all("[data-mm-in],[data-mm-done]").forEach(function (el) {
      el.removeAttribute("data-mm-in");
      el.removeAttribute("data-mm-done");
      el.style.removeProperty("--mm-delay");
    });
    $all("[data-mm-play]").forEach(function (el) { el.removeAttribute("data-mm-play"); });
    $all("[data-mm-rv]").forEach(function (el) {
      if (el.__mmStagger == null && el.parentElement && el.parentElement.__mmStagger != null) return;
      io.unobserve(el); io.observe(el);
    });
    $all("[data-mm]").forEach(function (el) { if (el.__mmStagger != null) { io.unobserve(el); io.observe(el); } });
  }

  window.MartMotion = {
    init: init,
    refresh: function (ctx) { prepare(ctx || document); },
    flyToCart: flyToCart,
    bumpCart: bumpCart,
    replay: replayAll,
    openSearch: openSearch,
    closeSearch: closeSearch,
    staggerIn: staggerIn,
    staggerOut: staggerOut,
    map: MAP
  };

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
