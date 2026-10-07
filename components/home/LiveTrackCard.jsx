"use client";
/* ==========================================================================
   369 Mart — Live tracking card   (inside /track/<id>, while the parcel moves)

   A real map of where the rider is, drawn from `GET /orders/<id>/track`
   (Odoo: mart369_whatsapp_bridge/controllers/order_track.py). The page polls
   it; this card only draws what it is given:

     rider dot   only when the server says `show_rider` (Express hides it
                 between stops on the newer delivery stack)
     home pin    the delivery address; shop pin when the shop has a location
     line        the server's road route when it sends one, otherwise a
                 dashed straight line, labelled approximate
     status      label + promised time, "Updated 8s ago", and "Signal lost"
                 once the rider's phone has gone quiet for two minutes

   The map follows the rider until the customer drags it; "Re-centre" puts it
   back. Map tiles come from mapProvider.js - OpenStreetMap until the shop's
   Google key exists.
   ========================================================================== */
import "leaflet/dist/leaflet.css";
import { useEffect, useRef, useState } from "react";
import { Icon } from "./shared";
import { fmtTime } from "./orderState";
import { TILES, loadLeaflet } from "./mapProvider";

const STALE_AFTER = 120;
const reduced = () => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
const point = (p) => (p && (p.lat || p.lng) ? [p.lat, p.lng] : null);

const SCOOTER = '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="6" cy="17" r="2.5"/><circle cx="18" cy="17" r="2.5"/><path d="M8.5 17h6.5l2-6h-4l-2 4M15 5h3l1 6"/></svg>';
const HOME = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 11 12 4l8 7v9H4z"/><path d="M10 20v-5h4v5"/></svg>';

const agoText = (s) => (s == null ? "" : s < 5 ? "Updated just now" : s < 60 ? `Updated ${s}s ago` : s < 3600 ? `Updated ${Math.floor(s / 60)} min ago` : "Updated over an hour ago");

export default function LiveTrackCard({ track, address }) {
  const box = useRef(null);
  const view = useRef(null); // { L, map, layers, fitted }
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
  const [follow, setFollow] = useState(true);

  const rider = track.show_rider ? point(track) : null;
  const home = point(track.dest) || point(address);
  const shop = point(track.shop);
  const route = Array.isArray(track.route) && track.route.length > 1
    ? track.route.map((p) => (Array.isArray(p) ? p : [p.lat, p.lng]))
    : null;

  /* "Updated Xs ago" counts on between polls: the server says how old the
     fix was when it answered, and the card adds the time since. */
  const got = useRef({ at: Date.now(), age: track.age });
  useEffect(() => { got.current = { at: Date.now(), age: track.age }; }, [track.age, track.fix_on]);
  const [, tick] = useState(0);
  useEffect(() => { const id = setInterval(() => tick((n) => n + 1), 1000); return () => clearInterval(id); }, []);
  const ago = rider && got.current.age != null ? got.current.age + Math.round((Date.now() - got.current.at) / 1000) : null;
  const stale = !!rider && (track.stale || (ago != null && ago > STALE_AFTER));

  /* The map itself, once. */
  useEffect(() => {
    let off = false;
    loadLeaflet().then((L) => {
      if (off || !box.current || view.current) return;
      const map = L.map(box.current, { zoomControl: false, scrollWheelZoom: false, attributionControl: true });
      map.attributionControl.setPrefix(false);
      L.tileLayer(TILES.url, TILES.options).addTo(map);
      L.control.zoom({ position: "bottomright" }).addTo(map);
      map.on("dragstart", () => setFollow(false));
      view.current = { L, map, layers: {}, fitted: false };
      setTimeout(() => map.invalidateSize(), 0);
      setReady(true);
    }).catch(() => { if (!off) setFailed(true); });
    return () => { off = true; view.current?.map.remove(); view.current = null; };
  }, []);

  /* Everything on it, every poll. */
  const key = JSON.stringify([rider, home, shop, route, stale]);
  useEffect(() => {
    const v = view.current;
    if (!ready || !v) return;
    const { L, map, layers } = v;
    const pin = (name, at, html, cls) => {
      if (!at) { layers[name]?.remove(); delete layers[name]; return; }
      if (layers[name]) layers[name].setLatLng(at);
      else layers[name] = L.marker(at, { keyboard: false, interactive: false, zIndexOffset: name === "rider" ? 1000 : 0, icon: L.divIcon({ className: "ot-lm " + cls, html, iconSize: [40, 40], iconAnchor: [20, 20] }) }).addTo(map);
      layers[name].getElement()?.classList.toggle("ot-lm-stale", name === "rider" && stale);
    };
    pin("shop", shop, "<b>369</b>", "ot-lm-shop");
    pin("home", home, HOME, "ot-lm-home");
    pin("rider", rider, SCOOTER, "ot-lm-rider");

    const line = route || [rider || shop, home].filter(Boolean);
    layers.line?.remove();
    layers.line = line.length > 1
      ? L.polyline(line, { color: "#0a78ab", weight: 4, opacity: 0.85, dashArray: route && !track.route_approx ? null : "2 9", lineCap: "round", interactive: false }).addTo(map)
      : null;

    /* Shop, rider and home all in view: the customer reads the whole trip
       at a glance, and a rider standing at the door does not zoom the map
       into one street with the shop off the edge. */
    const all = [rider, home, shop].filter(Boolean);
    if (!all.length) return;
    if (!v.fitted || follow) {
      if (all.length > 1) map.fitBounds(all, { padding: [56, 56], maxZoom: 16, animate: v.fitted && !reduced() });
      else map.setView(all[0], 15, { animate: v.fitted && !reduced() });
      v.fitted = true;
    }
  }, [ready, key, follow]); // eslint-disable-line

  /* The promised time, while it is still ahead; once it has passed, saying
     "Arriving by" a time already gone would be wrong, so it says late. */
  const moving = !!track.live && !track.ended;
  const due = track.eta ? Date.parse(track.eta) : NaN;
  const eta = track.ended ? ""
    : !Number.isNaN(due) ? (due > Date.now() ? `Arriving by ${fmtTime(due)}` : `Running late — was due by ${fmtTime(due)}`) : track.eta_text || "";
  /* The same map before the rider sets off and after the door, the way
     WhatsApp's tracking link shows it - only the words change. */
  const note = track.ended ? (track.state === "delivered" ? "Delivered to your door." : "")
    : !moving ? "Your rider shows here once they set off."
    : !track.show_rider ? "Your parcel is on its way. The rider shows here on the last stretch."
    : !rider ? "Waiting for the rider's location…" : "";

  if (failed || (!home && !rider && !shop)) return null;

  return (
    <div className={"ot-live" + (stale ? " ot-live-stale" : "")}>
      <div className="ot-live-stage">
        <div className="ot-live-map" ref={box} role="region" aria-label={`Live map. ${track.label}${eta ? ". " + eta : ""}`} />
        <span className="ot-live-pill">
          {stale ? <><Icon n="info" size={13} />Signal lost — showing last known spot</>
            : moving ? <><i className="ot-live-dot" />Live · {track.label}</> : track.label}
        </span>
        {!follow && (rider || home) && (
          <button className="ot-live-recentre" onClick={() => setFollow(true)}><Icon n="pin" size={14} />Re-centre</button>
        )}
        {moving && !route && (rider || shop) && home && <span className="ot-live-approx">Straight line · approximate</span>}
      </div>
      <div className="ot-live-bar">
        <span><b>{track.label}</b>{eta && <small>{eta}</small>}</span>
        <small className="ot-live-ago" aria-live="polite">{note || agoText(ago)}</small>
      </div>
    </div>
  );
}
