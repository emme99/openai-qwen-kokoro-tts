# plan.md — openai-qwen-tts: fix + multi-engine (Qwen3-TTS / Kokoro-82M)

> Piano di lavoro incrementale per un modello di coding locale (Splash + Qwen3.0 27b,
> VSCode + personal-openai-chat). Un task per chat, verifica dopo ogni task, commit per task.

## 0. Contesto e obiettivi

Stato attuale (verificato nel codice):
- `speed` accettato in `SpeechRequest` ma **mai passato** a `synthesize()` → ignorato in silenzio.
- Inferenza bloccante dentro handler `async`, **nessun lock**: richieste concorrenti vanno in parallelo su MPS.
- Modello caricato alla prima richiesta (preload commentato).
- Se non trova una voce, `service.py` **crea `default.wav` da rumore casuale** e lo clona.
- `uvicorn.run(host="0.0.0.0")` hardcoded; README dice porta 8000, `config.json` dice 5050.
- Voce = file reference in `voices/`: non esiste un concetto di voce indipendente dall'engine.

Obiettivi:
1. Un solo servizio OpenAI-compatible (`POST /v1/audio/speech`, porta 5050), **drop-in per tutor-local**:
   `voice=alloy` (IT) / `voice=ash` (EN), `language=it|en`, `speed=0.3|0.7|1.0`, `response_format=mp3|wav`.
2. Engine selezionabile da `.env`: `TTS_ENGINE=qwen` (Qwen3-TTS-12Hz-0.6B, MPS, float32)
   oppure `TTS_ENGINE=kokoro` (Kokoro-82M via kokoro-onnx, CPU).
3. Nomi voce logici stabili tra engine, risolti da un registro (`voices.toml`).
4. `speed` funzionante e identico tra engine (atempo ffmpeg, pitch preservato).
5. Sicurezza locale: bind 127.0.0.1, niente fallback rumorosi, errori espliciti.
6. Test senza modelli scaricati + benchmark con gate + CI.

Non-obiettivi (per ora): streaming, autenticazione, UI di cloning, Docker su Mac per Qwen (MPS non passa).

Vincoli hardware (M3 Max 36 GB):
| Componente | RAM stimata |
|---|---|
| LLM sviluppo (Splash Qwen3.0 27b 4bit) **o** Gemma 26B del tutor — uno alla volta | ~15–16 GB |
| Whisper large-v3-turbo (tutor) | ~1,6 GB |
| Wav2Vec2 XLSR + driver MPS (tutor) | ~3,5 GB |
| Qwen3-TTS 0.6B float32 MPS | ~3–4 GB |
| Kokoro-onnx CPU | ~0,4–0,6 GB |
| macOS + browser + VSCode | ~6–8 GB |
→ Con Qwen TTS si è stretti (~30–33 GB): pre caricare **solo l'engine attivo**. Con Kokoro si respira.
→ Qwen: **float32 obbligatorio** (float16 produce probabilità invalide, documentato nel README).

## 1. Come usare questo piano con il modello locale

- **Una chat nuova per ogni task.** Allega solo i file elencati in "File del task".
- Incolla il blocco del task + i criteri di accettazione. Non anticipare fasi future.
- Parametri consigliati: temperature 0.2, max_tokens ≥ 4096, contesto 32K
  (`splash serve --model <Qwen3.0-27B> --max-context 32K`).
  Thinking **spento** per i task meccanici (`reasoning_effort: "none"`), acceso solo se un task
  di design fallisce due volte — stessa lezione del llm_bench di tutor-local.
- Dopo ogni task: esegui i comandi di verifica, poi `git commit -m "T_x.y: <titolo>"`.
- Se il modello produce diff incoerenti: spezza il task per file, richiedi file completi invece di diff.

Template di prompt:
```
Lavora SOLO sul task seguente. Non modificare file non elencati, non aggiungere
dipendenze non elencate, non cambiare l'API pubblica se non richiesto.
Commenti in italiano, identificatori in inglese. Python ≥ 3.11.
[FILE ALLEGATI]
[TASK T_x.y COPIATO DAL PIANO]
Output: file completi o diff, poi i comandi di verifica da eseguire.
```

## 2. Architettura target

```
app.py            HTTP, validazione, lock async, to_thread, headers
config.py         Settings da .env (precedenza: env > config.json deprecato > default)
voices.py         registro voices.toml + resolver PURO (testabile senza modelli)
audio.py            WAV encode, catena atempo (PURO), conversione mp3 via ffmpeg
engines/base.py   contratto TTSEngine
engines/qwen.py   wrapper di service.py (import pesanti dentro load())
engines/kokoro.py kokoro-onnx (CPU)
tests/            FakeEngine + funzioni pure + API con TestClient (niente torch in CI)
scripts/          bench_tts.py, download_kokoro.py, smoke.sh
```

Contratto engine (gli engine NON gestiscono speed né formato):
```python
class TTSEngine(Protocol):
    name: str
    def load(self) -> None: ...
    def synthesize(self, text: str, *, voice: str, language: str) -> tuple[np.ndarray, int]:
        """Ritorna (samples float32, sample_rate). voice = binding già risolto."""
    def list_voices(self) -> list[str]: ...
```
Speed e mp3/wav centralizzati in `audio.py` → comportamento identico tra engine, un solo percorso testabile.

`.env.example` completo:
```ini
TTS_ENGINE=qwen            # qwen | kokoro
HOST=127.0.0.1
PORT=5050
PRELOAD=true
DEFAULT_LANGUAGE=it
VOICE_IT=alloy             # nomi LOGICI dal registro
VOICE_EN=ash
MAX_INPUT_CHARS=2000
VOICES_REGISTRY=voices.toml

# --- Qwen3-TTS ---
DEVICE=mps                 # mps | cpu | cuda
DTYPE=float32              # NON usare float16 (rotto su questo modello)
MODEL_PATH=./models/Qwen/Qwen3-TTS-12Hz-0.6B-Base
FLASH_ATTN=false

# --- Kokoro-82M (onnx, CPU) ---
KOKORO_MODEL_PATH=./models/kokoro-v1.0.onnx
KOKORO_VOICES_PATH=./models/voices-v1.0.bin
```

## 3. Design delle voci (soluzione del problema "voce = modello")

Problema: con Qwen la voce è un file reference; con Kokoro è interna al checkpoint
(`if_sara`, `am_adam`, …). Il client (tutor-local) non deve saperlo.

Soluzione: **nome logico stabile + registro con binding per engine + default per lingua in .env**.
`voices.toml` (tomllib è stdlib, zero dipendenze):
```toml
[alloy]
language = "it"
qwen = "voices/alloy.wav"
kokoro = "if_sara"

[ash]
language = "en"
qwen = "voices/ash.wav"
kokoro = "am_adam"

[nova]
language = "en"
qwen = "voices/nova.wav"
kokoro = "af_heart"

[sage]
language = "en"
qwen = "voices/sage.wav"
kokoro = "bf_emma"
```
Ordine di risoluzione (funzione pura, deterministica, testata):
1. `language` mancante → `DEFAULT_LANGUAGE`. Non in mappa → 400 con elenco lingue.
2. `voice` nel registro → binding dell'engine attivo; binding mancante → passo 4 con warning.
3. `voice` fuori registro:
   - engine qwen: esiste `voices/{voice}.wav`? → usa il file (compatibilità legacy).
   - engine kokoro: è un id nativo valido (in `list_voices()`)? → passthrough.
4. Non risolvibile (o `voice="default"`/vuoto) → default per lingua (`VOICE_IT`/`VOICE_EN`).
   Se anche il default non risolve → **400 con elenco voci disponibili. Mai rumore.**
5. Politica lingua: `language` della richiesta vince sempre.
   - qwen: il cloning è cross-lingual → tieni il reference, header `X-Voice-Fallback: cross-lingual`.
   - kokoro: le voci sono legate alla lingua → sostituisci col default della lingua richiesta,
     header `X-Voice-Fallback: language-default`.

Endpoint `GET /v1/voices` → `{engine, defaults:{it,en}, registry:[...], native:[...], files:[...]}`
(stessa filosofia del servizio macOS: ispezionabile).
Headers risposta: `X-Engine`, `X-Voice` (risolta), `X-Voice-Fallback` (solo se scattato),
`X-Process-Time-Ms` (già presente, mantenere), `X-Device`.
Campo `model`: accettato e ignorato, documentato come formalità (override engine = stretch F6).

Risultato: **tutor-local non cambia una riga di .env** quando passi da qwen a kokoro.

## 4. Fasi e task

### FASE 0 — Rete di sicurezza (nessun cambio di comportamento)

**T0.1 — Settings da .env**
- File: `config.py` (nuovo), `app.py`, `.env.example`, `requirements.txt` (+`python-dotenv`).
- `Settings` tipizzata con i campi del `.env.example`; precedenza env > config.json > default.
  `config.json` resta funzionante ma deprecato (log warning una volta).
- Accettazione: `PORT=5051 python app.py` parte su 5051; senza env usa config.json; test unitario sulla precedenza.

**T0.2 — Bind e porta**
- File: `app.py`, `README.md`.
- `uvicorn.run(app, host=settings.host, port=settings.port)`; default `127.0.0.1:5050`.
  README: eliminare ogni riferimento a 8000.
- Accettazione: `curl http://127.0.0.1:5050/health` OK; il servizio non è raggiungibile dall'IP LAN.

**T0.3 — Via il fallback rumoroso**
- File: `service.py`.
- Rimuovere il blocco che genera `default.wav` da `np.random`. Nessun reference → eccezione
  dedicata `VoiceNotFound` → HTTP 400 con elenco voci disponibili.
- Accettazione: richiesta con voice inesistente e senza default → 400; nessun file creato in `voices/`.

**T0.4 — Igiene e baseline riproducibile**
- File: `.gitignore`, `requirements.txt`, `requirements-dev.txt` (nuovo), `ruff.toml` (nuovo).
- Ignorare `models/`, `voices/cache/`, `.env`, `*.log`; rimuovere `trace.log` dal repo.
  Pinnare le versioni attuali funzionanti (`pip freeze` selettivo). Dev: pytest, ruff, httpx.
  Ruff come tutor-local: E/F/I, line-length 120.
- Accettazione: `ruff check .` verde; `git status` pulito dopo un avvio.

### FASE 1 — Correttezza del servizio Qwen

**T1.1 — speed funzionante (atempo centralizzato)**
- File: `audio.py` (nuovo), `app.py`, `tests/test_audio.py`.
- Funzione pura `build_atempo(speed: float) -> list[float]`: ogni stadio in [0.5, 2.0].
  Esempi: 1.0 → []; 0.7 → [0.7]; 0.3 → [0.5, 0.6]; 2.5 → [2.0, 1.25].
- Validazione API: speed ∈ [0.25, 4.0], altrimenti 400. Applicare la catena ffmpeg
  (`-filter:a atempo=...`) al WAV prodotto, prima dell'eventuale mp3. Gli engine non vedono speed.
- Accettazione: unit test sulla catena; con speed=0.3 la durata del file è ×3.33 ±10%
  (`ffprobe -v error -show_entries format=duration -of csv=p=0 out.mp3`); pitch invariato all'ascolto.

**T1.2 — Concorrenza: lock + thread**
- File: `app.py`, `tests/test_api.py`.
- `asyncio.Lock` globale; `await asyncio.to_thread(engine.synthesize, ...)` sotto lock.
  Pattern identico a `tutor-local/backend/app/providers/stt.py`.
- Accettazione: con FakeEngine(sleep=0.5), due POST concorrenti durano ~1.0 s totali (serializzati);
  `/health` risponde in <50 ms durante una sintesi in corso.

**T1.3 — Preload + lifespan**
- File: `app.py`.
- Sostituire `@app.on_event("startup")` (deprecato) con `lifespan`; se `PRELOAD=true`,
  `await asyncio.to_thread(engine.load)` all'avvio. `/health` → `{engine, device, model_loaded, defaults}`.
- Accettazione: prima richiesta a caldo (X-Process-Time-Ms senza picco di load); avvio con PRELOAD=false ancora lazy.

**T1.4 — Guardrail e cache**
- File: `app.py`, `service.py`.
- `MAX_INPUT_CHARS` → 400 oltre soglia. Cache prompt: mantenere al massimo 2 file per voce
  (cancellare i più vecchi per mtime alla scrittura). Commento su `weights_only=False`
  (pickle locale fidato, cache non condivisa).
- Accettazione: input 3000 caratteri → 400; dopo 3 mtime diversi della stessa voce, la cache contiene 2 file.

### FASE 2 — Astrazione engine (refactor puro, comportamento invariato)

**T2.1 — Contratto + wrapper Qwen + factory**
- File: `engines/base.py`, `engines/qwen.py` (nuovi), `service.py`, `app.py`, `tests/conftest.py`.
- `engines/qwen.py` incapsula `service.py` (pulire il doppio import try/except in cima);
  import di torch/qwen_tts **dentro** `load()`/`__init__`, mai a livello modulo.
  Factory: `make_engine(settings) -> TTSEngine` da `TTS_ENGINE`.
  `FakeEngine` in conftest: sinusoide a sr=24000, sleep configurabile, lista voci finta.
- Accettazione: suite API verde con FakeEngine **senza torch installato**; con engine qwen reale,
  output audio invariato rispetto a prima del refactor (ascolto + durata).

**T2.2 — audio.py unico percorso di encoding**
- File: `audio.py`, `app.py`, `engines/qwen.py`.
- Gli engine ritornano `(samples, sr)`; WAV encode + atempo + mp3 solo in `audio.py`
  (ffmpeg via subprocess, stderr catturato, errore → 500 con messaggio leggibile).
- Accettazione: golden test: stessa sinusoide in ingresso → stesso SHA256 del WAV in uscita.

### FASE 3 — Registro voci unificato

**T3.1 — voices.toml + resolver puro**
- File: `voices.toml`, `voices.py` (nuovo), `tests/test_voices.py`.
- `resolve_voice(voice, language, engine, registry, files, native, defaults) -> ResolvedVoice`
  con campi `{binding: str, fallback: str | None}`; implementa l'ordine del §3.
- Accettazione: unit test per tutti i rami (registro hit, binding mancante, file legacy qwen,
  passthrough nativo kokoro, default per lingua, 400, cross-lingual).

**T3.2 — Integrazione API + /v1/voices**
- File: `app.py`, `engines/*.py`, `README.md`.
- Usare il resolver a ogni richiesta; headers del §3; `GET /v1/voices`.
- Accettazione: richiesta tutor-local (`alloy`+`it`, `ash`+`en`, speed 0.7) risolve senza fallback;
  `ash`+`it` con engine kokoro → voce italiana di default + header X-Voice-Fallback.

### FASE 4 — Kokoro-82M

**T4.1 — engines/kokoro.py (kokoro-onnx, CPU)**
- File: `engines/kokoro.py`, `requirements.txt` (+`kokoro-onnx`, `soundfile`),
  `scripts/download_kokoro.py`, `.env.example`.
- Download `kokoro-v1.0.onnx` + `voices-v1.0.bin` (release model-files del repo kokoro-onnx) in `models/`.
  ```python
  from kokoro_onnx import Kokoro   # import dentro load()
  self._k = Kokoro(settings.kokoro_model_path, settings.kokoro_voices_path)
  samples, sr = self._k.create(text, voice=binding, speed=1.0, lang=lang_code)
  ```
  `speed=1.0` sempre (atempo è centralizzato). Mappa lang: `it → "it"`, `en → "en-us"`
  — **verificare i codici sulla versione installata** (misaki/espeak-ng; espeak-ng è già
  installato per tutor-local). Pinnare la versione testata.
- Accettazione: `TTS_ENGINE=kokoro python app.py`; curl it/en in mp3 → audio valido;
  p50 su frase di ~15 parole < 1 s (CPU, M3 Max).

**T4.2 — Voci native + registro reale**
- File: `voices.py`, `voices.toml`, `engines/kokoro.py`, `tests/test_voices.py`.
- `list_voices()` dal file voices; verificare che `if_sara`, `im_nicola`, `af_heart`, `am_adam`,
  `bf_emma` esistano in voices-v1.0.bin (altrimenti scegliere equivalenti da VOICES.md di Kokoro-82M
  e aggiornare il registro). Prefisso → lingua: `i→it`, `a/b→en`.
- Accettazione: `/v1/voices` con engine kokoro elenca le native; passthrough di `if_sara` funziona.

**T4.3 — (opzionale) kokoro torch/MPS**
- Solo se onnx non basta. `KOKORO_BACKEND=torch` con device mps; noti quirks MPS → default resta onnx.
- Accettazione: bench comparativo onnx vs torch documentato; default invariato.

### FASE 5 — Validazione, bench, CI, docs

**T5.1 — Suite completa**
- File: `tests/`.
- ≥ 40 test: atempo, resolver, settings, API con FakeEngine (errori 400/500, headers, lock, speed).
  Nessun download di modelli, niente torch.
- Accettazione: `python -m pytest -q` verde da venv pulito con sole requirements-dev.

**T5.2 — scripts/bench_tts.py (con gate, stile tutor-local)**
- 10 frasi (5 it, 5 en, ~15 parole), 3 run ciascuna per engine; legge `X-Process-Time-Ms`
  + tempo client-side; riporta p50/p95 a caldo, cold start, RSS del processo.
  Gate: **qwen p50 ≤ 2.0 s; kokoro p50 ≤ 0.8 s**; exit 1 se falliti.
  Salva `results/report.md` con impronta (engine + modello + frasi + speed), stile llm_bench.
- Accettazione: report generato per entrambi gli engine; gate valutati.

**T5.3 — A/B ascolto**
- 4 clip salvate (it/en × qwen/kokoro) + 1 clip `say` per riferimento. Giudizio documentato
  in `results/listening.md`. La naturalezza si decide a orecchio, non col numero.

**T5.4 — CI**
- `.github/workflows/ci.yml`: ubuntu-latest, Python 3.12, pip requirements-dev, `ruff check .` + `pytest -q`.
  Nessun modello, nessuna GPU.
- Accettazione: workflow verde al push.

**T5.5 — README riscritto**
- .env completo, due engine, registro voci, curl aggiornati (porta 5050, speed),
  troubleshooting (float16 rotto, MPS sperimentale, espeak-ng, RAM), tabella RAM del §0.

**T5.6 — Integrazione con tutor-local**
- Servizio macOS: `PORT=5051` nel suo .env (fallback). Servizio unificato: 5050.
  .env di tutor-local **invariato** (`TTS_VOICE_IT=alloy`, `TTS_VOICE_EN=ash`).
- Test manuali: turno con spiegazioni IT + citazioni EN; speed 0.3 (verificare rallentamento reale);
  pannello aiuto; ripasso con "ascolta e prova". Controllare `timings.tts` nel TurnResponse.
- Accettazione: tutti i flussi funzionano con entrambi gli engine; fallback documentato
  (cambio `TTS_BASE_URL` a 5051).

### FASE 6 — Stretch (solo dopo la Definition of Done)

- `model` come override engine per-request (`"kokoro"`/`"qwen3-tts"`; `"tts-1"` → default), lazy load del secondo engine.
- Routing per lingua: `ENGINE_IT=qwen`, `ENGINE_EN=kokoro` (se l'italiano di Kokoro non convince all'A/B).
- Streaming a chunk per testi lunghi; Docker aggiornato (kokoro CPU gira in container su Mac, qwen no).

## 5. Definition of Done

- [ ] `TTS_ENGINE=qwen` e `TTS_ENGINE=kokoro` passano i rispettivi gate di bench
- [ ] speed 0.3 / 0.7 / 1.0 verificata con ffprobe su entrambi gli engine
- [ ] tutor-local funziona senza modifiche al proprio .env, con entrambi gli engine
- [ ] `/v1/voices` corretto; voce inesistente → 400; nessun fallback rumoroso
- [ ] bind 127.0.0.1 di default; preload attivo; /health responsive sotto carico
- [ ] ≥ 40 test verdi senza modelli; ruff verde; CI verde
- [ ] README allineato al codice (porta, parametri, engine, voci)
- [ ] A/B ascolto documentato; fallback `say` su 5051 pronto

## 6. Rischi e mitigazioni

| Rischio | Mitigazione |
|---|---|
| Latenza Qwen MPS oltre gate | Kokoro diventa il default del tutor; Qwen resta per il cloning |
| Italiano di Kokoro mediocre | A/B T5.3; stretch: routing per lingua (F6) |
| Codici lang/misaki di kokoro-onnx diversi tra versioni | Verifica in T4.1 + pin della versione testata |
| Artefatti Qwen su testi brevi/misti | tutor-local già segmenta IT/EN; fallback say; monitoring nei test manuali |
| Pressione RAM (36 GB) | Preload del solo engine attivo; kokoro-onnx è ~0,5 GB; un solo LLM alla volta |
| Diff incoerenti dal 27b locale | Task piccoli, un file alla volta, criteri di accettazione eseguiti prima del commit |

## 7. Ordine di esecuzione

F0 → F1 → F2 → F3 → F4 → F5, un task per chat, commit per task.
F2 prima di F3/F4 è deliberato: il resolver e Kokoro si innestano sul contratto engine, non su `service.py`.