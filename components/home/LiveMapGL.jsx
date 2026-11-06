"use client";
/* ==========================================================================
   369 Mart — the live map: OpenFreeMap's Liberty style through MapLibre.

   The rider is their top-view scooter, drawn by the map itself so it can turn
   with the road. The phone reports about every 20 seconds, so the scooter
   glides from one report to the next along the path riderPath.mjs works out.

   If the map cannot start (no WebGL, the style not arriving) onFail() hands
   over to the backup, LiveMapLeaflet.jsx. A tile or two failing once it is
   running does not: the map just has a gap until they load.
   ========================================================================== */
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef, useState } from "react";
import { FREE_MAP, PIN, loadMapLibre } from "./mapProvider";
import { TURN_DEGREES_PER_SECOND, nextGlideMs, placeOnRoad, planMove, pointAt, turnToward } from "./riderPath.mjs";

const STYLE_WAIT_MS = 8000;
/* MapLibre's zoom numbers run one lower than Leaflet's for the same view. */
const MAX_ZOOM = 15;
const ONE_POINT_ZOOM = 14;
const LINE_DASH = [0.5, 2.25];
const NOTHING = { type: "FeatureCollection", features: [] };

const reduced = () => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
const lngLat = (p) => [p[1], p[0]];
const lineData = (points) => (points.length > 1
  ? { type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: points.map(lngLat) } }
  : NOTHING);
const riderData = (at, heading) => ({ type: "Feature", properties: { heading }, geometry: { type: "Point", coordinates: lngLat(at) } });

export default function LiveMapGL({ rider, home, shop, route, approx, stale, fixOn, follow, label, onDrag, onFail }) {
  const box = useRef(null);
  const view = useRef(null); // { ml, map, pins, fitted }
  const [ready, setReady] = useState(false);
  /* Where the scooter is drawn right now, and the glide it is on. */
  const motion = useRef({ at: null, heading: 0, target: 0, fixMs: 0, glideMs: undefined, frame: 0 });

  /* The map itself, once. */
  useEffect(() => {
    let off = false;
    let timer = null;
    let map = null;
    const give_up = () => {
      if (off) return;
      off = true;
      clearTimeout(timer);
      view.current = null;
      try { map?.remove(); } catch { /* it never got going */ }
      onFail();
    };
    loadMapLibre().then((ml) => {
      if (off || !box.current) return;
      const first = rider || home || shop;
      map = new ml.Map({
        container: box.current,
        style: FREE_MAP.style,
        center: first ? lngLat(first) : [0, 0],
        zoom: ONE_POINT_ZOOM,
        maxZoom: 19,
        scrollZoom: false,
        dragRotate: false,
        pitchWithRotate: false,
        touchPitch: false,
        /* The credits stay written out, on phones too: OpenStreetMap asks for it. */
        attributionControl: { compact: false },
      });
      map.touchZoomRotate.disableRotation();
      map.keyboard.disableRotation();
      map.addControl(new ml.NavigationControl({ showCompass: false }), "bottom-right");
      map.on("dragstart", () => onDrag());
      map.on("error", (e) => { if (!view.current && !e?.sourceId) give_up(); });
      timer = setTimeout(give_up, STYLE_WAIT_MS);

      map.once("styledata", async () => {
        try {
          const picture = await map.loadImage(FREE_MAP.rider.url);
          if (off) return;
          map.addImage("ot-rider", picture.data);
          /* Under the street names; the scooter goes over everything. */
          const firstLabel = map.getStyle().layers.find((l) => l.type === "symbol")?.id;
          map.addSource("ot-line", { type: "geojson", data: NOTHING });
          map.addSource("ot-rider", { type: "geojson", data: NOTHING });
          map.addLayer({
            id: "ot-line", type: "line", source: "ot-line",
            layout: { "line-cap": "round", "line-join": "round" },
            paint: { "line-color": "#0a78ab", "line-width": 4, "line-opacity": 0.85 },
          }, firstLabel);
          map.addLayer({
            id: "ot-rider", type: "symbol", source: "ot-rider",
            layout: {
              "icon-image": "ot-rider",
              "icon-size": FREE_MAP.rider.drawnHeight / FREE_MAP.rider.height,
              "icon-rotate": ["get", "heading"],
              "icon-rotation-alignment": "map",
              "icon-allow-overlap": true,
              "icon-ignore-placement": true,
            },
          });
          clearTimeout(timer);
          view.current = { ml, map, pins: {}, fitted: false };
          map.resize();
          setReady(true);
        } catch {
          give_up();
        }
      });
    }).catch(give_up);
    const m = motion.current;
    return () => {
      off = true;
      clearTimeout(timer);
      cancelAnimationFrame(m.frame);
      m.at = null;
      view.current = null;
      setReady(false);
      try { map?.remove(); } catch { /* already gone */ }
    };
  }, []); // eslint-disable-line

  /* The shop and home pins. */
  const pinsKey = JSON.stringify([home, shop]);
  useEffect(() => {
    const v = view.current;
    if (!ready || !v) return;
    const pin = (name, at, html, cls) => {
      if (!at) { v.pins[name]?.remove(); delete v.pins[name]; return; }
      if (v.pins[name]) { v.pins[name].setLngLat(lngLat(at)); return; }
      const el = document.createElement("div");
      el.className = "ot-lm " + cls;
      el.innerHTML = html;
      v.pins[name] = new v.ml.Marker({ element: el, anchor: "center" }).setLngLat(lngLat(at)).addTo(v.map);
    };
    pin("shop", shop, PIN.shop, "ot-lm-shop");
    pin("home", home, PIN.home, "ot-lm-home");
  }, [ready, pinsKey]); // eslint-disable-line

  /* The line: the road when the server sends it, else dashed and straight. */
  const lineKey = JSON.stringify([route, approx, route ? null : [rider || shop, home]]);
  useEffect(() => {
    const v = view.current;
    if (!ready || !v) return;
    v.map.getSource("ot-line")?.setData(lineData(route || [rider || shop, home].filter(Boolean)));
    v.map.setPaintProperty("ot-line", "line-dasharray", route && !approx ? null : LINE_DASH);
  }, [ready, lineKey]); // eslint-disable-line

  /* The signal is lost: the scooter fades, as the old dot went grey. */
  useEffect(() => {
    const v = view.current;
    if (ready && v) v.map.setPaintProperty("ot-rider", "icon-opacity", stale ? 0.45 : 1);
  }, [ready, stale]);

  /* The scooter, on each new report. */
  const riderKey = JSON.stringify([rider, fixOn]);
  useEffect(() => {
    const v = view.current;
    if (!ready || !v) return;
    const source = v.map.getSource("ot-rider");
    const m = motion.current;
    if (!rider) {
      cancelAnimationFrame(m.frame);
      m.at = null;
      m.fixMs = 0;
      source?.setData(NOTHING);
      return;
    }
    const fixMs = Date.parse(fixOn) || 0;
    m.glideMs = nextGlideMs(m.fixMs, fixMs, m.glideMs);
    if (fixMs) m.fixMs = fixMs;
    const draw = () => source?.setData(riderData(m.at, m.heading));

    if (!m.at) {
      const first = placeOnRoad(route, rider);
      m.at = first.at;
      m.heading = first.bearing;
      draw();
      return;
    }
    const path = planMove(m.at, rider, route);
    if (!path) return; // it has not really moved; it keeps facing the same way
    cancelAnimationFrame(m.frame);
    if (reduced() || document.hidden) {
      const end = pointAt(path, 1);
      m.at = end.at;
      m.heading = end.bearing;
      draw();
      return;
    }
    const start = performance.now();
    const ms = m.glideMs;
    let last = start;
    const step = (now) => {
      const k = Math.min(1, (now - start) / ms);
      const here = pointAt(path, k);
      m.at = here.at;
      m.heading = turnToward(m.heading, here.bearing, (TURN_DEGREES_PER_SECOND * Math.max(0, now - last)) / 1000);
      last = now;
      draw();
      /* Past the end only to finish a turn still under way. */
      const turning = Math.abs(((here.bearing - m.heading + 540) % 360) - 180) > 0.5;
      if (k < 1 || turning) m.frame = requestAnimationFrame(step);
    };
    m.frame = requestAnimationFrame(step);
  }, [ready, riderKey]); // eslint-disable-line

  /* Shop, rider and home all in view: the customer reads the whole trip at a
     glance, and a rider standing at the door does not zoom the map into one
     street with the shop off the edge. */
  const frameKey = JSON.stringify([rider, home, shop]);
  useEffect(() => {
    const v = view.current;
    if (!ready || !v) return;
    const all = [rider, home, shop].filter(Boolean);
    if (!all.length) return;
    if (!v.fitted || follow) {
      const animate = v.fitted && !reduced();
      if (all.length > 1) {
        const bounds = all.reduce((b, p) => b.extend(lngLat(p)), new v.ml.LngLatBounds(lngLat(all[0]), lngLat(all[0])));
        v.map.fitBounds(bounds, { padding: 56, maxZoom: MAX_ZOOM, animate });
      } else {
        v.map.easeTo({ center: lngLat(all[0]), zoom: ONE_POINT_ZOOM, animate });
      }
      v.fitted = true;
    }
  }, [ready, frameKey, follow]); // eslint-disable-line

  return <div className="ot-live-map" ref={box} role="region" aria-label={label} />;
}
