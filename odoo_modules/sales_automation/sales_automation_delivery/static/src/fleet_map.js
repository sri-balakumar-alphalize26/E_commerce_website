/** @odoo-module **/

/**
 * Delivery > Fleet > Live Map: every rider on one map (free, on a run, no
 * signal), each run's stops in order with minutes, a 30-minute trail for the
 * rider you tap, the shops and the orders still waiting for a rider. The
 * Shop Queue opens the same screen filtered to one shop.
 *
 * Drawn like the Delivery Partner app (17 Nov 2026): MapLibre on OpenFreeMap's
 * free "Liberty" map (no key), the scooter picture turned to where the rider
 * is heading and gliding between updates instead of jumping, shop pins in
 * green (#0F3D2E) and customer pins in orange (#C2410C). When MapLibre cannot
 * start (no WebGL, the map style does not load) the screen falls back to
 * Leaflet + OpenStreetMap, as before.
 */

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { loadCSS, loadJS } from "@web/core/assets";
import { Component, onMounted, onWillStart, onWillUnmount, useState, useRef } from "@odoo/owl";

const MAPLIBRE_JS = "https://unpkg.com/maplibre-gl@5.24.0/dist/maplibre-gl.js";
const MAPLIBRE_CSS = "https://unpkg.com/maplibre-gl@5.24.0/dist/maplibre-gl.css";
const STYLE = "https://tiles.openfreemap.org/styles/liberty";
const LEAFLET_JS = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";
const LEAFLET_CSS = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";
const RIDER_PICTURE = "/sales_automation_delivery/static/src/img/rider-top.png";
const COLOR = { free: "#1a7f3c", run: "#0a78ab", no_signal: "#8a96a0", off: "#c9d1d8", sos: "#b42318" };
const PIN = { shop: "#0F3D2E", customer: "#C2410C", covered: "#5F7A6E" };
const PADDING = { top: 64, right: 64, bottom: 96, left: 64 };
const STYLE_WAIT_MS = 8000;     // the map style must arrive in this time, or Leaflet takes over
const GLIDE_MS = 14000;         // a little under the 15 s refresh: the scooter keeps moving
const JUMP_KM = 3;              // further than this in one refresh: placed, not glided

function bearing(from, to) {
    // degrees from north, clockwise, between two [lng, lat]
    const rad = Math.PI / 180;
    const [lng1, lat1] = [from[0] * rad, from[1] * rad];
    const [lng2, lat2] = [to[0] * rad, to[1] * rad];
    const y = Math.sin(lng2 - lng1) * Math.cos(lat2);
    const x = Math.cos(lat1) * Math.sin(lat2) - Math.sin(lat1) * Math.cos(lat2) * Math.cos(lng2 - lng1);
    return (Math.atan2(y, x) / rad + 360) % 360;
}

function km(a, b) {
    const rad = Math.PI / 180;
    const dLat = (b[1] - a[1]) * rad;
    const dLng = (b[0] - a[0]) * rad;
    const h = Math.sin(dLat / 2) ** 2 + Math.cos(a[1] * rad) * Math.cos(b[1] * rad) * Math.sin(dLng / 2) ** 2;
    return 12742 * Math.asin(Math.sqrt(h));
}

function initials(name) {
    return (name || "?").split(/\s+/).filter(Boolean).map((w) => w[0]).join("").slice(0, 2).toUpperCase() || "?";
}

export class FleetMap extends Component {
    static template = "sales_automation_delivery.FleetMap";
    static props = { "*": true };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.mapRef = useRef("map");
        const ctx = (this.props.action && this.props.action.context) || {};
        this.state = useState({
            riders: [], shops: [], waiting: [], counts: { riders: 0, waiting: 0 },
            shopId: ctx.sa_shop_id || 0, shopName: "",
            selected: ctx.sa_focus_rider || 0,
            at: "", loading: true, mapReady: false, error: "",
            tick: 0,
        });
        this._layers = { riders: {}, stops: null, trail: null, run: null, shops: null, waiting: null };
        this._marks = { shops: new Map(), waiting: new Map(), stops: new Map(), riders: new Map() };
        this._fitted = false;
        this._kind = null;   // "free" (MapLibre) or "leaflet"

        onWillStart(async () => {
            try {
                await loadCSS(MAPLIBRE_CSS);
                await loadJS(MAPLIBRE_JS);
            } catch {
                // no MapLibre: Leaflet below
            }
            if (!window.maplibregl) {
                await this._loadLeaflet();
            }
            await this.refresh();
        });
        onMounted(() => {
            this._initMap();
            this._timer = setInterval(() => this.refresh().catch(() => {}), 15000);
            this._ticker = setInterval(() => { this.state.tick += 1; }, 1000);
        });
        onWillUnmount(() => {
            clearInterval(this._timer);
            clearInterval(this._ticker);
            clearTimeout(this._styleTimer);
            this._dropMap();
        });
    }

    // ---------------------------------------------------------------- data
    async refresh() {
        const data = await this.orm.call("stock.picking", "sa_fleet_snapshot", [this.state.shopId || null]);
        this.state.riders = data.riders;
        this.state.shops = data.shops;
        this.state.waiting = data.waiting;
        this.state.counts = data.counts;
        this.state.at = data.at;
        this.state.loading = false;
        if (this.state.shopId) {
            const s = data.shops.find((x) => x.id === this.state.shopId);
            this.state.shopName = s ? s.name : "";
        }
        this._draw();
    }

    age(r) {
        // re-read on every tick so the "updated N s ago" counts up
        void this.state.tick;
        if (r.age_seconds === null || r.age_seconds === undefined) { return "no position yet"; }
        const base = r.age_seconds + Math.round((Date.now() - this._atMs()) / 1000);
        if (base < 90) { return `updated ${Math.max(0, base)} s ago`; }
        if (base < 3600) { return `last seen ${Math.round(base / 60)} min ago`; }
        return `last seen ${Math.round(base / 3600)} h ago`;
    }
    _atMs() {
        if (!this._atCache || this._atCache.iso !== this.state.at) {
            this._atCache = { iso: this.state.at, ms: new Date(this.state.at).getTime() || Date.now() };
        }
        return this._atCache.ms;
    }
    stateLabel(r) {
        return { free: "Free", run: `On a run · ${r.stops.length} stop${r.stops.length === 1 ? "" : "s"}`,
                 no_signal: "No signal", off: "Off duty", sos: "SOS - not available" }[r.state] || r.state;
    }
    stopLine(s) {
        const bits = [];
        if (s.km !== null && s.km !== undefined) { bits.push(`${s.km} km`); }
        if (s.minutes !== null && s.minutes !== undefined) { bits.push(`${s.minutes} min`); }
        return bits.join(" · ");
    }
    get filterShops() {
        // branches the storefront adds to the map are not delivery shops: no filter for them
        return this.state.shops.filter((s) => !s.extra);
    }

    // ---------------------------------------------------------------- actions
    select(r) {
        this.state.selected = this.state.selected === r.id ? 0 : r.id;
        this._draw();
        if (this.state.selected && this._map && r.latitude) {
            if (this._kind === "free") {
                this._map.easeTo({ center: [r.longitude, r.latitude], duration: 500 });
            } else {
                this._map.panTo([r.latitude, r.longitude], { animate: true });
            }
        }
    }
    openJob(jobId) {
        this.action.doAction({ type: "ir.actions.act_window", res_model: "stock.picking", res_id: jobId,
                               views: [[false, "form"]], target: "current" });
    }
    openRider(riderId) {
        this.action.doAction({ type: "ir.actions.act_window", res_model: "sa.delivery.partner", res_id: riderId,
                               views: [[false, "form"]], target: "current" });
    }
    async callRider(w) {
        try {
            await this.orm.call("stock.picking", "sa_action_call_rider", [[w.job_id]]);
            this.notification.add(`A rider is being called for #${w.ref}.`, { type: "success" });
        } catch (e) {
            this.notification.add((e && e.data && e.data.message) || "Could not call a rider.", { type: "danger" });
        }
        await this.refresh();
    }
    onShopChange(ev) {
        this.state.shopId = parseInt(ev.target.value, 10) || 0;
        this._fitted = false;
        this.refresh();
    }

    // ---------------------------------------------------------------- the map
    _initMap() {
        if (!this.mapRef.el) { return; }
        if (window.maplibregl) {
            this._initFree();
        } else if (window.L) {
            this._initLeaflet();
            this._draw();
        } else {
            this.state.error = "The map could not be loaded (no internet?). The list still works.";
        }
    }

    _draw() {
        if (this._kind === "free") {
            if (this._ready) { this._drawFree(); }
        } else if (this._kind === "leaflet") {
            this._drawLeaflet();
        }
    }

    _dropMap() {
        for (const group of Object.values(this._marks)) {
            for (const m of group.values()) {
                if (m.frame) { cancelAnimationFrame(m.frame); }
            }
            group.clear();
        }
        try {
            if (this._map) { this._map.remove(); }
        } catch {
            // it never got going
        }
        this._map = null;
        this._ready = false;
        this._kind = null;
        this._layers = { riders: {}, stops: null, trail: null, run: null, shops: null, waiting: null };
    }

    async _loadLeaflet() {
        if (window.L) { return true; }
        try {
            await loadCSS(LEAFLET_CSS);
            await loadJS(LEAFLET_JS);
            return true;
        } catch {
            this.state.error = "The map could not be loaded (no internet?). The list still works.";
            return false;
        }
    }

    async _toLeaflet() {
        // an error and the style timeout can both ask: switch once
        if (this._kind === "leaflet" || this._switching) { return; }
        this._switching = true;
        clearTimeout(this._styleTimer);
        this._dropMap();
        this._fitted = false;
        if (await this._loadLeaflet() && this.mapRef.el) {
            this._initLeaflet();
            this._draw();
        }
        this._switching = false;
    }

    // ------------------------------------------------- MapLibre (the usual map)
    _initFree() {
        const ml = window.maplibregl;
        this._kind = "free";
        this._ready = false;
        try {
            this._map = new ml.Map({
                container: this.mapRef.el,
                style: STYLE,
                center: [55.3, 25.2],
                zoom: 11,
                maxZoom: 19,
                dragRotate: false,
                pitchWithRotate: false,
                touchPitch: false,
                attributionControl: { compact: false },
            });
        } catch {
            // no WebGL: not from inside this call, the component is mid-mount
            setTimeout(() => this._toLeaflet(), 0);
            return;
        }
        this._map.touchZoomRotate.disableRotation();
        this._map.keyboard.disableRotation();
        this._map.addControl(new ml.NavigationControl({ showCompass: false }), "top-right");
        this._styleTimer = setTimeout(() => this._toLeaflet(), STYLE_WAIT_MS);
        this._map.on("error", (e) => { if (!this._ready && !(e && e.sourceId)) { this._toLeaflet(); } });
        this._map.once("load", () => {
            clearTimeout(this._styleTimer);
            if (this._kind !== "free") { return; }
            this._addLines();
            this._ready = true;
            this.state.mapReady = true;
            this._draw();
        });
    }

    _addLines() {
        const map = this._map;
        const empty = { type: "FeatureCollection", features: [] };
        // under the street names, like the app; the pins and scooters are above everything
        const firstLabel = map.getStyle().layers.find((l) => l.type === "symbol");
        const before = firstLabel && firstLabel.id;
        map.addSource("sa-trail", { type: "geojson", data: empty });
        map.addSource("sa-run", { type: "geojson", data: empty });
        map.addLayer({
            id: "sa-trail", type: "line", source: "sa-trail",
            layout: { "line-cap": "round", "line-join": "round" },
            paint: { "line-color": PIN.covered, "line-width": 5, "line-opacity": 0.85 },
        }, before);
        map.addLayer({
            id: "sa-run", type: "line", source: "sa-run",
            layout: { "line-cap": "round", "line-join": "round" },
            paint: {
                "line-color": PIN.customer,
                "line-width": ["case", ["get", "sel"], 5, 3],
                "line-opacity": ["case", ["get", "sel"], 0.95, 0.55],
                // straight legs (no road route on this screen): dashed, as in the app
                "line-dasharray": [2, 1.5],
            },
        }, before);
    }

    _pin(cls, text, title, onClick) {
        // a round head on a short stem, anchored at the stem's foot (the app's pin)
        const el = document.createElement("div");
        el.className = `sa_fm_pin ${cls}`;
        el.title = title || "";
        const head = document.createElement("i");
        head.textContent = text || "";
        el.appendChild(head);
        el.appendChild(document.createElement("u"));
        if (onClick) {
            el.addEventListener("click", (ev) => { ev.stopPropagation(); onClick(); });
        } else {
            el.style.cursor = "default";
        }
        return el;
    }

    _sync(group, items, make, update) {
        // keep one marker per item: drop the gone, make the new, update the rest
        const ml = window.maplibregl;
        const seen = new Set();
        for (const item of items) {
            const key = String(item.key);
            seen.add(key);
            let mark = group.get(key);
            if (!mark) {
                const { el, anchor } = make(item);
                mark = { marker: new ml.Marker({ element: el, anchor }).setLngLat(item.at).addTo(this._map), el };
                group.set(key, mark);
            }
            update(mark, item);
        }
        for (const [key, mark] of group) {
            if (!seen.has(key)) {
                if (mark.frame) { cancelAnimationFrame(mark.frame); }
                mark.marker.remove();
                group.delete(key);
            }
        }
    }

    _drawFree() {
        const map = this._map;
        const sel = this.state.selected;
        const pts = [];
        const at = (o) => [o.longitude, o.latitude];

        // shops: green
        const shops = this.state.shops.filter((s) => s.latitude);
        this._sync(this._marks.shops, shops.map((s) => ({ ...s, key: s.id, at: at(s) })),
            (s) => ({ el: this._pin("shop", "", s.name), anchor: "bottom" }),
            (m, s) => {
                m.marker.setLngLat(s.at);
                m.el.classList.toggle("approx", !!s.approximate);
                m.el.title = s.name + (s.approximate ? " (approximate)" : "");
            });
        shops.forEach((s) => pts.push(at(s)));

        // orders waiting for a rider: orange ring with "!"
        const waiting = this.state.waiting.filter((w) => w.latitude);
        this._sync(this._marks.waiting, waiting.map((w) => ({ ...w, key: w.job_id, at: at(w) })),
            (w) => ({ el: this._pin("wait", "!", "", () => this.openJob(w.job_id)), anchor: "bottom" }),
            (m, w) => {
                m.marker.setLngLat(w.at);
                m.el.classList.toggle("approx", !!w.approximate);
                m.el.title = `#${w.ref} waiting · ${w.customer}${w.approximate ? " (approximate)" : ""}`;
            });
        waiting.forEach((w) => pts.push(at(w)));

        // each run's stops: orange, numbered; the run line rider -> 1 -> 2 ...
        const stops = [];
        const runs = [];
        const trails = [];
        for (const r of this.state.riders) {
            if (r.state === "off" && !r.stops.length) { continue; }
            const isSel = r.id === sel;
            const line = r.latitude ? [at(r)] : [];
            for (const s of r.stops) {
                if (!s.latitude) { continue; }
                stops.push({ ...s, key: s.job_id, at: at(s), sel: isSel });
                line.push(at(s));
                pts.push(at(s));
            }
            if (line.length > 1 && (isSel || !sel)) {
                runs.push({ type: "Feature", properties: { sel: isSel }, geometry: { type: "LineString", coordinates: line } });
            }
            if (isSel && r.trail && r.trail.length > 1) {
                trails.push({ type: "Feature", properties: {},
                              geometry: { type: "LineString", coordinates: r.trail.map((p) => [p[1], p[0]]) } });
            }
        }
        this._sync(this._marks.stops, stops,
            (s) => ({ el: this._pin("stop", String(s.stop_no), "", () => this.openJob(s.job_id)), anchor: "bottom" }),
            (m, s) => {
                m.marker.setLngLat(s.at);
                m.el.firstChild.textContent = String(s.stop_no);
                m.el.classList.toggle("sel", !!s.sel);
                m.el.classList.toggle("approx", !!s.approximate);
                m.el.title = `${s.stop_no} · #${s.ref} ${s.customer}${this.stopLine(s) ? " · " + this.stopLine(s) : ""}`;
            });
        map.getSource("sa-run").setData({ type: "FeatureCollection", features: runs });
        map.getSource("sa-trail").setData({ type: "FeatureCollection", features: trails });

        // riders: the scooter, turned to its heading, gliding to each new position
        const riders = this.state.riders.filter((r) => r.latitude && !(r.state === "off" && !r.stops.length));
        this._sync(this._marks.riders, riders.map((r) => ({ ...r, key: r.id, at: at(r) })),
            (r) => {
                // MapLibre owns the outer element's classes; the look is on the inner one
                const el = document.createElement("div");
                el.innerHTML = `<div class="sa_fm_rd"><span class="ring"></span><img alt="" src="${RIDER_PICTURE}"/><b></b></div>`;
                el.addEventListener("click", (ev) => { ev.stopPropagation(); this.select(this.state.riders.find((x) => x.id === r.id) || r); });
                return { el, anchor: "center" };
            },
            (m, r) => {
                const look = m.el.firstChild;
                look.className = `sa_fm_rd ${r.state}${r.id === sel ? " sel" : ""}`;
                look.querySelector("b").textContent = initials(r.name);
                m.el.title = `${r.name} · ${this.stateLabel(r)}`;
                m.el.style.zIndex = r.id === sel ? "3" : "2";
                this._glide(m, r.at, r.heading);
            });
        riders.forEach((r) => pts.push(at(r)));

        if (!this._fitted && pts.length) {
            if (pts.length === 1) {
                map.jumpTo({ center: pts[0], zoom: 15 });
            } else {
                const ml = window.maplibregl;
                const bounds = pts.reduce((b, p) => b.extend(p), new ml.LngLatBounds(pts[0], pts[0]));
                map.fitBounds(bounds, { padding: PADDING, maxZoom: 15, duration: 0 });
            }
            this._fitted = true;
        }
    }

    _turn(m, deg) {
        if (deg === null || deg === undefined || isNaN(deg)) { return; }
        m.heading = deg;
        const img = m.el.querySelector("img");
        if (img) { img.style.transform = `rotate(${deg}deg)`; }
    }

    _glide(m, to, heading) {
        const from = m.shown || to;
        if (m.target && m.target[0] === to[0] && m.target[1] === to[1]) {
            return;   // the same fix as last time: let the glide finish
        }
        m.target = to;
        if (m.frame) { cancelAnimationFrame(m.frame); m.frame = 0; }
        const moved = km(from, to);
        if (moved * 1000 >= 5) {
            this._turn(m, heading !== null && heading !== undefined ? heading : bearing(from, to));
        } else if (heading !== null && heading !== undefined) {
            this._turn(m, heading);
        }
        const reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        if (!m.shown || moved > JUMP_KM || moved * 1000 < 5 || reduce) {
            m.shown = to;
            m.marker.setLngLat(to);
            return;
        }
        const began = performance.now();
        const step = (now) => {
            const k = Math.min(1, (now - began) / GLIDE_MS);
            m.shown = [from[0] + (to[0] - from[0]) * k, from[1] + (to[1] - from[1]) * k];
            m.marker.setLngLat(m.shown);
            m.frame = k < 1 ? requestAnimationFrame(step) : 0;
        };
        m.frame = requestAnimationFrame(step);
    }

    // ------------------------------------------------- Leaflet (the fallback)
    _initLeaflet() {
        if (!window.L || !this.mapRef.el) { return; }
        this._kind = "leaflet";
        this._map = window.L.map(this.mapRef.el, { zoomControl: true, attributionControl: true });
        window.L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
            maxZoom: 19, attribution: "&copy; OpenStreetMap",
        }).addTo(this._map);
        this._map.setView([25.2, 55.3], 11);
        this.state.mapReady = true;
    }
    _icon(html, cls, size) {
        return window.L.divIcon({ className: "", html: `<span class="sa_fm_mk ${cls}">${html}</span>`, iconSize: [size, size], iconAnchor: [size / 2, size / 2] });
    }
    _drawLeaflet() {
        const L = window.L;
        if (!L || !this._map) { return; }
        const map = this._map;
        const pts = [];
        const group = (name) => {
            if (this._layers[name]) { map.removeLayer(this._layers[name]); }
            this._layers[name] = L.layerGroup().addTo(map);
            return this._layers[name];
        };
        const shops = group("shops");
        for (const s of this.state.shops) {
            if (!s.latitude) { continue; }
            L.marker([s.latitude, s.longitude], { icon: this._icon("&#127978;", `shop${s.approximate ? " approx" : ""}`, 30), title: s.name })
                .bindTooltip(s.name, { direction: "top", offset: [0, -14] }).addTo(shops);
            pts.push([s.latitude, s.longitude]);
        }
        const waiting = group("waiting");
        for (const w of this.state.waiting) {
            if (!w.latitude) { continue; }
            L.marker([w.latitude, w.longitude], { icon: this._icon("!", `waiting${w.approximate ? " approx" : ""}`, 26) })
                .bindTooltip(`#${w.ref} waiting · ${w.customer}`, { direction: "top", offset: [0, -12] })
                .on("click", () => this.openJob(w.job_id)).addTo(waiting);
            pts.push([w.latitude, w.longitude]);
        }
        const riders = group("riders");
        const stops = group("stops");
        const run = group("run");
        const trail = group("trail");
        for (const r of this.state.riders) {
            if (r.state === "off" && !r.stops.length) { continue; }
            const sel = r.id === this.state.selected;
            if (r.latitude) {
                const m = L.marker([r.latitude, r.longitude], {
                    icon: this._icon(initials(r.name), `rider ${r.state}${sel ? " sel" : ""}`, 34), zIndexOffset: sel ? 1000 : 500,
                }).bindTooltip(`${r.name} · ${this.stateLabel(r)}`, { direction: "top", offset: [0, -16] })
                  .on("click", () => this.select(r));
                m.addTo(riders);
                pts.push([r.latitude, r.longitude]);
            }
            // the run: numbered stops, dashed line rider -> 1 -> 2 ...
            const line = r.latitude ? [[r.latitude, r.longitude]] : [];
            for (const s of r.stops) {
                if (!s.latitude) { continue; }
                L.marker([s.latitude, s.longitude], { icon: this._icon(String(s.stop_no), `stop${sel ? " sel" : ""}`, 24) })
                    .bindTooltip(`${s.stop_no} · #${s.ref} ${s.customer}${this.stopLine(s) ? " · " + this.stopLine(s) : ""}`, { direction: "top", offset: [0, -12] })
                    .on("click", () => this.openJob(s.job_id)).addTo(stops);
                line.push([s.latitude, s.longitude]);
                pts.push([s.latitude, s.longitude]);
            }
            if (line.length > 1 && (sel || !this.state.selected)) {
                L.polyline(line, { color: COLOR.run, weight: sel ? 4 : 2.5, opacity: sel ? 0.95 : 0.6, dashArray: "6 8" }).addTo(run);
            }
            if (sel && r.trail && r.trail.length > 1) {
                L.polyline(r.trail, { color: "#f7931e", weight: 3, opacity: 0.8 }).addTo(trail);
            }
        }
        if (!this._fitted && pts.length) {
            map.fitBounds(L.latLngBounds(pts).pad(0.2));
            this._fitted = true;
        }
    }
}

registry.category("actions").add("sales_automation_delivery.fleet_map", FleetMap);
