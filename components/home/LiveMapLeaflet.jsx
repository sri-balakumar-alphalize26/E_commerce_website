"use client";
/* ==========================================================================
   369 Mart — the live map's backup: OpenStreetMap through Leaflet.

   LiveMapGL.jsx is the map customers normally see. This one draws only when
   that cannot start (see LiveTrackCard), so an order can still be followed.
   The rider is a round dot here, moved to each new report.
   ========================================================================== */
import "leaflet/dist/leaflet.css";
import { useEffect, useRef, useState } from "react";
import { PIN, TILES, loadLeaflet } from "./mapProvider";

const reduced = () => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

export default function LiveMapLeaflet({ rider, home, shop, route, approx, stale, follow, label, onDrag, onFail }) {
  const box = useRef(null);
  const view = useRef(null); // { L, map, layers, fitted }
  const [ready, setReady] = useState(false);

  /* The map itself, once. */
  useEffect(() => {
    let off = false;
    loadLeaflet().then((L) => {
      if (off || !box.current || view.current) return;
      const map = L.map(box.current, { zoomControl: false, scrollWheelZoom: false, attributionControl: true });
      map.attributionControl.setPrefix(false);
      L.tileLayer(TILES.url, TILES.options).addTo(map);
      L.control.zoom({ position: "bottomright" }).addTo(map);
      map.on("dragstart", () => onDrag());
      view.current = { L, map, layers: {}, fitted: false };
      setTimeout(() => map.invalidateSize(), 0);
      setReady(true);
    }).catch(() => { if (!off) onFail(); });
    return () => { off = true; view.current?.map.remove(); view.current = null; };
  }, []); // eslint-disable-line

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
    pin("shop", shop, PIN.shop, "ot-lm-shop");
    pin("home", home, PIN.home, "ot-lm-home");
    pin("rider", rider, PIN.scooter, "ot-lm-rider");

    const line = route || [rider || shop, home].filter(Boolean);
    layers.line?.remove();
    layers.line = line.length > 1
      ? L.polyline(line, { color: "#0a78ab", weight: 4, opacity: 0.85, dashArray: route && !approx ? null : "2 9", lineCap: "round", interactive: false }).addTo(map)
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

  return <div className="ot-live-map" ref={box} role="region" aria-label={label} />;
}
