/** Self-check for Kestrel Vision maths. Run: `node src/civic/visionMath.check.ts` */
import assert from "node:assert/strict";

import { classify, scoreLabels, similarity, type Heads } from "./visionMath.ts";

const dims: [number, number] = [2, 2];
const unit = (v: number[]) => {
  const a = Math.hypot(v[0], v[1]), b = Math.hypot(v[2], v[3]);
  return [v[0] / a, v[1] / a, v[2] / b, v[3] / b];
};
const heads: Heads = {
  version: "test", dims, scale: 100, preselectThreshold: 0.9, sameSpotThreshold: 0.8,
  classes: [{ key: "pothole", category: "POTHOLE" }, { key: "road_ok", category: null }],
  classVectors: { pothole: unit([1, 0, 1, 0]), road_ok: unit([0, 1, 0, 1]) },
  extra: {},
};

// similarity averages the two halves' cosines
assert.equal(similarity(unit([1, 0, 1, 0]), unit([1, 0, 1, 0]), dims), 1);
assert.equal(similarity(unit([1, 0, 1, 0]), unit([0, 1, 0, 1]), dims), 0);
assert.ok(Math.abs(similarity(unit([1, 0, 0, 1]), unit([1, 0, 1, 0]), dims) - 0.5) < 1e-12, "one half agrees, one does not");

// probabilities sum to 1 and favour the nearer label
const p = scoreLabels(unit([0.9, 0.1, 0.8, 0.2]), heads.classVectors, heads);
assert.ok(Math.abs(p.pothole + p.road_ok - 1) < 1e-9);
assert.ok(p.pothole > 0.99);

// classify maps the visual class to the Kestrel category, and "nothing wrong" to null
const g = classify(unit([0.9, 0.1, 0.8, 0.2]), heads);
assert.deepEqual([g.key, g.category], ["pothole", "POTHOLE"]);
assert.equal(classify(unit([0.1, 0.9, 0.2, 0.8]), heads).category, null);
assert.equal(g.ranked[0].key, "pothole");

// numerically safe with large logits
const big = scoreLabels(unit([1, 0, 1, 0]), heads.classVectors, { dims, scale: 10_000 });
assert.ok(Number.isFinite(big.pothole) && Math.abs(big.pothole - 1) < 1e-9);

// a class bias shifts the decision exactly like the python evaluator's logit bias
const tie = unit([1, 1, 1, 1]);
assert.equal(classify(tie, { ...heads, classBias: { road_ok: 1 } }).key, "road_ok");
assert.equal(classify(tie, { ...heads, classBias: { pothole: 1 } }).key, "pothole");

console.log("visionMath.check.ts: all assertions passed");
