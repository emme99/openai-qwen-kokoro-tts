// Statistiche pure: mediana, p95 (nearest-rank), RTF, formattazione, aggregati per profilo+device.
export function median(values) {
  const v = values.filter(Number.isFinite).sort((a, b) => a - b);
  if (!v.length) return null;
  const m = Math.floor(v.length / 2);
  return v.length % 2 ? v[m] : (v[m - 1] + v[m]) / 2;
}
export function p95(values) {
  const v = values.filter(Number.isFinite).sort((a, b) => a - b);
  if (!v.length) return null;
  return v[Math.min(v.length - 1, Math.ceil(0.95 * v.length) - 1)];
}
export function rtf(serviceMs, audioMs) {
  if (!Number.isFinite(serviceMs) || !Number.isFinite(audioMs) || audioMs <= 0) return null;
  return serviceMs / audioMs;
}
export const fmtMs = (x) => (Number.isFinite(x) ? `${Math.round(x)} ms` : "--");
export const fmtBytes = (x) => (Number.isFinite(x) ? (x > 1048576 ? `${(x / 1048576).toFixed(1)} MB` : `${Math.round(x / 1024)} KB`) : "--");
export const fmtRtf = (x) => (Number.isFinite(x) ? x.toFixed(2) : "--");
export function aggregate(rows) {
  const groups = new Map();
  for (const r of rows) {
    const key = `${r.profileName || r.profileId} · ${r.device || "?"}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(r);
  }
  return [...groups.entries()].map(([key, rs]) => ({
    key, n: rs.length,
    p50: median(rs.map((r) => r.serviceMs ?? r.totalMs)),
    p95: p95(rs.map((r) => r.serviceMs ?? r.totalMs)),
    rtfMedian: median(rs.map((r) => r.rtf)),
  })).sort((a, b) => a.key.localeCompare(b.key));
}
