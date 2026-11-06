/* ==========================================================================
   369 Mart — which map the live tracking card draws on.

   OpenFreeMap's Liberty style through MapLibre (LiveMapGL.jsx): free, no key,
   and allowed for commercial use. Its credits (OpenFreeMap, OpenMapTiles,
   OpenStreetMap) come with the map and stay on show.

   The WhatsApp "Follow it live" page draws the same map and moves the scooter
   by the same rules (sales_automation_delivery's static/src/track_map.js).

   The backup is OpenStreetMap through Leaflet (LiveMapLeaflet.jsx). It only
   draws when the new map cannot start: a phone with no WebGL, or the style not
   arriving. OSM's tile policy asks for the attribution line, so it is shown
   there too.

   Google Maps is the shop's choice once its key exists. When
   NEXT_PUBLIC_GOOGLE_MAPS_KEY is set, load Google here and hand LiveTrackCard
   a map of its own beside these two. Until then the key is not read anywhere
   else.
   ========================================================================== */

export const GOOGLE_MAPS_KEY = process.env.NEXT_PUBLIC_GOOGLE_MAPS_KEY || "";

export const FREE_MAP = {
  style: "https://tiles.openfreemap.org/styles/liberty",
  /* The rider's top view, nose pointing up, as the rider app draws it. */
  rider: { url: "/images/rider-top.png", height: 256, drawnHeight: 52 },
};

/* The pins both maps draw. */
export const PIN = {
  scooter: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="6" cy="17" r="2.5"/><circle cx="18" cy="17" r="2.5"/><path d="M8.5 17h6.5l2-6h-4l-2 4M15 5h3l1 6"/></svg>',
  home: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 11 12 4l8 7v9H4z"/><path d="M10 20v-5h4v5"/></svg>',
  shop: "<b>369</b>",
};

/* MapLibre also touches `window` when it is imported. */
let loadingGL = null;
export function loadMapLibre() {
  if (!loadingGL) loadingGL = import("maplibre-gl").then((m) => m.default || m);
  return loadingGL;
}

export const TILES = {
  url: "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
  options: {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>',
  },
};

/* Leaflet touches `window` the moment it is imported, so it is only ever
   loaded in the browser, the first time a live card mounts. */
let loading = null;
export function loadLeaflet() {
  if (!loading) loading = import("leaflet").then((m) => m.default || m);
  return loading;
}
