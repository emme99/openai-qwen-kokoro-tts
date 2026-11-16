// Profili endpoint: la console non conosce gli engine, conosce servizi OpenAI-compatible.
export const PROFILES_KEY = "tts.profiles";
export const SEED = [
  { id: "qwen", name: "Qwen3-TTS (MPS)", baseUrl: "http://127.0.0.1:5050", model: "tts-1", apiKey: "", voices: { it: "alloy", en: "ash" }, notes: "" },
  { id: "kokoro", name: "Kokoro-82M (CPU)", baseUrl: "http://127.0.0.1:5052", model: "tts-1", apiKey: "", voices: { it: "alloy", en: "ash" }, notes: "" },
  { id: "say", name: "macOS say (fallback)", baseUrl: "http://127.0.0.1:5051", model: "tts-1", apiKey: "", voices: { it: "alloy", en: "ash" }, notes: "" },
];
export function slug(s) { return String(s).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "profilo"; }
export function normalizeProfile(p) {
  const id = String(p.id || "").trim() || slug(p.name || p.baseUrl || "profilo");
  return {
    id, name: String(p.name || id),
    baseUrl: String(p.baseUrl || "").trim().replace(/\/+$/, ""),
    model: String(p.model || "tts-1"), apiKey: String(p.apiKey || ""),
    voices: { it: p.voices?.it || "alloy", en: p.voices?.en || "ash" },
    notes: String(p.notes || ""),
  };
}
export function loadProfiles() {
  try { const raw = localStorage.getItem(PROFILES_KEY); if (raw) return JSON.parse(raw).map(normalizeProfile); } catch { /* node o quota */ }
  return SEED.map(normalizeProfile);
}
export function saveProfiles(list) { try { localStorage.setItem(PROFILES_KEY, JSON.stringify(list)); } catch { /* quota */ } }
export function isLocal(baseUrl) {
  try { const h = new URL(baseUrl).hostname; return h === "127.0.0.1" || h === "localhost" || h === "::1"; } catch { return false; }
}
