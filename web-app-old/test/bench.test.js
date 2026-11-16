import { test } from "node:test";
import assert from "node:assert/strict";
import { canonicalFingerprintInput, sha256Hex, summarize, reportMd } from "../public/js/bench.js";

const profiles = [{ id: "qwen", baseUrl: "http://127.0.0.1:5050", model: "tts-1" }];
const phrases = [{ id: "it01", text: "ciao", lang: "it" }];
test("fingerprint canonico indipendente dall'ordine", () => {
  const a = canonicalFingerprintInput({ profiles, phrases, speed: 1, repeats: 3 });
  const b = canonicalFingerprintInput({ profiles: [...profiles].reverse(), phrases: [...phrases].reverse(), speed: 1, repeats: 3 });
  assert.equal(a, b);
});
test("sha256 vettore noto", async () => { assert.equal(await sha256Hex("abc"), "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"); });
test("summarize gate pass/fail", () => {
  const results = [ { profileId: "qwen", profileName: "Qwen", serviceMs: 1500, totalMs: 1600, rtf: 0.5 }, { profileId: "qwen", profileName: "Qwen", serviceMs: 2500, totalMs: 2600, rtf: 0.6 } ];
  const s = summarize(results, { qwen: 2000 })[0]; assert.equal(s.p50, 2000); assert.equal(s.pass, true);
  const s2 = summarize(results, { qwen: 1000 })[0]; assert.equal(s2.pass, false);
});
test("summarize senza gate", () => { const s = summarize([{ profileId: "x", profileName: "X", serviceMs: 100, totalMs: 110, rtf: 0.3 }], {})[0]; assert.equal(s.pass, null); });
test("reportMd contiene tabella e impronta", () => { const md = reportMd([{ name: "Qwen", n: 2, p50: 2000, p95: 2500, rtfMedian: 0.5, gateMs: 2000, pass: true }], { date: "x", fingerprint: "abc", speed: 1, repeats: 3, phraseCount: 10 }); assert.ok(md.includes("| Qwen |")); assert.ok(md.includes("abc")); assert.ok(md.includes("PASS")); });
