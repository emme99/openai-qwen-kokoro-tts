# plan-webapp.md — Console di valutazione TTS generica (OpenAI-compatible)

> Evoluzione di web-app/ da "Qwen3-TTS Tester" a console di test/valutazione per QUALSIASI
> servizio TTS OpenAI-compatible: Qwen3-TTS, Kokoro-82M, il servizio macOS `say`, altri.
> Stesso metodo del plan.md: un task per chat (Splash + Qwen3.0 27b), verifica, commit.

## 0. Contesto e obiettivi

Stato attuale (verificato nel codice):
- `server.js`: `TTS_API_URL` hardcoded (localhost:5050), `model:"qwen3-tts"` hardcoded,
  **`speed` NON inoltrato**, `app.listen(PORT)` su tutte le interfacce, `cors()` aperto.
- Proxy `/api/generate` inoltra solo text/voice/language/response_format; passa through
  `X-Process-Time-Ms`→`X-TTS-Process-Time-Ms` e `X-Device`→`X-TTS-Device`.
- UI italiana, card singola: select voci hardcoded (default/alloy/ash/echo/nova/sage),
  lingua it/en, mp3 fisso, player audio, sezione "Tempi" (servizio/totale/mediane CPU e MPS)
  con storia in-memory (ultime 10, persa al reload).
- `script.js` monolitico, CSS inline, solo tema chiaro. Nessun test, nessuno script npm test.

Obiettivi:
1. **Profili endpoint** configurabili e persistiti: {nome, baseUrl, model, apiKey?, voci default}.
   La web-app non conosce gli engine: conosce endpoint. Seed: qwen@5050, kokoro@5052, say@5051.
2. **Parametri completi**: voice (discovery + input libero), language, speed (slider 0.25–4.0
   con preset 0.3/0.7/1.0 di tutor-local), response_format mp3/wav, model.
3. **Metriche da valutazione**: tempo servizio (header), tempo totale client, durata audio,
   **RTF** = tempo servizio / durata audio, bytes, voce risolta + eventuale fallback, engine/device.
   Mediane p50/p95 raggruppate per **profilo+device** (generalizza le attuali mediane CPU/MPS).
4. **Storia persistente** (localStorage) con export CSV/JSON e replay.
5. **Confronto A/B blind** tra due profili: stesso testo, sintesi sequenziale, etichette
   randomizzate, voto A/B/pari + nota, reveal, tally, export.
6. **Bench batch**: set frasi condiviso col bench CLI del piano 1, repeats, warmup scartato,
   p50/p95/RTF per profilo, gate configurabili, export report.md + JSON con impronta.
7. Igiene: bind 127.0.0.1, proxy con allowlist host, niente CORS, tema chiaro/scuro, test unitari.

Non-obiettivi: framework UI, build step, autenticazione, persistenza server-side (stretch),
waveform/spettrogrammi (stretch). Si resta vanilla JS + CSS puro + Express, `npm start` e via.

Vincoli: Node ≥ 18; dipendenze runtime invariate (express, axios); CORS rimosso (same-origin);
sintesi SEMPRE sequenziali (GPU condivisa, misure pulite, meno calore) con pacing opzionale.

## 1. Come usare questo piano col modello locale

Stesse regole del plan.md §1 (una chat per task, solo i file elencati, temperature 0.2,
max_tokens ≥ 4096, thinking spento per i task meccanici, commit per task).
Nota: i file UI sono autocontenuti; con Splash che regge contesti grandi puoi allegare
index.html + il modulo JS del task together, ma non tutto il progetto.
Template prompt: identico al plan.md, con "Vanilla JS ES modules, niente build step,
niente nuove dipendenze runtime, commenti in italiano".

## 2. Architettura target

```
web-app/
  server.js               proxy generico + validazione URL + bind localhost
  .env.example            PORT, ALLOWED_HOSTS, ALLOW_ANY_HOST
  package.json            + "test": "node --test"
  public/
    index.html            tabs: Sintesi | Confronto A/B | Bench | Storia
    styles.css            tema chiaro/scuro (prefers-color-scheme), CSS puro
    js/
      api.js              fetch verso il proxy (generate/health/voices)
      profiles.js         CRUD profili in localStorage + seed
      voices.js           adapter /v1/voices (PURO, testabile in node)
      stats.js            median/p95/RTF/bytes (PURO)
      history.js          storia localStorage + export CSV/JSON (PURO per export)
      ab.js               logica A/B: ordine randomizzato, voti, tally (PURO)
      bench.js            orchestrazione batch + fingerprint + report (PURO dove possibile)
      ui.js               rendering, tabs, form, player
  test/                   node --test su moduli puri + validatore URL
```
Principio: tutta la logica di calcolo in moduli puri importabili sia dal browser (ES modules)
sia da `node --test`; `ui.js` è l'unico modulo che tocca il DOM.

## 3. Design decisions

### 3.1 Profili (non engine)
Schema profilo (localStorage, chiave `tts.profiles`):
```json
{ "id": "qwen", "name": "Qwen3-TTS (MPS)", "baseUrl": "http://127.0.0.1:5050",
  "model": "tts-1", "apiKey": "", "voices": {"it": "alloy", "en": "ash"}, "notes": "" }
```
Seed al primo avvio: qwen@5050, kokoro@5052, say@5051 (model "tts-1" per tutti: è formalità
di protocollo; con lo stretch F6 del piano 1 si potrà mettere "kokoro"/"qwen3-tts").
`apiKey` opzionale per endpoint generici (anche cloud): inviato solo al proxy locale;
se l'host non è locale, banner di avviso "endpoint non locale: i dati escono dalla macchina".

### 3.2 Proxy generico (server.js)
`POST /api/generate` body: `{baseUrl, apiKey?, model, input, voice, language, speed, response_format}`.
- Inoltra TUTTI i campi al `/v1/audio/speech` del baseUrl (speed incluso!).
- Pass-through di tutti gli header `X-*` della risposta come `X-TTS-*`
  (Engine, Voice, Voice-Fallback, Device, Process-Time-Ms).
- Validazione: protocollo http/https; host in `ALLOWED_HOSTS` (default `127.0.0.1,localhost`);
  `ALLOW_ANY_HOST=true` per endpoint generici (default false). Rifiuti → 400 con messaggio chiaro.
- Timeout 120 s; errore del servizio → stesso status + `detail` leggibile.
- `GET /api/health?target=<baseUrl>` e `GET /api/voices?target=<baseUrl>`: pass-through con
  la stessa validazione. `app.listen(PORT, "127.0.0.1")`. Rimuovere `cors`.

### 3.3 Adapter /v1/voices (tre forme, degradazione graziosa)
1. Servizio unificato (piano 1 T3.2): `{engine, defaults:{it,en}, registry:[...], native:[...], files:[...]}`
   → select con i nomi logici del registry + native + file; mostra engine e defaults.
2. Servizio macOS: risposta con mapping voci OpenAI→macOS → estrae i nomi supportati.
3. Endpoint senza /v1/voices (o errore) → **input libero** per la voce + nota "discovery non disponibile".
L'adapter è una funzione pura `parseVoices(json) -> {names:[...], defaults?, engine?, raw}` con unit test.

### 3.4 Metriche
- `serviceMs`: header `X-TTS-Process-Time-Ms` (sintesi+conversione lato server).
- `totalMs`: performance.now() client (include rete/proxy).
- `audioMs`: `audio.duration * 1000` da `loadedmetadata`.
- `rtf`: serviceMs / audioMs (< 1 = più veloce del realtime). Se serviceMs assente → RTF da totalMs, flaggato.
- `bytes`: blob.size. `voice`: header X-TTS-Voice; `fallback`: X-TTS-Voice-Fallback → banner giallo.
- Aggregati p50/p95 per (profilo, device): sostituiscono le mediane CPU/MPS globali,
  ma il confronto tra device resta possibile filtrando la storia.

### 3.5 A/B blind
- Due profili, stesso testo/lingua/speed/format. Voce: default per lingua di ciascun profilo
  (o override per profilo). Grazie al registro del piano 1, "alloy" è la stessa voce logica
  sui due engine → confronto equo.
- Sintesi **sequenziale** con pacing (default 300 ms tra le due) per non contendere la GPU.
- Etichette A/B assegnate a caso (seed registrabile nei test), player separati, voto A/B/pari
  + nota facoltativa, poi reveal (profilo+voce+metriche). Tally per coppia di profili, export JSON/MD.
- I voti sono salvati in localStorage (`tts.ab.votes`) e includono le metriche dei due clip.

### 3.6 Bench batch
- Set frasi **condiviso** col CLI: `bench/phrases.json` nella root del repo
  (10 frasi: 5 it, 5 en, ~15 parole; id + text + lang). Il piano 1 T5.2 va allineato per leggerlo.
- Run: warmup 1 per profilo (scartato) → phrases × repeats (default 3), sequenziale, pacing 250 ms.
- Progress bar + annulla. Risultati: p50/p95 serviceMs, RTF mediano, per profilo.
- Gate configurabili in UI (default: qwen 2000 ms, kokoro 800 ms — stessi del piano 1 T5.2).
- Export `report.md` + `results.json` con impronta SHA-256 (profili+modelli+frasi+speed+repeats)
  via crypto.subtle — stessa cultura llm_bench: risultati confrontabili solo a parità di impronta.

### 3.7 Persistenza
localStorage: profili, storia (≤ 200 righe, solo parametri+metriche), voti A/B, impostazioni.
Blob audio: ultimi 10 in memoria per replay istantaneo; dalla storia più vecchia si "rigenera"
(nuova richiesta, metriche nuove — documentato in UI). Export CSV/JSON sempre disponibile.

## 4. Fasi e task

### FASE W0 — Proxy generico (server)
**W0.1 — Inoltro completo + pass-through header**
- File: `server.js`.
- Body del proxy come §3.2; inoltrare speed/model/apiKey; rinominare tutti gli X-* in X-TTS-*.
- Accettazione: curl al proxy con speed=0.7 → il servizio riceve speed (log lato servizio);
  risposta contiene X-TTS-Process-Time-Ms; con servizio unificato anche X-TTS-Engine/Voice.

**W0.2 — Validazione URL, bind, pulizia**
- File: `server.js`, `.env.example` (nuovo), `package.json`.
- Allowlist host (funzione pura `isAllowedUrl(url, allowedHosts, allowAny)` in `lib/validate.js`,
  condivisa coi test), bind 127.0.0.1, rimuovere cors, route /api/health e /api/voices.
- Accettazione: baseUrl `http://evil.example` → 400; `http://127.0.0.1:5052` → OK;
  il server non è raggiungibile dall'IP LAN; `node --test` verde sul validatore.

### FASE W1 — Profili, discovery, form completo (client)
**W1.1 — Modularizzazione + tema**
- File: `public/index.html`, `public/styles.css` (nuovo), `public/js/*` (nuovi), `public/script.js` (rimosso).
- Estrarre CSS inline; script type=module; tabs Scheletro (Sintesi/A/B/Bench/Storia);
  dark/light automatico; comportamento attuale invariato nella tab Sintesi.
- Accettazione: generazione+player+tempi funzionano come prima; tema scuro leggibile; nessuna regressione.

**W1.2 — Profili + health**
- File: `public/js/profiles.js`, `public/js/api.js`, `public/js/ui.js`, `index.html`.
- CRUD profili + seed (§3.1); select profilo attivo; badge per profilo: health OK/errore,
  engine/device/model_loaded se presenti; avviso endpoint non locale.
- Accettazione: tre profili seed visibili;切换 profilo cambia il servizio chiamato;
  profilo con porta sbagliata → badge errore senza rompere la UI.

**W1.3 — Discovery voci + parametri completi**
- File: `public/js/voices.js`, `public/js/ui.js`, `index.html`, `test/voices.test.js`.
- Adapter §3.3 con test sulle tre forme; select voci dinamica + input libero; language estendibile;
  speed slider 0.25–4.0 + preset 0.3/0.7/1.0; format mp3/wav; model dal profilo (editabile).
- Accettazione: con servizio unificato la select mostra alloy/ash + native kokoro;
  con servizio senza /v1/voices l'input libero funziona; speed 0.3 inoltrato (verifica W0.1).

### FASE W2 — Metriche e storia
**W2.1 — Metriche complete**
- File: `public/js/stats.js`, `public/js/ui.js`, `test/stats.test.js`.
- Funzioni pure median/p95/rtf; audioMs da loadedmetadata; bytes; banner fallback voce;
  p50/p95 per profilo+device nella sezione Tempi.
- Accettazione: unit test su median/p95/rtf (casi noti, lista vuota, serviceMs assente);
  RTF mostrato e coerente con serviceMs/audioMs a mano.

**W2.2 — Storia persistente + export**
- File: `public/js/history.js`, `public/js/ui.js`, `index.html`, `test/history.test.js`.
- Tab Storia: tabella ≤200 righe persistita, filtri profilo/device, replay (blob in memoria)
  e rigenera, export CSV/JSON (funzioni pure di serializzazione, test su escaping), svuota.
- Accettazione: reload pagina → storia intatta; CSV aperto in Numbers/Excel senza colonne rotte;
  rigenera produce una nuova riga con metriche nuove.

### FASE W3 — Confronto A/B blind
**W3.1 — Flusso A/B**
- File: `public/js/ab.js`, `public/js/ui.js`, `index.html`, `test/ab.test.js`.
- Logica pura: assegnazione randomizzata (seed), tally, record voto con metriche.
  UI: scelta 2 profili, testo/lingua/speed, sintesi sequenziale + pacing, player A/B,
  voto + nota, reveal, tally per coppia, export JSON/MD.
- Accettazione: con seed fisso l'ordine è deterministico (test); 10 voti → tally corretto;
  le due sintesi non si sovrappongono (verifica dai timestamp); export leggibile.

### FASE W4 — Bench batch
**W4.1 — Set frasi + orchestrazione**
- File: `bench/phrases.json` (root repo), `public/js/bench.js`, `public/js/ui.js`, `index.html`.
- 10 frasi it/en; scelta profili, repeats (default 3), warmup scartato, progress + annulla, pacing.
- Accettazione: bench 10×2×3 completato; annulla interrompe dopo il clip corrente;
  il file phrases.json è lo stesso letto da scripts/bench_tts.py (piano 1 T5.2, da allineare).

**W4.2 — Risultati, gate, export con impronta**
- File: `public/js/bench.js`, `public/js/stats.js`, `test/bench.test.js`, `index.html`.
- p50/p95/RTF per profilo; gate configurabili (default 2000/800 ms) evidenziati pass/fail;
  export report.md + results.json con impronta SHA-256 (crypto.subtle).
- Accettazione: impronta identica a parità di inputs (test); report.md apribile e coerente
  col formato del bench CLI; gate fail evidenziato in rosso.

### FASE W5 — Qualità, test, docs
**W5.1 — Suite node:test**
- File: `web-app/test/*`, `package.json` ("test": "node --test").
- ≥ 25 test sui moduli puri (validate, voices, stats, history export, ab, bench fingerprint).
- Accettazione: `npm test` verde da clone pulito con `npm ci` (nessun servizio attivo richiesto).

**W5.2 — UX polish**
- File: `public/js/ui.js`, `public/styles.css`, `index.html`.
- Ctrl+Invio genera, focus management nei tabs, aria-live sullo status, responsive <820 px,
  empty states (storia vuota, nessun profilo, discovery assente).
- Accettazione: checklist manuale documentata in web-app/README.md; navigazione da tastiera OK.

**W5.3 — Docs + CI**
- File: `web-app/README.md` (nuovo), `README.md` (sezione web-app), `.github/workflows/ci.yml`.
- Job CI: npm ci + npm test (nessun modello, nessun servizio). README: profili, A/B, bench,
  setup due istanze, troubleshooting (header assenti, discovery assente, porta occupata).
- Accettazione: CI verde; README permette a un estraneo di fare il primo A/B in 5 minuti.

**W5.4 — Smoke end-to-end con i profili di tutor-local**
- Manuale: alloy+it e ash+en su qwen e kokoro, speed 0.3 → durata ×3.33 ±10% (ffprobe o player);
  profilo say@5051 → voices adapter forma macOS; A/B qwen vs kokoro con 5 frasi; bench completo.
- Accettazione: tutto documentato in results/webapp-smoke.md con data e versioni.

### FASE W6 — Stretch (dopo la DoD)
- Waveform canvas per clip; bench con >2 profili; import di phrase set esterni;
  persistenza server-side (sqlite) al posto di localStorage; display del routing per lingua
  se implementato lo stretch F6 del piano 1.

## 5. Definition of Done
- [ ] Il proxy inoltra speed/model/apiKey e tutti gli header X-*; bind 127.0.0.1; allowlist attiva
- [ ] Tre profili seed funzionanti (qwen/kokoro/say); discovery con adapter sulle tre forme
- [ ] Metriche complete (serviceMs/totalMs/audioMs/RTF/bytes/voce risolta/fallback)
- [ ] Storia persistente + export CSV/JSON; replay e rigenera
- [ ] A/B blind sequenziale con voti, tally ed export
- [ ] Bench batch con gate e impronta, phrases.json condiviso col CLI
- [ ] ≥25 test node:test verdi in CI; tema scuro; README completo
- [ ] Smoke end-to-end documentato, incluso speed 0.3 verificato sulla durata

## 6. Rischi e mitigazioni
| Rischio | Mitigazione |
|---|---|
| Contention GPU falsando le misure | Sintesi sempre sequenziali + pacing; warmup scartato |
| Header/voices assenti su endpoint generici | Degradazione graziosa: input libero voce, RTF da totalMs flaggato |
| Quota localStorage | Cap 200 righe + export; blob solo in memoria |
| Proxy come open relay | Allowlist host di default, ALLOW_ANY_HOST esplicito, bind localhost |
| Forme /v1/voices divergenti tra servizi | Adapter puro con test su tutte e tre le forme |
| Surriscaldamento nei bench lunghi | Repeats default 3, pacing 250 ms, kokoro in CPU; annulla sempre disponibile |
| Confronto A/B non equo (voci diverse) | Nomi logici dal registro (piano 1) + default per lingua per profilo |

## 7. Dipendenze dal plan.md (servizio)
| Task web-app | Dipende da | Nota |
|---|---|---|
| W0 (proxy) | nessuna | Parte subito; speed avrà effetto reale dopo T1.1 |
| W1.3 discovery | T3.2 (/v1/voices unificato) | Prima: adapter forma macOS + input libero |
| W2 banner fallback/voce | T3.2 (headers) | Prima: colonne vuote, nessun errore |
| W3 A/B tra engine | due istanze del servizio (§8) | Nessuna dipendenza dallo stretch F6 |
| W4 bench | T5.2 allineato a bench/phrases.json | Stessi gate, stessa impronta |
| W5.4 smoke | T1.1 (speed) + F4 (kokoro) | È la validazione finale congiunta |

Ordine consigliato: W0 → W1 → W2 in parallelo alle fasi 1–3 del servizio; W3–W5 dopo F4.

## 8. Setup per l'A/B tra engine (due istanze, zero stretch)
Istanza 1 (invariata): `.env` con `TTS_ENGINE=qwen`, `PORT=5050`, `PRELOAD=true`.
Istanza 2: copia del repo o stessa working dir con env diversi:
```ini
TTS_ENGINE=kokoro
PORT=5052
PRELOAD=true
KOKORO_MODEL_PATH=./models/kokoro-v1.0.onnx
KOKORO_VOICES_PATH=./models/voices-v1.0.bin
```
RAM totale ~4,5 GB (qwen ~3–4 + kokoro ~0,5): compatibile col budget del plan.md §0.
Servizio macOS `say`: `PORT=5051` nel suo .env (fallback, terzo profilo).
Con lo stretch F6 del piano 1 (model come override engine) basterà una sola istanza:
i profili useranno `model:"kokoro"` / `model:"qwen3-tts"` sulla stessa porta 5050.