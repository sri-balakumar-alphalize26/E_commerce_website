/* How the scooter moves on the order page's live map. No browser and no map:
 *
 *   npm run test:unit
 *
 * The road below runs north, then turns east: an L with its corner at CORNER.
 * 0.001 of a degree is about 111 m north-south, and about 109 m east-west at
 * this latitude.
 */
import test from "node:test";
import assert from "node:assert/strict";
import {
  bearing, locate, metres, nextGlideMs, placeOnRoad, planMove, pointAt, turnToward,
  GLIDE_DEFAULT_MS, GLIDE_MAX_MS, GLIDE_MIN_MS,
} from "../../components/home/riderPath.mjs";

const START = [10.35, 77.98];
const CORNER = [10.352, 77.98];
const END = [10.352, 77.982];
const ROAD = [START, CORNER, END];

const near = (a, b, within = 1) => assert.ok(metres(a, b) <= within, `${a} is ${metres(a, b)} m from ${b}`);

test("bearing is clockwise from north", () => {
  assert.ok(Math.abs(bearing(START, CORNER)) < 0.01);
  assert.ok(Math.abs(bearing(CORNER, END) - 90) < 0.1);
  assert.ok(Math.abs(bearing(CORNER, START) - 180) < 0.01);
});

test("locate finds the nearest spot and how far along the road it is", () => {
  const spot = locate(ROAD, [10.351, 77.9802]);
  near(spot.point, [10.351, 77.98]);
  assert.equal(spot.piece, 0);
  assert.ok(Math.abs(spot.along - metres(START, [10.351, 77.98])) < 1);
});

test("a move across a corner follows the road, not the straight line", () => {
  const from = [10.351, 77.98];
  const to = [10.352, 77.981];
  const path = planMove(from, to, ROAD);
  assert.ok(path.some((p) => metres(p, CORNER) < 1), "the path goes through the corner");
  /* Halfway it is at the corner. A straight line would cut about 77 m inside. */
  near(pointAt(path, 0.5).at, CORNER, 2);
});

test("the scooter faces the road: north before the corner, east after it", () => {
  const path = planMove([10.351, 77.98], [10.352, 77.981], ROAD);
  assert.ok(Math.abs(pointAt(path, 0.25).bearing) < 1);
  assert.ok(Math.abs(pointAt(path, 0.75).bearing - 90) < 1);
});

test("the glide moves steadily from the old spot to the new one", () => {
  const from = [10.3505, 77.98];
  const to = [10.3515, 77.98];
  const path = planMove(from, to, ROAD);
  near(pointAt(path, 0).at, from);
  near(pointAt(path, 1).at, to);
  let last = -1;
  for (let k = 0; k <= 1; k += 0.1) {
    const gone = metres(from, pointAt(path, k).at);
    assert.ok(gone > last, "every step is further along");
    last = gone;
  }
});

test("a report beside the road is drawn on the road", () => {
  const beside = [10.3515, 77.9803]; // about 33 m east of it
  const path = planMove([10.3505, 77.98], beside, ROAD);
  near(path[path.length - 1], [10.3515, 77.98]);
});

test("leaving the route goes straight to the report", () => {
  const away = [10.351, 77.99]; // about 1 km east of the road
  assert.deepEqual(planMove([10.351, 77.98], away, ROAD), [[10.351, 77.98], away]);
});

test("coming back to the route from far away goes straight too", () => {
  const away = [10.351, 77.99];
  const path = planMove(away, [10.3515, 77.98], ROAD);
  assert.equal(path.length, 2);
  near(path[1], [10.3515, 77.98]);
});

test("going back along the road does not ride forward round it", () => {
  const path = planMove([10.3515, 77.98], [10.3505, 77.98], ROAD);
  assert.equal(path.length, 2);
  assert.ok(Math.abs(pointAt(path, 0.5).bearing - 180) < 1);
});

test("GPS wander while standing still is not a move", () => {
  assert.equal(planMove([10.351, 77.98], [10.35102, 77.98001], ROAD), null);
  assert.equal(planMove([10.351, 77.98], [10.35102, 77.98001], null), null);
});

test("standing still beside the road stays put, report after report", () => {
  const raw = [10.351, 77.9803];
  const { at } = placeOnRoad(ROAD, raw);
  assert.equal(planMove(at, raw, ROAD), null);
});

test("a road doubling back on itself does not send the scooter the long way", () => {
  const hairpin = [[10.35, 77.98], [10.36, 77.98], [10.36, 77.9802], [10.35, 77.9802]];
  const path = planMove([10.3501, 77.98], [10.3501, 77.9802], hairpin);
  assert.equal(path.length, 2, "not 2 km round the bend for a 20 m move");
});

test("with no road line it moves in a straight line", () => {
  const from = [10.351, 77.98];
  const to = [10.352, 77.981];
  assert.deepEqual(planMove(from, to, null), [from, to]);
  assert.deepEqual(planMove(from, to, [from]), [from, to]);
});

test("a rider seen for the first time starts on the road, facing along it", () => {
  const onIt = placeOnRoad(ROAD, [10.352, 77.9811]);
  near(onIt.at, [10.352, 77.9811]);
  assert.ok(Math.abs(onIt.bearing - 90) < 1);
  const off = placeOnRoad(ROAD, [10.351, 77.99]);
  assert.deepEqual(off.at, [10.351, 77.99]);
  assert.equal(off.bearing, 0);
  assert.equal(placeOnRoad(null, START).at, START);
});

test("the glide lasts as long as the gap between reports, within limits", () => {
  const at = Date.parse("2026-11-06T10:00:00Z");
  assert.equal(nextGlideMs(at, at + 12000), 12000);
  assert.equal(nextGlideMs(at, at + 1000), GLIDE_MIN_MS);
  assert.equal(nextGlideMs(at, at + 300000), GLIDE_MAX_MS);
});

test("with no newer report the glide time stays what it was", () => {
  const at = Date.parse("2026-11-06T10:00:00Z");
  assert.equal(nextGlideMs(0, at), GLIDE_DEFAULT_MS);
  assert.equal(nextGlideMs(at, at, 9000), 9000);
  assert.equal(nextGlideMs(at, at - 5000, 9000), 9000);
  assert.equal(nextGlideMs(at, NaN, 9000), 9000);
});

test("turning takes the short way round, past north", () => {
  assert.equal(turnToward(350, 10, 5), 355);
  assert.equal(turnToward(10, 350, 5), 5);
  assert.equal(turnToward(355, 10, 40), 10);
  assert.equal(turnToward(90, 90, 5), 90);
});
