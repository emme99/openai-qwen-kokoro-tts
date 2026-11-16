// Chiamate al proxy locale (same-origin): niente CORS, niente chiavi nel browser verso l'esterno.
export async function generate(profile, params) {
  const startedAt = performance.now();
  const r = await fetch("/api/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      baseUrl: profile.baseUrl, apiKey: profile.apiKey || "",
      model: params.model || profile.model,
      input: params.input, voice: params.voice, language: params.language,
      speed: params.speed, response_format: params.response_format,
    }),
  });
  const totalMs = performance.now() - startedAt;
  if (!r.ok) {
    let detail = await r.text();
    try { detail = JSON.parse(detail).detail ?? detail; } catch { /* testo */ }
    throw new Error(detail || `HTTP ${r.status}`);
  }
  const blob = await r.blob();
  return { blob, headers: r.headers, totalMs };
}

export async function getJson(route, target) {
  const r = await fetch(`${route}?target=${encodeURIComponent(target)}`);
  const text = await r.text();
  let json = null; try { json = JSON.parse(text); } catch { /* non JSON */ }
  return { ok: r.ok, status: r.status, json, text };
}
export const health = (baseUrl) => getJson("/api/health", baseUrl);
export const voices = (baseUrl) => getJson("/api/voices", baseUrl);
