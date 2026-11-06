/* ==========================================================================
   369 Mart — how the scooter moves between two reports from the rider's phone.

   The phone reports about every 20 seconds. Drawn as they arrive, the rider
   would jump; this works out the path to glide along instead. No map code in
   here, so it can be tested on its own: tests/unit/riderPath.test.mjs.

   Points are [lat, lng], the way LiveTrackCard holds them.
   ========================================================================== */

/* Near the road line counts as on it: a phone's GPS wanders about this much. */
export const ON_ROAD_METRES = 60;
/* Less movement than this is the GPS wandering, not the rider moving. */
export const JITTER_METRES = 5;
/* The same limits as the WhatsApp tracking page's glide. */
export const GLIDE_MIN_MS = 3000;
export const GLIDE_MAX_MS = 20000;
export const GLIDE_DEFAULT_MS = 6000;
/* How fast the scooter turns, so a corner in the line is not a sudden flip. */
export const TURN_DEGREES_PER_SECOND = 180;

const EARTH = 6371000;
const rad = (d) => (d * Math.PI) / 180;
const deg = (r) => (r * 180) / Math.PI;

export function metres(a, b) {
  const x = rad(b[1] - a[1]) * Math.cos(rad((a[0] + b[0]) / 2));
  const y = rad(b[0] - a[0]);
  return Math.hypot(x, y) * EARTH;
}

/* Degrees clockwise from north: what the map's icon-rotate wants. */
export function bearing(a, b) {
  const y = Math.sin(rad(b[1] - a[1])) * Math.cos(rad(b[0]));
  const x = Math.cos(rad(a[0])) * Math.sin(rad(b[0]))
    - Math.sin(rad(a[0])) * Math.cos(rad(b[0])) * Math.cos(rad(b[1] - a[1]));
  return (deg(Math.atan2(y, x)) + 360) % 360;
}

/* The nearest spot on the line: where it is, how far from `at`, how far along
   the line it falls, and which piece of the line it is on. */
export function locate(route, at) {
  const scale = Math.cos(rad(at[0]));
  let best = null;
  let walked = 0;
  for (let i = 0; i < route.length - 1; i += 1) {
    const a = route[i];
    const b = route[i + 1];
    const piece = metres(a, b);
    const dx = (b[1] - a[1]) * scale;
    const dy = b[0] - a[0];
    const across = dx * dx + dy * dy;
    const t = across
      ? Math.max(0, Math.min(1, (((at[1] - a[1]) * scale) * dx + (at[0] - a[0]) * dy) / across))
      : 0;
    const point = [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
    const away = metres(point, at);
    if (!best || away < best.away) best = { point, away, along: walked + piece * t, piece: i };
    walked += piece;
  }
  return best;
}

const usable = (route) => Array.isArray(route) && route.length > 1;

/* Where to draw a rider seen for the first time, and which way they face. */
export function placeOnRoad(route, at) {
  if (!usable(route)) return { at, bearing: 0 };
  const spot = locate(route, at);
  if (spot.away > ON_ROAD_METRES) return { at, bearing: 0 };
  return { at: spot.point, bearing: bearing(route[spot.piece], route[spot.piece + 1]) };
}

/* The path from where the scooter is drawn to the new report, or null when it
   has not really moved. Along the road when it is on it and going forward;
   straight when it has left the line, or turned back along it. */
export function planMove(from, to, route) {
  let target = to;
  let points = null;
  if (usable(route)) {
    const a = locate(route, from);
    const b = locate(route, to);
    if (b.away <= ON_ROAD_METRES) target = b.point;
    if (a.away <= ON_ROAD_METRES && b.away <= ON_ROAD_METRES && b.along > a.along) {
      const road = [from, a.point, ...route.slice(a.piece + 1, b.piece + 1), b.point];
      /* A road that doubles back past itself can match the far stretch: the
         rider did not ride all that way in one report. */
      if (pathLength(road) <= 4 * metres(from, to) + 200) points = road;
    }
  }
  if (metres(from, target) < JITTER_METRES) return null;
  return tidy(points || [from, target]);
}

function pathLength(points) {
  let total = 0;
  for (let i = 0; i < points.length - 1; i += 1) total += metres(points[i], points[i + 1]);
  return total;
}

function tidy(points) {
  const out = [points[0]];
  for (const p of points.slice(1)) if (metres(out[out.length - 1], p) > 0.01) out.push(p);
  return out.length > 1 ? out : [points[0], points[points.length - 1]];
}

/* Where along the path the scooter is at k (0 to 1), and which way it faces. */
export function pointAt(path, k) {
  const total = pathLength(path);
  let left = Math.max(0, Math.min(1, k)) * total;
  for (let i = 0; i < path.length - 1; i += 1) {
    const piece = metres(path[i], path[i + 1]);
    if (left <= piece || i === path.length - 2) {
      const t = piece ? Math.min(1, left / piece) : 1;
      return {
        at: [path[i][0] + (path[i + 1][0] - path[i][0]) * t, path[i][1] + (path[i + 1][1] - path[i][1]) * t],
        bearing: bearing(path[i], path[i + 1]),
      };
    }
    left -= piece;
  }
  return { at: path[path.length - 1], bearing: 0 };
}

/* How long to glide: the gap between the phone's last two reports, within the
   limits. A report no newer than the last keeps the time already in use. */
export function nextGlideMs(lastFixMs, fixMs, current = GLIDE_DEFAULT_MS) {
  if (!lastFixMs || !fixMs || !(fixMs > lastFixMs)) return current;
  return Math.max(GLIDE_MIN_MS, Math.min(GLIDE_MAX_MS, fixMs - lastFixMs));
}

/* One step of a turn, the short way round (350° to 10° passes through north). */
export function turnToward(current, target, maxStep) {
  const gap = ((target - current + 540) % 360) - 180;
  if (Math.abs(gap) <= maxStep) return (target + 360) % 360;
  return (current + Math.sign(gap) * maxStep + 360) % 360;
}
