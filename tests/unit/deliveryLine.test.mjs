/* The delivery label on product cards and the product page. No browser:
 *
 *   npm run test:unit
 *
 * 13 Nov 2026: a product with nothing in stock showed "Quick · 10–20 mins".
 */
import test from "node:test";
import assert from "node:assert/strict";
import { deliveryLine, isOut, modeOf } from "../../lib/deliveryLine.mjs";

test("in stock, no answer from the shop yet: Quick with the usual words", () => {
  assert.equal(modeOf({ stock: 5 }), "quick");
  assert.equal(deliveryLine({ stock: 5 }), "Quick · 10–20 mins");
});

test("the shop's Quick answer brings its own time", () => {
  assert.equal(deliveryLine({}, { mode: "quick", when: "30 mins" }), "Quick · 30 mins");
});

test("out of stock is never Quick, and shows no line at all", () => {
  const p = { stock: 0 };
  assert.ok(isOut(p));
  assert.equal(modeOf(p), "none");
  assert.equal(deliveryLine(p), "");
  assert.equal(deliveryLine(p, { mode: "quick", when: "30 mins" }), "", "the shop's Quick answer does not count");
});

test("out of stock with its own Express promise keeps that promise", () => {
  const p = { stock: 0, delivery: "Next day" };
  assert.equal(modeOf(p, { mode: "quick" }), "all");
  assert.equal(deliveryLine(p, { mode: "quick", when: "30 mins" }), "Express · Next day");
});

test("a product Inventory does not track (no stock sent) is not out", () => {
  assert.equal(isOut({}), false);
  assert.equal(deliveryLine({}), "Quick · 10–20 mins");
});

test("Express: the product's promise first, then the hub rules', else just Express", () => {
  assert.equal(deliveryLine({ delivery: "2 days" }, { mode: "all", when: "Tomorrow" }), "Express · 2 days");
  assert.equal(deliveryLine({}, { mode: "all", when: "Tomorrow" }), "Express · Tomorrow");
  assert.equal(deliveryLine({}, { mode: "all" }), "Express");
});
