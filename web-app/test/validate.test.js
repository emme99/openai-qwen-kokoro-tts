import { test } from "node:test";
import assert from "node:assert/strict";
import { isAllowedUrl, buildSpeechPayload, renameHeaders } from "../lib/validate.js";

test("allowlist: localhost ok", () => assert.equal(isAllowedUrl("http://127.0.0.1:5050").ok, true));
test("allowlist: host esterno rifiutato", () => assert.equal(isAllowedUrl("http://evil.example").ok, false));
test("allowlist: allowAny consente esterno", () => assert.equal(isAllowedUrl("https://api.openai.com", { allowAny: true }).ok, true));
test("allowlist: protocollo non http rifiutato", () => assert.equal(isAllowedUrl("ftp://127.0.0.1").ok, false));
test("allowlist: URL invalido rifiutato", () => assert.equal(isAllowedUrl("non una url").ok, false));
test("payload: input mancante", () => assert.equal(buildSpeechPayload({}).ok, false));
test("payload: speed fuori range", () => assert.equal(buildSpeechPayload({ input: "ciao", speed: 9 }).ok, false));
test("payload: speed 0.3 valido e inoltrato", () => { const b = buildSpeechPayload({ input: "ciao", speed: 0.3 }); assert.equal(b.ok, true); assert.equal(b.payload.speed, 0.3); });
test("payload: formato non valido", () => assert.equal(buildSpeechPayload({ input: "ciao", response_format: "ogg" }).ok, false));
test("payload: default", () => { const b = buildSpeechPayload({ input: "ciao" }); assert.equal(b.payload.model, "tts-1"); assert.equal(b.payload.response_format, "mp3"); assert.equal(b.payload.speed, 1); });
test("headers: solo X-* rinominati", () => { const h = renameHeaders({ "x-process-time-ms": "123", "content-type": "audio/mpeg", "x-device": "mps" }); assert.deepEqual(h, { "X-TTS-process-time-ms": "123", "X-TTS-device": "mps" }); });
