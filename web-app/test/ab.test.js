import { test } from "node:test";
import assert from "node:assert/strict";
import { assignLabels, makeVote, tally } from "../public/js/ab.js";

test("assignLabels deterministico dato seed", () => { assert.deepEqual(assignLabels(42), assignLabels(42)); });
test("assignLabels copre entrambi gli ordini", () => { const orders = new Set(Array.from({ length: 50 }, (_, i) => JSON.stringify(assignLabels(i)))); assert.equal(orders.size, 2); });
test("makeVote mappa etichetta->profilo", () => { const v = makeVote({ pair: ["qwen", "kokoro"], labels: [1, 0], winner: "A", metrics: [], seed: 1 }); assert.equal(v.winnerProfile, "kokoro"); });
test("makeVote pari", () => { const v = makeVote({ pair: ["a", "b"], labels: [0, 1], winner: "tie", metrics: [], seed: 1 }); assert.equal(v.winnerProfile, null); });
test("tally conta vittorie e pari", () => {
  const votes = [ makeVote({ pair: ["a", "b"], labels: [0, 1], winner: "A", metrics: [], seed: 1 }), makeVote({ pair: ["a", "b"], labels: [0, 1], winner: "tie", metrics: [], seed: 2 }), makeVote({ pair: ["a", "b"], labels: [1, 0], winner: "A", metrics: [], seed: 3 }) ];
  const t = tally(votes)["a vs b"]; assert.equal(t.n, 3); assert.equal(t.ties, 1); assert.equal(t.wins.a, 1); assert.equal(t.wins.b, 1);
});
