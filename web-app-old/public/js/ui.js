// Unico modulo che tocca il DOM: orchestrazione di sintesi, A/B, bench, storia, profili.
import * as api from "./api.js";
import { loadProfiles, saveProfiles, normalizeProfile, slug, isLocal } from "./profiles.js";
import { parseVoices } from "./voices.js";
import { median, p95, rtf, fmtMs, fmtBytes, fmtRtf, aggregate } from "./stats.js";
import { loadHistory, saveHistory, toCSV, toJSON, capRows } from "./history.js";
import { assignLabels, makeVote, tally, votesToMd, loadVotes, saveVotes } from "./ab.js";
import { canonicalFingerprintInput, sha256Hex, summarize, reportMd } from "./bench.js";

const $ = (id) => document.getElementById(id);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const uid = () => (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`);

let profiles = loadProfiles();
let history = loadHistory();
let votes = loadVotes();
let phrases = [];
const blobs = new Map(); // id -> objectURL (ultimi 10, per replay istantaneo)
let benchCancel = false;
let abCurrent = null;
let benchMeta = null, benchSummary = null, benchResults = [];

function download(name, text, mime = "text/plain") {
  const url = URL.createObjectURL(new Blob([text], { type: mime }));
  const a = document.createElement("a");
  a.href = url; a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function keepBlob(id, url) {
  blobs.set(id, url);
  while (blobs.size > 10) { const k = blobs.keys().next().value; URL.revokeObjectURL(blobs.get(k)); blobs.delete(k); }
}
function measureAudio(url) {
  return new Promise((resolve) => {
    const a = new Audio(); a.preload = "metadata";
    const done = (v) => { a.src = ""; resolve(v); };
    const t = setTimeout(() => done(null), 4000);
    a.onloadedmetadata = () => { clearTimeout(t); done(Number.isFinite(a.duration) ? a.duration * 1000 : null); };
    a.onerror = () => { clearTimeout(t); done(null); };
    a.src = url;
  });
}
function activeProfile() { return profiles.find((p) => p.id === $("profileSelect").value) || profiles[0]; }

// ---- Sintesi: una richiesta, metriche, storia ----
async function synthesize(profile, params, { autoplay = false, record = true } = {}) {
  const { blob, headers, totalMs } = await api.generate(profile, params);
  const url = URL.createObjectURL(blob);
  const audioMs = await measureAudio(url);
  const serviceMs = Number(headers.get("X-TTS-Process-Time-Ms"));
  const row = {
    id: uid(), ts: new Date().toISOString(),
    profileId: profile.id, profileName: profile.name,
    device: headers.get("X-TTS-Device") || "?", engine: headers.get("X-TTS-Engine") || "",
    voice: headers.get("X-TTS-Voice") || params.voice, fallback: headers.get("X-TTS-Voice-Fallback") || "",
    language: params.language, speed: params.speed, format: params.response_format, model: params.model || profile.model,
    text: params.input,
    serviceMs: Number.isFinite(serviceMs) && serviceMs > 0 ? serviceMs : null,
    totalMs, audioMs, rtf: rtf(serviceMs, audioMs) ?? rtf(totalMs, audioMs), bytes: blob.size,
  };
  if (record) { history = capRows([row, ...history]); saveHistory(history); keepBlob(row.id, url); renderHistory(); renderAgg(); }
  return { url, row };
}

function synthParams() {
  const voice = $("voiceFree").checked ? $("voiceInput").value.trim() : $("voiceSelect").value;
  return {
    input: $("textInput").value, voice: voice || "default", language: $("languageSelect").value,
    speed: Number($("speedRange").value), response_format: $("formatSelect").value, model: $("modelInput").value.trim(),
  };
}
async function onGenerate() {
  const p = activeProfile(); const params = synthParams();
  if (!params.input.trim()) { $("status").textContent = "Inserisci del testo."; return; }
  $("generateBtn").disabled = true; $("status").textContent = "Generazione in corso…"; $("fallbackBanner").hidden = true;
  try {
    const { url, row } = await synthesize(p, params, { autoplay: true });
    $("audioPlayer").src = url; $("audioPlayer").play().catch(() => {});
    $("mService").textContent = fmtMs(row.serviceMs); $("mTotal").textContent = fmtMs(row.totalMs);
    $("mAudio").textContent = fmtMs(row.audioMs); $("mRtf").textContent = fmtRtf(row.rtf);
    $("mBytes").textContent = fmtBytes(row.bytes); $("mVoice").textContent = row.voice + (row.device !== "?" ? ` · ${row.device}` : "");
    if (row.fallback) { $("fallbackBanner").textContent = `Fallback voce: ${row.fallback}`; $("fallbackBanner").hidden = false; }
    $("status").textContent = `Completato in ${fmtMs(row.totalMs)}`;
  } catch (e) { $("status").textContent = "Errore: " + e.message; }
  finally { $("generateBtn").disabled = false; }
}

// ---- Profili + discovery ----
function fillSelect(sel, items, keep) {
  const prev = keep ?? sel.value;
  sel.replaceChildren(...items.map(([v, label]) => { const o = document.createElement("option"); o.value = v; o.textContent = label; return o; }));
  if ([...sel.options].some((o) => o.value === prev)) sel.value = prev;
}
function renderProfileSelects() {
  const items = profiles.map((p) => [p.id, p.name]);
  for (const id of ["profileSelect", "abProfileA", "abProfileB", "pmSelect"]) fillSelect($(id), items);
  fillSelect($("histFilterProfile"), [["", "tutti"], ...items]);
  $("modelInput").value = activeProfile()?.model || "tts-1";
  renderBenchProfiles();
}
async function discoverVoices() {
  const p = activeProfile(); if (!p) return;
  const res = await api.voices(p.baseUrl).catch(() => null);
  const parsed = parseVoices(res?.json);
  const lang = $("languageSelect").value;
  if (parsed.names.length) {
    $("voiceFree").checked = false; $("voiceInput").hidden = true; $("voiceSelect").hidden = false;
    fillSelect($("voiceSelect"), parsed.names.map((n) => [n, n + (parsed.defaults?.[lang] === n ? " (default)" : "")]));
    const def = p.voices?.[lang] || parsed.defaults?.[lang];
    if (def && parsed.names.includes(def)) $("voiceSelect").value = def;
  } else {
    $("voiceSelect").hidden = true; $("voiceFree").checked = true; $("voiceInput").hidden = false;
    $("voiceInput").value = p.voices?.[lang] || "alloy";
  }
  $("engineBadge").textContent = parsed.engine ? `engine: ${parsed.engine}` : (res?.ok ? "discovery ok" : "discovery non disponibile");
}
async function refreshHealth() {
  const bar = $("profileBar"); bar.replaceChildren();
  for (const p of profiles) {
    const b = document.createElement("span"); b.className = "badge"; b.textContent = `${p.name}: …`;
    bar.appendChild(b);
    const h = await api.health(p.baseUrl).catch(() => null);
    if (h?.ok && h.json) {
      const j = h.json; const bits = [j.engine, j.device, j.model_loaded === false ? "non caricato" : null].filter(Boolean);
      b.textContent = `${p.name}: ok${bits.length ? " · " + bits.join("/") : ""}`; b.classList.add("ok");
    } else {
      const v = await api.voices(p.baseUrl).catch(() => null);
      if (v?.ok) { b.textContent = `${p.name}: raggiungibile`; b.classList.add("ok"); }
      else { b.textContent = `${p.name}: offline`; b.classList.add("err"); }
    }
    if (!isLocal(p.baseUrl)) { b.textContent += " ⚠ non locale"; b.classList.add("err"); }
  }
}
function loadPmFields() {
  const p = profiles.find((x) => x.id === $("pmSelect").value); if (!p) return;
  $("pmName").value = p.name; $("pmBaseUrl").value = p.baseUrl; $("pmModel").value = p.model;
  $("pmApiKey").value = p.apiKey; $("pmVoiceIt").value = p.voices.it; $("pmVoiceEn").value = p.voices.en;
  $("pmHint").textContent = isLocal(p.baseUrl) ? "" : "⚠ endpoint non locale: i dati escono dalla macchina.";
}
function pmFromFields() {
  return normalizeProfile({ name: $("pmName").value, baseUrl: $("pmBaseUrl").value, model: $("pmModel").value,
    apiKey: $("pmApiKey").value, voices: { it: $("pmVoiceIt").value, en: $("pmVoiceEn").value } });
}
function afterProfilesChange() { saveProfiles(profiles); renderProfileSelects(); loadPmFields(); refreshHealth(); discoverVoices(); }

// ---- A/B blind ----
async function abRun() {
  const pA = profiles.find((p) => p.id === $("abProfileA").value);
  const pB = profiles.find((p) => p.id === $("abProfileB").value);
  if (!pA || !pB || pA.id === pB.id) { $("abStatus").textContent = "Scegli due profili diversi."; return; }
  const lang = $("abLanguage").value, speed = Number($("abSpeed").value), text = $("abText").value;
  if (!text.trim()) { $("abStatus").textContent = "Inserisci del testo."; return; }
  const seed = Date.now() % 2147483647, labels = assignLabels(seed), pair = [pA.id, pB.id];
  abCurrent = { seed, labels, pair, slots: [null, null] };
  $("abRun").disabled = true; $("abReveal").hidden = true;
  for (const b of ["abVoteA", "abVoteB", "abVoteTie"]) $(b).disabled = true;
  try {
    for (let slot = 0; slot < 2; slot++) {
      const prof = profiles.find((p) => p.id === pair[labels[slot]]);
      $("abStatus").textContent = `Sintesi ${slot === 0 ? "A" : "B"}…`;
      const params = { input: text, voice: prof.voices?.[lang] || "default", language: lang, speed, response_format: "mp3", model: prof.model };
      const { url, row } = await synthesize(prof, params, { record: true });
      abCurrent.slots[slot] = { profileId: prof.id, profileName: prof.name, url, row };
      $(slot === 0 ? "abPlayerA" : "abPlayerB").src = url;
      await sleep(300); // pacing: niente contention GPU
    }
    $("abStatus").textContent = "Ascolta A e B, poi vota (i nomi sono nascosti).";
    for (const b of ["abVoteA", "abVoteB", "abVoteTie"]) $(b).disabled = false;
  } catch (e) { $("abStatus").textContent = "Errore: " + e.message; }
  finally { $("abRun").disabled = false; }
}
function abVote(winner) {
  if (!abCurrent || abCurrent.slots.some((s) => !s)) return;
  const metrics = abCurrent.slots.map((s) => ({ profileId: s.profileId, serviceMs: s.row.serviceMs, totalMs: s.row.totalMs, rtf: s.row.rtf }));
  const vote = makeVote({ pair: abCurrent.pair, labels: abCurrent.labels, winner, note: $("abNote").value, metrics, seed: abCurrent.seed });
  votes = [vote, ...votes]; saveVotes(votes);
  const [sA, sB] = abCurrent.slots;
  $("abReveal").innerHTML = "";
  $("abReveal").append(`A = ${sA.profileName} (${sA.row.voice}, ${fmtMs(sA.row.serviceMs)}) · B = ${sB.profileName} (${sB.row.voice}, ${fmtMs(sB.row.serviceMs)})`);
  $("abReveal").hidden = false;
  for (const b of ["abVoteA", "abVoteB", "abVoteTie"]) $(b).disabled = true;
  renderTally();
}
function renderTally() {
  const t = tally(votes); const el = $("abTally"); el.replaceChildren();
  const keys = Object.keys(t);
  if (!keys.length) { el.textContent = "Nessun voto ancora."; return; }
  for (const k of keys) {
    const s = t[k]; const wins = Object.entries(s.wins).map(([p, n]) => `${p}: ${n}`).join(", ") || "—";
    const d = document.createElement("div"); d.textContent = `${k} → ${s.n} confronti, ${s.ties} pari, vittorie [${wins}]`;
    el.appendChild(d);
  }
}

// ---- Bench batch ----
function renderBenchProfiles() {
  const box = $("benchProfiles"), gates = $("benchGates"); box.replaceChildren(); gates.replaceChildren();
  for (const p of profiles) {
    const l = document.createElement("label"); l.className = "check";
    const c = document.createElement("input"); c.type = "checkbox"; c.value = p.id; c.className = "bench-profile";
    l.append(c, ` ${p.name}`); box.appendChild(l);
    const g = document.createElement("label"); g.className = "check"; g.textContent = `gate ${p.id} (ms) `;
    const gi = document.createElement("input"); gi.type = "number"; gi.className = "bench-gate"; gi.dataset.profile = p.id;
    gi.value = p.id === "qwen" ? 2000 : p.id === "kokoro" ? 800 : 1500; gi.style.width = "90px";
    g.appendChild(gi); gates.appendChild(g);
  }
}
async function benchRun() {
  const selected = [...document.querySelectorAll(".bench-profile:checked")].map((c) => profiles.find((p) => p.id === c.value)).filter(Boolean);
  if (!selected.length) { $("benchProgress").textContent = "Seleziona almeno un profilo."; return; }
  if (!phrases.length) { $("benchProgress").textContent = "phrases.json non caricato."; return; }
  const repeats = Number($("benchRepeats").value), pacing = Number($("benchPacing").value), speed = Number($("benchSpeed").value);
  const gates = {}; for (const gi of document.querySelectorAll(".bench-gate")) gates[gi.dataset.profile] = Number(gi.value);
  benchCancel = false; $("benchStart").disabled = true; $("benchCancel").disabled = false;
  benchResults = [];
  const total = selected.length * phrases.length * repeats; let done = 0;
  try {
    for (const prof of selected) {
      await synthesize(prof, { input: phrases[0].text, voice: prof.voices?.[phrases[0].lang] || "default", language: phrases[0].lang, speed, response_format: "mp3", model: prof.model }, { record: false });
      for (const ph of phrases) for (let r = 0; r < repeats; r++) {
        if (benchCancel) throw new Error("annullato");
        const { row } = await synthesize(prof, { input: ph.text, voice: prof.voices?.[ph.lang] || "default", language: ph.lang, speed, response_format: "mp3", model: prof.model }, { record: false });
        benchResults.push(row); done++;
        $("benchProgress").textContent = `${done}/${total} · ${prof.name} · ${ph.id} (${fmtMs(row.serviceMs)})`;
        await sleep(pacing);
      }
    }
    benchSummary = summarize(benchResults, gates);
    const fp = await sha256Hex(canonicalFingerprintInput({ profiles: selected, phrases, speed, repeats }));
    benchMeta = { date: new Date().toISOString(), fingerprint: fp, speed, repeats, phraseCount: phrases.length };
    $("benchFingerprint").textContent = `impronta: ${fp}`;
    renderBenchResults();
    $("benchProgress").textContent = benchCancel ? "Annullato." : `Completato: ${done} sintesi.`;
  } catch (e) { $("benchProgress").textContent = e.message === "annullato" ? "Annullato." : "Errore: " + e.message; if (benchResults.length) { benchSummary = summarize(benchResults, gates); renderBenchResults(); } }
  finally { $("benchStart").disabled = false; $("benchCancel").disabled = true; }
}
function renderBenchResults() {
  const tb = $("benchResults"); tb.replaceChildren();
  for (const s of benchSummary || []) {
    const tr = document.createElement("tr");
    const cells = [s.name, s.n, fmtMs(s.p50), fmtMs(s.p95), fmtRtf(s.rtfMedian), s.gateMs ?? "--"];
    for (const c of cells) { const td = document.createElement("td"); td.textContent = c; tr.appendChild(td); }
    const td = document.createElement("td"); td.textContent = s.pass === null ? "n/d" : s.pass ? "PASS" : "FAIL"; td.className = s.pass ? "pass" : "fail"; tr.appendChild(td);
    tb.appendChild(tr);
  }
}

// ---- Storia ----
function renderAgg() {
  const tb = $("aggTable"); tb.replaceChildren();
  for (const g of aggregate(history)) {
    const tr = document.createElement("tr");
    for (const c of [g.key, g.n, fmtMs(g.p50), fmtMs(g.p95), fmtRtf(g.rtfMedian)]) { const td = document.createElement("td"); td.textContent = c; tr.appendChild(td); }
    tb.appendChild(tr);
  }
}
function filteredHistory() {
  const fp = $("histFilterProfile").value, fd = $("histFilterDevice").value;
  return history.filter((r) => (!fp || r.profileId === fp) && (!fd || r.device === fd));
}
function renderHistory() {
  const devices = [...new Set(history.map((r) => r.device))].sort();
  fillSelect($("histFilterDevice"), [["", "tutti"], ...devices.map((d) => [d, d])]);
  const rows = filteredHistory(); $("histCount").textContent = `${rows.length} righe`;
  const tb = $("histTable"); tb.replaceChildren();
  if (!rows.length) { const tr = document.createElement("tr"); const td = document.createElement("td"); td.colSpan = 8; td.textContent = "Storia vuota: genera qualcosa nella tab Sintesi."; td.className = "muted"; tr.appendChild(td); tb.appendChild(tr); return; }
  for (const r of rows) {
    const tr = document.createElement("tr");
    for (const c of [new Date(r.ts).toLocaleTimeString("it-IT"), r.profileName, r.device, r.voice, fmtMs(r.serviceMs), fmtMs(r.totalMs), fmtRtf(r.rtf)]) {
      const td = document.createElement("td"); td.textContent = c; tr.appendChild(td);
    }
    const td = document.createElement("td");
    if (blobs.has(r.id)) { const b = document.createElement("button"); b.className = "ghost small"; b.textContent = "▶"; b.onclick = () => { switchTab("synth"); $("audioPlayer").src = blobs.get(r.id); $("audioPlayer").play().catch(() => {}); }; td.appendChild(b); }
    const regen = document.createElement("button"); regen.className = "ghost small"; regen.textContent = "↻"; regen.title = "rigenera";
    regen.onclick = async () => { const p = profiles.find((x) => x.id === r.profileId); if (!p) return; switchTab("synth"); $("status").textContent = "Rigenero…"; try { const { url } = await synthesize(p, { input: r.text, voice: r.voice, language: r.language, speed: r.speed, response_format: r.format, model: r.model }, { autoplay: true }); $("audioPlayer").src = url; $("audioPlayer").play().catch(() => {}); $("status").textContent = "Rigenerato."; } catch (e) { $("status").textContent = "Errore: " + e.message; } };
    td.appendChild(regen); tr.appendChild(td); tb.appendChild(tr);
  }
}

// ---- Tabs + init ----
function switchTab(name) {
  for (const b of document.querySelectorAll(".tabs button")) b.classList.toggle("active", b.dataset.tab === name);
  for (const s of document.querySelectorAll(".tab")) s.classList.toggle("active", s.id === `tab-${name}`);
}
export async function init() {
  try { phrases = await (await fetch("phrases.json")).json(); } catch { phrases = []; }
  renderProfileSelects(); renderHistory(); renderAgg(); renderTally(); loadPmFields();
  refreshHealth(); discoverVoices();
  for (const b of document.querySelectorAll(".tabs button")) b.onclick = () => switchTab(b.dataset.tab);
  $("refreshHealth").onclick = refreshHealth;
  $("generateBtn").onclick = onGenerate;
  $("textInput").addEventListener("keydown", (e) => { if ((e.ctrlKey || e.metaKey) && e.key === "Enter") onGenerate(); });
  $("profileSelect").onchange = () => { $("modelInput").value = activeProfile()?.model || "tts-1"; discoverVoices(); };
  $("languageSelect").onchange = discoverVoices;
  $("voiceFree").onchange = () => { $("voiceInput").hidden = !$("voiceFree").checked; $("voiceSelect").hidden = $("voiceFree").checked; };
  $("speedRange").oninput = () => { $("speedValue").textContent = Number($("speedRange").value).toFixed(2); };
  for (const b of document.querySelectorAll(".presets button")) b.onclick = () => { $("speedRange").value = b.dataset.speed; $("speedValue").textContent = Number(b.dataset.speed).toFixed(2); };
  $("pmSelect").onchange = loadPmFields;
  $("pmSave").onclick = () => { const i = profiles.findIndex((p) => p.id === $("pmSelect").value); if (i < 0) return; const np = pmFromFields(); np.id = profiles[i].id; profiles[i] = np; afterProfilesChange(); };
  $("pmAdd").onclick = () => { const np = pmFromFields(); if (profiles.some((p) => p.id === np.id)) np.id = `${np.id}-${Date.now().toString(36)}`; profiles.push(np); afterProfilesChange(); $("pmSelect").value = np.id; loadPmFields(); };
  $("pmDelete").onclick = () => { if (profiles.length <= 1) return; profiles = profiles.filter((p) => p.id !== $("pmSelect").value); afterProfilesChange(); };
  $("abRun").onclick = abRun;
  $("abVoteA").onclick = () => abVote("A"); $("abVoteB").onclick = () => abVote("B"); $("abVoteTie").onclick = () => abVote("tie");
  $("abExportJson").onclick = () => download("ab-votes.json", toJSON(votes), "application/json");
  $("abExportMd").onclick = () => download("ab-votes.md", votesToMd(votes), "text/markdown");
  $("benchStart").onclick = benchRun; $("benchCancel").onclick = () => { benchCancel = true; };
  $("benchExportMd").onclick = () => { if (benchSummary) download("report.md", reportMd(benchSummary, benchMeta), "text/markdown"); };
  $("benchExportJson").onclick = () => { if (benchSummary) download("bench-results.json", JSON.stringify({ meta: benchMeta, summary: benchSummary, results: benchResults }, null, 2), "application/json"); };
  $("histFilterProfile").onchange = renderHistory; $("histFilterDevice").onchange = renderHistory;
  $("histExportCsv").onclick = () => download("history.csv", toCSV(filteredHistory()), "text/csv");
  $("histExportJson").onclick = () => download("history.json", toJSON(filteredHistory()), "application/json");
  $("histClear").onclick = () => { history = []; saveHistory(history); for (const u of blobs.values()) URL.revokeObjectURL(u); blobs.clear(); renderHistory(); renderAgg(); };
}
