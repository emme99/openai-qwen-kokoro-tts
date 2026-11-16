import { test } from "node:test";
import assert from "node:assert/strict";
import { toCSV, capRows } from "../public/js/history.js";

test("csv escaping virgole e virgolette", () => { const csv = toCSV([{ text: 'ciao, "mondo"', profileName: "qwen" }]); assert.ok(csv.includes('"ciao, ""mondo"""')); });
test("csv header presente", () => assert.ok(toCSV([]).startsWith("ts,profileName"));
test("capRows limita", () => assert.equal(capRows(Array.from({ length: 300 }, (_, i) => i)).length, 200));
test("csv newline nel testo", () => { const csv = toCSV([{ text: "a\nb" }]); assert.ok(csv.includes('"a\nb"')); });
