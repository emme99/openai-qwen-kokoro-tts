// Logica pura del bench batch: impronta canonica, SHA-256, riepilogo con gate, report Markdown.
import { median, p95 } from "./stats.js";
export function canonicalFingerprintInput({ profiles, phrases, speed, repeats }) {
  const slim = profiles.map((p) => ({ id: p.id, baseUrl: p.baseUrl, model: p.model })).sort((a, b) => a.id.localeCompare(b.id));
  const ph = phrases.map((p) => ({ id: p.id, text: p.text, lang: p.lang })).sort((a, b) => a.id.localeCompare(b.id));
  return JSON.stringify({ profiles: slim, phrases: ph, speed, repeats });
}
export async function sha256Hex(str) {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(str));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}
export function summarize(results, gates = {}) {
  const byProfile = new Map();
  for (const r of results) {
    if (!byProfile.has(r.profileId)) byProfile.set(r.profileId, []);
    byProfile.get(r.profileId).push(r);
  }
  return [...byProfile.entries()].map(([id, rs]) => {
    const service = rs.map((r) => r.serviceMs).filter(Number.isFinite);
    const basis = service.length ? service : rs.map((r) => r.totalMs);
    const gate = gates[id] ?? null;
    const p50 = median(basis);
    return {
      profileId: id, name: rs[0].profileName, n: rs.length,
      p50, p95: p95(basis), rtfMedian: median(rs.map((r) => r.rtf)),
      gateMs: gate, pass: gate === null || p50 === null ? null : p50 <= gate,
    };
  }).sort((a, b) => a.profileId.localeCompare(b.profileId));
}
export function reportMd(summary, meta) {
  const lines = ["# Bench TTS", "", `- data: ${meta.date}`, `- impronta: ${meta.fingerprint}`,
    `- speed: ${meta.speed}, repeats: ${meta.repeats}, frasi: ${meta.phraseCount}`, "",
    "| Profilo | n | p50 ms | p95 ms | RTF mediano | Gate ms | Esito |",
    "|---|---|---|---|---|---|---|"];
  for (const s of summary) {
    lines.push(`| ${s.name} | ${s.n} | ${s.p50 === null ? "--" : Math.round(s.p50)} | ${s.p95 === null ? "--" : Math.round(s.p95)} | ${s.rtfMedian === null ? "--" : s.rtfMedian.toFixed(2)} | ${s.gateMs ?? "--"} | ${s.pass === null ? "n/d" : s.pass ? "PASS" : "FAIL"} |`);
  }
  return lines.join("\n") + "\n";
}
