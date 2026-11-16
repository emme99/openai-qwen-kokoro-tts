// Logica pura del confronto A/B blind: etichette randomizzate deterministiche dato il seed, voti, tally.
export const AB_KEY = "tts.ab.votes";
export function mulberry32(seed) {
  let a = seed >>> 0;
  return function () {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
// labels[0] = indice del profilo che finisce sotto "A", labels[1] sotto "B".
export function assignLabels(seed) { return mulberry32(seed)() < 0.5 ? [0, 1] : [1, 0]; }
export function makeVote({ pair, labels, winner, note, metrics, seed }) {
  const winnerProfile = winner === "tie" ? null : pair[labels[winner === "A" ? 0 : 1]];
  return { ts: Date.now(), pair: [...pair].sort(), winner, winnerProfile, note: note || "", metrics, seed };
}
export function tally(votes) {
  const out = {};
  for (const v of votes) {
    const key = v.pair.join(" vs ");
    if (!out[key]) out[key] = { n: 0, ties: 0, wins: {} };
    out[key].n += 1;
    if (v.winner === "tie" || !v.winnerProfile) out[key].ties += 1;
    else out[key].wins[v.winnerProfile] = (out[key].wins[v.winnerProfile] || 0) + 1;
  }
  return out;
}
export function votesToMd(votes) {
  const lines = ["# Voti A/B", ""];
  for (const [key, s] of Object.entries(tally(votes))) {
    lines.push(`## ${key}`, `- confronti: ${s.n}, pari: ${s.ties}`);
    for (const [p, n] of Object.entries(s.wins)) lines.push(`- ${p}: ${n} vittorie`);
    lines.push("");
  }
  return lines.join("\n");
}
export function loadVotes() { try { const raw = localStorage.getItem(AB_KEY); if (raw) return JSON.parse(raw); } catch { /* node */ } return []; }
export function saveVotes(v) { try { localStorage.setItem(AB_KEY, JSON.stringify(v)); } catch { /* quota */ } }
