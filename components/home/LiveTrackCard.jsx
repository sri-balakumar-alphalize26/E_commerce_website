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
   back. The map is LiveMapGL.jsx (OpenFreeMap, with the scooter gliding along
   the road); LiveMapLeaflet.jsx is the backup if that cannot start. This card
   holds what is the same on both: the words and the buttons over the map.
   ========================================================================== */
import { useEffect, useRef, useState } from "react";
import { Icon } from "./shared";
import { fmtTime } from "./orderState";
import LiveMapGL from "./LiveMapGL";
import LiveMapLeaflet from "./LiveMapLeaflet";

const STALE_AFTER = 120;
const point = (p) => (p && (p.lat || p.lng) ? [p.lat, p.lng] : null);

const agoText = (s) => (s == null ? "" : s < 5 ? "Updated just now" : s < 60 ? `Updated ${s}s ago` : s < 3600 ? `Updated ${Math.floor(s / 60)} min ago` : "Updated over an hour ago");

/* Once the new map could not start on this device, later cards on the page
   go straight to the backup instead of waiting for it again. */
let glBroken = false;

export default function LiveTrackCard({ track, address }) {
  const [useBackup, setUseBackup] = useState(glBroken);
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

  const mapProps = {
    rider, home, shop, route, stale, follow,
    approx: !!track.route_approx,
    label: `Live map. ${track.label}${eta ? ". " + eta : ""}`,
    onDrag: () => setFollow(false),
  };
  /* The server's route when the road service did not answer: only the two
     ends, joined straight. Said out loud, the same as having no route. */
  const straight = !route || (route.length <= 2 && !!track.route_approx);

  return (
    <div className={"ot-live" + (stale ? " ot-live-stale" : "")}>
      <div className="ot-live-stage">
        {useBackup
          ? <LiveMapLeaflet {...mapProps} onFail={() => setFailed(true)} />
          : <LiveMapGL {...mapProps} fixOn={track.fix_on} onFail={() => { glBroken = true; setUseBackup(true); }} />}
        <span className="ot-live-pill">
          {stale ? <><Icon n="info" size={13} />Signal lost — showing last known spot</>
            : moving ? <><i className="ot-live-dot" />Live · {track.label}</> : track.label}
        </span>
        {!follow && (rider || home) && (
          <button className="ot-live-recentre" onClick={() => setFollow(true)}><Icon n="pin" size={14} />Re-centre</button>
        )}
        {moving && straight && (rider || shop) && home && <span className="ot-live-approx">Straight line · approximate</span>}
      </div>
      <div className="ot-live-bar">
        <span><b>{track.label}</b>{eta && <small>{eta}</small>}</span>
        <small className="ot-live-ago" aria-live="polite">{note || agoText(ago)}</small>
      </div>
    </div>
  );
}
