/* ==========================================================================
   369 Mart — which map the live tracking card draws on.

   OpenStreetMap through Leaflet for now: free, no key, and the same tiles the
   WhatsApp "Follow it live" page uses (sales_automation_delivery's
   delivery_track_templates.xml). OSM's tile policy asks for the attribution
   line, so it is shown.

   Google Maps is the shop's choice once its key exists. Switching is this
   file only: when NEXT_PUBLIC_GOOGLE_MAPS_KEY is set, load Google here and
   hand LiveTrackCard the same three things (a map, a marker, a line). Until
   then the key is not read anywhere else, and nothing in the card cares
   which map it is.
   ========================================================================== */

export const GOOGLE_MAPS_KEY = process.env.NEXT_PUBLIC_GOOGLE_MAPS_KEY || "";

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
