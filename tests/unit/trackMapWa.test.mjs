/* The WhatsApp tracking page moves the scooter with its own copy of the rules
 * (sales_automation_delivery/static/src/track_map.js), because an Odoo module
 * cannot import the website's riderPath.mjs. This checks that the two copies
 * give the same answers, so neither can drift without a test failing.
 */
import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import * as web from "../../components/home/riderPath.mjs";

const require = createRequire(import.meta.url);
const wa = require("../../odoo_modules/sales_automation/sales_automation_delivery/static/src/track_map.js");

const ROAD = [[10.35, 77.98], [10.352, 77.98], [10.352, 77.982]];
const HAIRPIN = [[10.35, 77.98], [10.36, 77.98], [10.36, 77.9802], [10.35, 77.9802]];

const MOVES = [
  ["across a corner", [10.351, 77.98], [10.352, 77.981], ROAD],
  ["along a straight piece", [10.3505, 77.98], [10.3515, 77.98], ROAD],
  ["a report beside the road", [10.3505, 77.98], [10.3515, 77.9803], ROAD],
  ["leaving the route", [10.351, 77.98], [10.351, 77.99], ROAD],
  ["coming back to the route", [10.351, 77.99], [10.3515, 77.98], ROAD],
  ["going backwards", [10.3515, 77.98], [10.3505, 77.98], ROAD],
  ["GPS wander", [10.351, 77.98], [10.35102, 77.98001], ROAD],
  ["a road doubling back", [10.3501, 77.98], [10.3501, 77.9802], HAIRPIN],
  ["no road line", [10.351, 77.98], [10.352, 77.981], null],
  ["a road line of one point", [10.351, 77.98], [10.352, 77.981], [[10.351, 77.98]]],
];

for (const [name, from, to, route] of MOVES) {
  test(`the same path: ${name}`, () => {
    const path = web.planMove(from, to, route);
    assert.deepEqual(wa.planMove(from, to, route), path);
    if (path) {
      for (const k of [0, 0.25, 0.5, 0.75, 1]) assert.deepEqual(wa.pointAt(path, k), web.pointAt(path, k));
    }
  });
}

test("the same starting place and direction", () => {
  for (const at of [[10.352, 77.9811], [10.351, 77.9803], [10.351, 77.99]]) {
    assert.deepEqual(wa.placeOnRoad(ROAD, at), web.placeOnRoad(ROAD, at));
  }
  assert.deepEqual(wa.placeOnRoad(null, ROAD[0]), web.placeOnRoad(null, ROAD[0]));
});

test("the same glide times", () => {
  const at = Date.parse("2026-11-06T10:00:00Z");
  for (const [last, fix, current] of [
    [at, at + 12000, undefined], [at, at + 1000, undefined], [at, at + 300000, undefined],
    [0, at, undefined], [at, at, 9000], [at, at - 5000, 9000], [at, NaN, 9000],
  ]) {
    assert.equal(wa.nextGlideMs(last, fix, current), web.nextGlideMs(last, fix, current));
  }
});

test("the same turns", () => {
  for (const [current, target, step] of [[350, 10, 5], [10, 350, 5], [355, 10, 40], [90, 90, 5], [0, 180, 30]]) {
    assert.equal(wa.turnToward(current, target, step), web.turnToward(current, target, step));
  }
});
