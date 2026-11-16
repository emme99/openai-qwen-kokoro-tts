import { test } from "node:test";
import assert from "node:assert/strict";
import { median, p95, rtf, aggregate } from "../public/js/stats.js";

test("mediana dispari", () => assert.equal(median([3, 1, 2]), 2));
test("mediana pari", () => assert.equal(median([1, 2, 3, 4]), 2.5));
test("mediana vuota", () => assert.equal(median([]), null));
test("mediana ignora non finiti", () => assert.equal(median([1, null, 3, NaN]), 2));
test("p95 nearest-rank", () => assert.equal(p95([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]), 10));
test("rtf", () => assert.equal(rtf(500, 1000), 0.5));
test("rtf audio zero", () => assert.equal(rtf(500, 0), null));
test("aggregate per profilo+device", () => {
  const rows = [ { profileName: "qwen", device: "mps", serviceMs: 100, totalMs: 120, rtf: 0.5 }, { profileName: "qwen", device: "mps", serviceMs: 200, totalMs: 220, rtf: 0.6 }, { profileName: "kokoro", device: "cpu", serviceMs: 50, totalMs: 60, rtf: 0.2 } ];
  const a = aggregate(rows); assert.equal(a.length, 2);
  const q = a.find((g) => g.key.includes("qwen")); assert.equal(q.n, 2); assert.equal(q.p50, 150);
});
