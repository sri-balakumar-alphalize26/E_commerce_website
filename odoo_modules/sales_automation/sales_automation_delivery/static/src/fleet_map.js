/** @odoo-module **/

/**
 * Delivery > Fleet > Live Map: every rider on one map (free, on a run, no
 * signal), each run's stops in order with minutes, a 30-minute trail for the
 * rider you tap, the shops and the orders still waiting for a rider. The
 * Shop Queue opens the same screen filtered to one shop.
 *
 * Leaflet + OpenStreetMap, the same map the customer's page draws on.
 */

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { loadCSS, loadJS } from "@web/core/assets";
import { Component, onMounted, onWillStart, onWillUnmount, useState, useRef } from "@odoo/owl";

const LEAFLET_JS = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";
const LEAFLET_CSS = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";
const COLOR = { free: "#1a7f3c", run: "#0a78ab", no_signal: "#8a96a0", off: "#c9d1d8", sos: "#b42318" };

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
        this._fitted = false;

        onWillStart(async () => {
            try {
                await loadCSS(LEAFLET_CSS);
                await loadJS(LEAFLET_JS);
            } catch (e) {
                this.state.error = "The map library could not be loaded (no internet?). The list still works.";
            }
            await this.refresh();
        });
        onMounted(() => {
            this._initMap();
            this._draw();
            this._timer = setInterval(() => this.refresh().catch(() => {}), 15000);
            this._ticker = setInterval(() => { this.state.tick += 1; }, 1000);
        });
        onWillUnmount(() => {
            clearInterval(this._timer);
            clearInterval(this._ticker);
            if (this._map) { this._map.remove(); this._map = null; }
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
        if (this._map) { this._draw(); }
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

    // ---------------------------------------------------------------- actions
    select(r) {
        this.state.selected = this.state.selected === r.id ? 0 : r.id;
        this._draw();
        if (this.state.selected && this._map && r.latitude) {
            this._map.panTo([r.latitude, r.longitude], { animate: true });
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

    // ---------------------------------------------------------------- map
    _initMap() {
        if (!window.L || !this.mapRef.el) { return; }
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
    _draw() {
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
            L.marker([s.latitude, s.longitude], { icon: this._icon("&#127978;", "shop", 30), title: s.name })
                .bindTooltip(s.name, { direction: "top", offset: [0, -14] }).addTo(shops);
            pts.push([s.latitude, s.longitude]);
        }
        const waiting = group("waiting");
        for (const w of this.state.waiting) {
            if (!w.latitude) { continue; }
            L.marker([w.latitude, w.longitude], { icon: this._icon("!", "waiting", 26) })
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
                const initials = (r.name || "?").split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase();
                const m = L.marker([r.latitude, r.longitude], {
                    icon: this._icon(initials, `rider ${r.state}${sel ? " sel" : ""}`, 34), zIndexOffset: sel ? 1000 : 500,
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
