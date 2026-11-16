// Validazione pura lato proxy: URL consentiti, payload OpenAI-compatible, inoltro header.
// Nessuna dipendenza: testabile con node --test senza express.

export function isAllowedUrl(urlStr, { allowedHosts = ["127.0.0.1", "localhost"], allowAny = false } = {}) {
  let u;
  try { u = new URL(urlStr); } catch { return { ok: false, reason: "URL non valido" }; }
  if (u.protocol !== "http:" && u.protocol !== "https:") {
    return { ok: false, reason: "protocollo non consentito (solo http/https)" };
  }
  if (allowAny) return { ok: true, reason: null };
  if (!allowedHosts.includes(u.hostname)) {
    return { ok: false, reason: `host non in allowlist: ${u.hostname}` };
  }
  return { ok: true, reason: null };
}

export const SPEED_MIN = 0.25;
export const SPEED_MAX = 4.0;
export const FORMATS = ["mp3", "wav"];

export function buildSpeechPayload(body = {}) {
  const input = typeof body.input === "string" ? body.input.trim() : "";
  if (!input) return { ok: false, reason: "input mancante" };
  const speed = body.speed === undefined || body.speed === null || body.speed === "" ? 1.0 : Number(body.speed);
  if (!Number.isFinite(speed) || speed < SPEED_MIN || speed > SPEED_MAX) {
    return { ok: false, reason: `speed deve essere tra ${SPEED_MIN} e ${SPEED_MAX}` };
  }
  const format = body.response_format || "mp3";
  if (!FORMATS.includes(format)) return { ok: false, reason: "response_format deve essere mp3 o wav" };
  return {
    ok: true,
    payload: {
      model: body.model || "tts-1",
      input,
      voice: body.voice || "default",
      language: body.language || "it",
      speed,
      response_format: format,
    },
  };
}

export function renameHeaders(headers) {
  // Inoltra solo gli header X-* del servizio, rinominati X-TTS-* (case-insensitive in lettura).
  const out = {};
  const entries = typeof Headers !== "undefined" && headers instanceof Headers
    ? [...headers.entries()]
    : Object.entries(headers || {});
  for (const [name, value] of entries) {
    const lower = String(name).toLowerCase();
    if (lower.startsWith("x-")) out[`X-TTS-${lower.slice(2)}`] = String(value);
  }
  return out;
}
