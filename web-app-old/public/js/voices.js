// Adapter puro per /v1/voices: forma unificata (piano 1), mapping macOS, o assente/ignota.
function namesFrom(value) {
  const out = [];
  if (!value) return out;
  if (Array.isArray(value)) {
    for (const v of value) {
      if (typeof v === "string") out.push(v);
      else if (v && typeof v === "object") out.push(v.name || v.voice || v.id || "");
    }
  } else if (typeof value === "object") out.push(...Object.keys(value));
  else if (typeof value === "string") out.push(value);
  return out.filter(Boolean);
}
export function parseVoices(json) {
  if (!json || typeof json !== "object") return { names: [], defaults: null, engine: null, raw: json ?? null };
  const names = new Set([
    ...namesFrom(json.registry),
    ...namesFrom(json.native),
    ...namesFrom(json.voices),
    ...namesFrom(json.files).map((f) => String(f).replace(/^.*[\\/]/, "").replace(/\.wav$/i, "")),
    ...namesFrom(json.mapping),
    ...namesFrom(json.language_mapping),
  ]);
  const defaults = json.defaults && typeof json.defaults === "object" ? json.defaults : null;
  const engine = typeof json.engine === "string" ? json.engine : null;
  return { names: [...names].sort(), defaults, engine, raw: json };
}
