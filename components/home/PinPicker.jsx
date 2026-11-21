"use client";
/* ==========================================================================
   369 Mart — "Pick on map": the shopper puts the pin on their door.

   The pin stays in the middle and the map moves under it, the way delivery
   apps do it, so a thumb on a phone never has to grab a tiny marker. It opens
   on the address's own pin, else the typed pincode's area (the shop's postcode
   list, /pincode-spot), else the shopper's current location if they allow it.

   With a pin, the shop measures Quick or Express from the branch, and the
   address form can warn when the pincode and the pin are far apart. Same free
   map as order tracking (OpenFreeMap through MapLibre, no key); its credits
   stay on show.
   ========================================================================== */
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { FREE_MAP, loadMapLibre } from "./mapProvider";

const START_ZOOM = 15;
const AREA_ZOOM = 13;       // a pincode's area, before zooming to the door
const WIDE_ZOOM = 4;        // nothing known yet

/* `help` and `hereLabel` let the staff console say "branch" where the shop
   says "your door"; left out, the shopper's words stay as they were. */
export default function PinPicker({
  start, pincode, onPick, onCancel,
  help = <><b>Put the pin on your door.</b> Drag the map; the pin stays in the middle.</>,
  hereLabel = "Use where I am now",
}) {
  const box = useRef(null);
  const mapRef = useRef(null);
  const [state, setState] = useState("loading"); // loading | ready | failed
  const [note, setNote] = useState("");
  const [locating, setLocating] = useState(false);

  useEffect(() => {
    let off = false;
    let map = null;
    (async () => {
      /* Where to open: this address's pin, the pincode's area, or wide. */
      let center = start && (start.lat || start.lng) ? [start.lng, start.lat] : null;
      let zoom = START_ZOOM;
      if (!center && pincode) {
        const spot = await api(`/pincode-spot?pin=${encodeURIComponent(pincode)}`, { raw: true }).catch(() => null);
        if (spot?.known) {
          center = [spot.lng, spot.lat];
          zoom = AREA_ZOOM;
          setNote(`Showing ${spot.place || `postcode ${pincode}`}. Zoom in and move the map to your door.`);
        }
      }
      if (!center) { center = [78.9629, 22.5937]; zoom = WIDE_ZOOM; }
      const ml = await loadMapLibre().catch(() => null);
      if (off || !box.current) return;
      if (!ml) { setState("failed"); return; }
      try {
        map = new ml.Map({
          container: box.current, style: FREE_MAP.style, center, zoom,
          maxZoom: 19, dragRotate: false, pitchWithRotate: false, touchPitch: false,
          attributionControl: { compact: false },
        });
      } catch {
        setState("failed");
        return;
      }
      map.touchZoomRotate.disableRotation();
      map.addControl(new ml.NavigationControl({ showCompass: false }), "bottom-right");
      map.on("error", (e) => { if (!mapRef.current && !e?.sourceId) setState("failed"); });
      map.once("load", () => { if (!off) { mapRef.current = map; setState("ready"); } });
    })();
    return () => { off = true; mapRef.current = null; try { map?.remove(); } catch { /* never started */ } };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const here = () => {
    if (!navigator.geolocation) { setNote("Location isn't available in this browser. Move the map instead."); return; }
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => {
        setLocating(false);
        mapRef.current?.flyTo({ center: [coords.longitude, coords.latitude], zoom: 17 });
        setNote("Moved to where you are now. Check the pin is on the right door.");
      },
      () => { setLocating(false); setNote("We couldn't get your location. Move the map to your door instead."); },
      { enableHighAccuracy: true, timeout: 8000 },
    );
  };

  const confirm = () => {
    const c = mapRef.current?.getCenter();
    if (c) onPick({ lat: Number(c.lat.toFixed(6)), lng: Number(c.lng.toFixed(6)) });
  };

  return (
    <div className="pp-root">
      <p className="pp-help">
        {help}
        {note && <span> {note}</span>}
      </p>
      <div className="pp-map">
        <div ref={box} className="pp-canvas" />
        {state === "ready" && (
          <span className="pp-pin" aria-hidden="true">
            <svg viewBox="0 0 24 24"><path d="M12 22s-7-6.2-7-12a7 7 0 0 1 14 0c0 5.8-7 12-7 12z" /><circle cx="12" cy="10" r="2.6" /></svg>
          </span>
        )}
        {state === "loading" && <span className="pp-msg">Loading the map…</span>}
        {state === "failed" && (
          <span className="pp-msg">The map couldn't load here. Close this and use your current location instead.</span>
        )}
      </div>
      <div className="pp-actions">
        <button type="button" className="co-ghost" onClick={here} disabled={state !== "ready" || locating}>
          {locating ? "Finding you…" : hereLabel}
        </button>
        <span className="pp-gap" />
        <button type="button" className="co-ghost" onClick={onCancel}>Cancel</button>
        <button type="button" className="co-primary" onClick={confirm} disabled={state !== "ready"}>Use this spot</button>
      </div>
    </div>
  );
}
