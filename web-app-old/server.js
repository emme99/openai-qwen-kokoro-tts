// Proxy generico per servizi TTS OpenAI-compatible + file statici della console.
// Bind solo localhost di default; allowlist host per evitare che il proxy diventi un open relay.
import express from "express";
import path from "node:path";
import fs from "node:fs";
import { fileURLToPath } from "node:url";
import { isAllowedUrl, buildSpeechPayload, renameHeaders } from "./lib/validate.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Mini caricatore .env (zero dipendenze): non sovrascrive variabili gia' presenti nell'ambiente.
const envFile = path.join(__dirname, ".env");
if (fs.existsSync(envFile)) {
  for (const line of fs.readFileSync(envFile, "utf8").split("\n")) {
    const m = line.match(/^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$/);
    if (m && !(m[1] in process.env)) process.env[m[1]] = m[2].replace(/^["']|["']$/g, "");
  }
}

const PORT = Number(process.env.PORT || 3000);
const HOST = process.env.HOST || "127.0.0.1";
const ALLOWED_HOSTS = (process.env.ALLOWED_HOSTS || "127.0.0.1,localhost").split(",").map((s) => s.trim()).filter(Boolean);
const ALLOW_ANY_HOST = String(process.env.ALLOW_ANY_HOST || "false").toLowerCase() === "true";
const TIMEOUT_MS = Number(process.env.TIMEOUT_MS || 120000);

const app = express();
app.use(express.json({ limit: "1mb" }));
app.use(express.static(path.join(__dirname, "public")));

function checkTarget(res, target) {
  const v = isAllowedUrl(target, { allowedHosts: ALLOWED_HOSTS, allowAny: ALLOW_ANY_HOST });
  if (!v.ok) { res.status(400).json({ detail: v.reason }); return false; }
  return true;
}

async function fetchWithTimeout(url, options = {}) {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
  try { return await fetch(url, { ...options, signal: ctrl.signal }); }
  finally { clearTimeout(t); }
}

app.post("/api/generate", async (req, res) => {
  const { baseUrl, apiKey } = req.body || {};
  if (!checkTarget(res, baseUrl)) return;
  const built = buildSpeechPayload(req.body);
  if (!built.ok) return res.status(400).json({ detail: built.reason });
  const url = String(baseUrl).replace(/\/+$/, "") + "/v1/audio/speech";
  try {
    const headers = { "Content-Type": "application/json" };
    if (apiKey) headers["Authorization"] = `Bearer ${apiKey}`;
    const r = await fetchWithTimeout(url, { method: "POST", headers, body: JSON.stringify(built.payload) });
    if (!r.ok) {
      const text = await r.text();
      let detail = text;
      try { detail = JSON.parse(text).detail ?? text; } catch { /* testo non JSON */ }
      return res.status(r.status).json({ detail: String(detail).slice(0, 500) });
    }
    for (const [k, v] of Object.entries(renameHeaders(r.headers))) res.set(k, v);
    res.set("Content-Type", r.headers.get("content-type") || "audio/mpeg");
    res.send(Buffer.from(await r.arrayBuffer()));
  } catch (e) {
    const msg = e.name === "AbortError" ? "timeout dal servizio TTS" : (e.cause?.message || e.message);
    res.status(502).json({ detail: `servizio non raggiungibile: ${msg}` });
  }
});

async function passthroughJson(req, res, suffix) {
  const target = req.query.target;
  if (!checkTarget(res, target)) return;
  const url = String(target).replace(/\/+$/, "") + suffix;
  try {
    const r = await fetchWithTimeout(url, { method: "GET" });
    const text = await r.text();
    res.status(r.status);
    try { res.json(JSON.parse(text)); } catch { res.send(text); }
  } catch (e) {
    res.status(502).json({ detail: `servizio non raggiungibile: ${e.cause?.message || e.message}` });
  }
}

app.get("/api/health", (req, res) => passthroughJson(req, res, "/health"));
app.get("/api/voices", (req, res) => passthroughJson(req, res, "/v1/voices"));

app.listen(PORT, HOST, () => {
  console.log(`TTS console su http://${HOST}:${PORT} (allowlist: ${ALLOW_ANY_HOST ? "any" : ALLOWED_HOSTS.join(", ")})`);
});
