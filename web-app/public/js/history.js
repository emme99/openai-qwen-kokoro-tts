// Storia persistente (localStorage) + export puri CSV/JSON. I blob audio restano in memoria (ultimi 10).
export const HISTORY_KEY = "tts.history";
export const HISTORY_MAX = 200;
export const capRows = (rows, max = HISTORY_MAX) => rows.slice(0, max);
const COLS = ["ts","profileName","device","engine","voice","fallback","language","speed","format","model","serviceMs","totalMs","audioMs","rtf","bytes","text"];
function csvCell(v) {
  const s = v === null || v === undefined ? "" : String(v);
  return /[",\n;]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}
export function toCSV(rows) {
  return [COLS.join(","), ...rows.map((r) => COLS.map((c) => csvCell(r[c])).join(","))].join("\n");
}
export const toJSON = (rows) => JSON.stringify(rows, null, 2);
export function loadHistory() { try { const raw = localStorage.getItem(HISTORY_KEY); if (raw) return JSON.parse(raw); } catch { /* node */ } return []; }
export function saveHistory(rows) { try { localStorage.setItem(HISTORY_KEY, JSON.stringify(capRows(rows))); } catch { /* quota */ } }
