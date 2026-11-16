import { test } from "node:test";
import assert from "node:assert/strict";
import { parseVoices } from "../public/js/voices.js";

test("forma unificata", () => {
  const p = parseVoices({ engine: "kokoro", defaults: { it: "alloy", en: "ash" }, registry: [{ name: "alloy" }, { name: "ash" }], native: ["if_sara", "am_adam"], files: ["voices/alloy.wav"] });
  assert.deepEqual(p.names, ["alloy", "am_adam", "ash", "if_sara"]);
  assert.equal(p.engine, "kokoro"); assert.equal(p.defaults.it, "alloy");
});
test("forma macOS mapping", () => { const p = parseVoices({ voices: { alloy: { macos: "Alice" }, ash: { macos: "Samantha" } } }); assert.deepEqual(p.names, ["alloy", "ash"]); });
test("forma ignota/assente", () => { const p = parseVoices(null); assert.deepEqual(p.names, []); assert.equal(p.engine, null); });
test("native come array di stringhe", () => { const p = parseVoices({ native: ["af_heart", "bf_emma"] }); assert.deepEqual(p.names, ["af_heart", "bf_emma"]); });
test("files: basename senza estensione", () => { const p = parseVoices({ files: ["voices/sage.wav"] }); assert.deepEqual(p.names, ["sage"]); });
