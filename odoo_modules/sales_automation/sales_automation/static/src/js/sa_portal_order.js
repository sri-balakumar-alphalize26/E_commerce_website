/** @odoo-module ignore **/
/* The customer's order page (/my/orders/<id>), 23 Nov 2026. Loaded with the
   website's scripts but does nothing outside that page and Odoo's
   /payment/status while an order is being paid.
   1. A delivery slot moves with an animation, no page reload.
   2. One Back leaves: our own steps replace the page instead of adding one,
      and an old step brought back by Back shows its present state.
   3. The location of the order: the phone's position, no page reload.
   Everything still works without this file. */
(function () {
    "use strict";
    var ORDER = /^\/(?:[a-z]{2}(?:_[A-Za-z]{2,4})?\/)?my\/orders\/\d+$/;
    var STATUS = /^\/(?:[a-z]{2}(?:_[A-Za-z]{2,4})?\/)?payment\/status$/;
    var path = window.location.pathname;
    var isOrder = ORDER.test(path), isStatus = STATUS.test(path);
    if (!isOrder && !isStatus) { return; }

    function keep(key, value) {
        try {
            if (value === undefined) { return window.sessionStorage.getItem(key) || ""; }
            window.sessionStorage.setItem(key, value);
        } catch (e) { /* private mode: the page works without it */ }
        return "";
    }
    function ready(fn) {
        if (document.readyState === "loading") { document.addEventListener("DOMContentLoaded", fn); } else { fn(); }
    }
    function ours() { return isOrder ? !!document.querySelector(".sa-page") : !!keep("saOrderFlow"); }
    ready(function () { if (isOrder && ours()) { keep("saOrderFlow", path + window.location.search); } });

    // ---------------------------------------------------------- 2. one Back
    function cameBack(event) {
        var nav = window.performance && performance.getEntriesByType ? performance.getEntriesByType("navigation")[0] : null;
        return event.persisted || (nav && nav.type === "back_forward");
    }
    window.addEventListener("pageshow", function (event) {
        if (!cameBack(event)) { return; }
        ready(function () {
            if (!ours()) { return; }
            if (isStatus) { window.location.replace(keep("saOrderFlow")); } else { window.location.reload(); }
        });
    });
    if (window.navigation && window.navigation.addEventListener) {
        window.navigation.addEventListener("navigate", function (event) {
            if (!event.cancelable || event.navigationType !== "push" || event.hashChange || event.formData
                    || event.downloadRequest !== null || !ours()) { return; }
            var url = new URL(event.destination.url);
            if (url.searchParams.has("report_type") || url.origin !== window.location.origin || !(ORDER.test(url.pathname) || STATUS.test(url.pathname))) { return; }
            event.preventDefault();
            window.setTimeout(function () { window.location.replace(url.href); }, 0);
        });
    }

    // ------------------------------------------ the waiting page becomes Pay
    ready(function () {
        var page = document.querySelector('.sa-page[data-step="wait"]');
        var token = new URLSearchParams(window.location.search).get("access_token");
        if (!isOrder || !page || !token || !window.fetch) { return; }
        var asked = 0;
        (function again() {
            window.setTimeout(function () {
                if (document.hidden) { again(); return; }
                asked += 1;
                fetch(path + "/step?access_token=" + encodeURIComponent(token), { credentials: "same-origin" })
                    .then(function (reply) { return reply.ok ? reply.json() : {}; })
                    .then(function (answer) { 
                        if (answer.step !== "go") { again(); return; }
                        if (keep("saWaitReload") === path) { return; }     // once: never in a circle
                        keep("saWaitReload", path);
                        window.location.reload();
                    })
                    .catch(again);
            }, asked < 90 ? 10000 : 60000);
        })();
    });

    // ------------------------------------------------------ 3. the location
    ready(function () {
        var box = document.querySelector(".sa-loc");
        var form = box && box.querySelector(".sa-loc-form");
        if (!box) { return; }
        var change = box.querySelector(".sa-loc-change");
        if (change) { change.addEventListener("click", function () { box.classList.toggle("open"); }); }
        if (!form || !window.fetch || !navigator.geolocation) {
            return;                              // "Pick on map" is left
        }
        form.hidden = false;
        var button = form.querySelector("button"), words = button.textContent;
        function say(text) {
            var line = box.querySelector(".sa-note");
            if (!text) { if (line) { line.remove(); } return; }
            if (!line) {
                line = document.createElement("p");
                line.className = "sa-note";
                line.setAttribute("role", "alert");
                box.appendChild(line);
            }
            line.textContent = text;
        }
        function idle() { button.disabled = false; button.textContent = words; }
        form.addEventListener("submit", function (event) {
            event.preventDefault();
            if (button.disabled) { return; }
            button.disabled = true;
            button.textContent = "Finding you\u2026";
            say("");
            navigator.geolocation.getCurrentPosition(function (found) {
                var data = new FormData(form);
                data.set("lat", found.coords.latitude);
                data.set("lng", found.coords.longitude);
                fetch(form.action, {
                    method: "POST", body: data, credentials: "same-origin", headers: { "X-Requested-With": "fetch" },
                }).then(function (reply) {
                    if (!reply.ok) { throw new Error("location " + reply.status); }
                    return reply.json();
                }).then(function (answer) {
                    idle();
                    if (!answer.ok) { say(answer.error); return; }
                    if (answer.reload) { window.location.reload(); return; }     // the total changed
                    box.dataset.has = "1";
                    box.classList.remove("open");
                }).catch(function () { idle(); say("Could not save the location. Please try again."); });
            }, function () {
                idle();
                say("Your phone did not give the location. Allow it for this page"
                    + (box.querySelector(".sa-loc-map") ? ", or use Pick on map." : " and try again."));
            }, { enableHighAccuracy: true, timeout: 20000, maximumAge: 30000 });
        });
    });

    // ------------------------------------------------------------- 1. slots
    function rect(chip, form) {
        var a = chip.getBoundingClientRect(), b = form.getBoundingClientRect();
        return { left: a.left - b.left, top: a.top - b.top, width: a.width, height: a.height };
    }
    function place(el, r) {
        el.style.left = r.left + "px"; el.style.top = r.top + "px";
        el.style.width = r.width + "px"; el.style.height = r.height + "px";
    }
    function mark(form, chip) {
        form.querySelectorAll(".sa-slotchip").forEach(function (c) {
            c.classList.toggle("on", c === chip);
            c.setAttribute("aria-pressed", c === chip ? "true" : "false");
        });
    }
    function slide(form, from, to) {
        var still = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        if (!from || from === to || still) { mark(form, to); return; }
        var glide = document.createElement("span");
        glide.className = "sa-slot-glide";
        glide.setAttribute("aria-hidden", "true");
        place(glide, rect(from, form));
        form.appendChild(glide);
        from.classList.remove("on");
        void glide.offsetWidth;
        place(glide, rect(to, form));
        window.setTimeout(function () { mark(form, to); glide.remove(); }, 260);
    }
    function note(form, text) {
        var box = form.parentNode.querySelector(".sa-slot-msg");
        if (!text) { if (box) { box.remove(); } return; }
        if (!box) {
            box = document.createElement("p");
            box.className = "sa-note sa-slot-msg";
            box.setAttribute("role", "alert");
            form.parentNode.insertBefore(box, form);
        }
        box.textContent = text;
    }
    document.addEventListener("submit", function (event) {
        var form = event.target;
        if (!form || !form.matches) { return; }
        var chip = event.submitter;
        if (form.matches(".sa-loc-map")) { keep("saAddrFrom", "1"); return; }
        if (form.closest(".sa-addr")) {
            var what = form.querySelector("input[name=do]");
            if (!what || what.value !== "use") { keep("saAddrFrom", "1"); return; }   // add / edit: their own page
            if (!chip || !window.fetch) { return; }
            event.preventDefault();
            if (form.dataset.busy) { return; }
            form.dataset.busy = "1";
            var pick = new FormData(form);
            pick.set("address_id", chip.value);
            fetch(form.action, { method: "POST", body: pick, credentials: "same-origin" }).then(function (reply) {
                if (!reply.ok || !ORDER.test(new URL(reply.url).pathname)) { throw new Error("address " + reply.status); }
                // this same entry, drawn again: nothing is added for Back
                window.history.replaceState(null, "", reply.url.split("#")[0] + "#sa_address");
                window.location.reload();
            }).catch(function () {
                var id = document.createElement("input");
                id.type = "hidden"; id.name = "address_id"; id.value = chip.value;
                form.appendChild(id);
                HTMLFormElement.prototype.submit.call(form);
            });
            return;
        }
        if (!form.matches(".sa-slot-chips") || !chip || !window.fetch) { return; }
        event.preventDefault();
        if (form.dataset.busy || chip.classList.contains("on")) { return; }
        form.dataset.busy = "1";
        var before = form.querySelector(".sa-slotchip.on");
        var data = new FormData(form);
        data.set("slot_key", chip.value);
        note(form, "");
        form.parentNode.querySelectorAll(".sa-note").forEach(function (n) { n.remove(); });
        slide(form, before, chip);
        fetch(form.action, {
            method: "POST", body: data, credentials: "same-origin", headers: { "X-Requested-With": "fetch" },
        }).then(function (reply) {
            if (!reply.ok) { throw new Error("slot " + reply.status); }
            return reply.json();
        }).then(function (answer) {
            window.setTimeout(function () {
                delete form.dataset.busy;
                if (!answer.ok) {
                    var back = null;
                    form.querySelectorAll(".sa-slotchip").forEach(function (c) { if (c.value === answer.chosen) { back = c; } });
                    if (back) { slide(form, chip, back); }
                    note(form, answer.error);
                    return;
                }
                document.querySelectorAll(".sa-promise b").forEach(function (b) {
                    if (answer.promise) { b.textContent = answer.promise; }
                });
            }, 280);
        }).catch(function () {
            // no answer: the plain form, as without this script
            var hidden = document.createElement("input");
            hidden.type = "hidden"; hidden.name = "slot_key"; hidden.value = chip.value;
            form.appendChild(hidden);
            HTMLFormElement.prototype.submit.call(form);
        });
    });
})();
