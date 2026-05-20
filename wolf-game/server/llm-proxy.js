"use strict";

const http = require("http");
const fs = require("fs");
const path = require("path");
const { loadConfig, watchConfig } = require("./config");
const { dispatch, REGISTRY } = require("./providers");

let cfg;
try {
  cfg = loadConfig();
} catch (e) {
  console.error("[llm-proxy]", e.message);
  process.exit(1);
}

watchConfig(newCfg => {
  cfg = newCfg;
  console.log(`[llm-proxy] config reloaded | available: ${cfg.available.join(", ") || "(none)"} | default: ${cfg.defaultProvider || "(none)"}`);
});

const LOG_FILE = path.join(__dirname, "..", "prompts.log");
const MEMORY_DIR = path.join(__dirname, "..", "memory");

function ensureMemoryDir() {
  if (!fs.existsSync(MEMORY_DIR)) fs.mkdirSync(MEMORY_DIR, { recursive: true });
}

function memoryPath(agentNo) {
  const n = Number(agentNo);
  if (!Number.isInteger(n) || n < 1 || n > 99) throw new Error(`bad agentNo: ${agentNo}`);
  return path.join(MEMORY_DIR, `agent-${n}.md`);
}

function appendMemory({ agentNo, header, content }) {
  ensureMemoryDir();
  const p = memoryPath(agentNo);
  if (!fs.existsSync(p) && header) {
    fs.writeFileSync(p, `# ${header}\n\n`, "utf-8");
  }
  fs.appendFileSync(p, content.endsWith("\n") ? content : content + "\n", "utf-8");
}

function resetMemory() {
  ensureMemoryDir();
  for (const name of fs.readdirSync(MEMORY_DIR)) {
    if (/^agent-\d+\.md$/.test(name)) fs.unlinkSync(path.join(MEMORY_DIR, name));
  }
}

function logPrompt(endpoint, provider, req, resp) {
  const ts = new Date().toISOString().slice(0, 19).replace("T", " ");
  const sep = "=".repeat(90);
  const lines = [
    sep,
    `[${ts}] ${endpoint}  provider=${provider}`,
    sep,
    "── SYSTEM ──", req.system || "(empty)", "",
    "── USER ──",   req.user   || "(empty)",
  ];
  if (req.tools?.length) {
    lines.push("", "── TOOLS ──", req.tools.map(t => `· ${t.name}`).join("\n"));
  }
  lines.push("", "── RESPONSE ──", JSON.stringify(resp, null, 2), "", "");
  try { fs.appendFileSync(LOG_FILE, lines.join("\n"), "utf-8"); }
  catch (e) { console.error("[llm-proxy] prompt log write failed:", e.message); }
}

function sendJson(res, status, obj) {
  res.writeHead(status, { "Content-Type": "application/json; charset=utf-8" });
  res.end(JSON.stringify(obj));
}

const server = http.createServer(async (req, res) => {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");
  if (req.method === "OPTIONS") { res.writeHead(204); res.end(); return; }

  if (req.method === "GET" && req.url === "/config") {
    return sendJson(res, 200, {
      port: cfg.port,
      availableProviders: cfg.available,
      knownProviders: Object.keys(REGISTRY),
      default: cfg.defaultProvider,
    });
  }

  const isLLM = req.method === "POST" && (req.url === "/chat" || req.url === "/decide");
  const isMemoryAppend = req.method === "POST" && req.url === "/memory";
  const isMemoryReset  = req.method === "POST" && req.url === "/memory/reset";

  if (!isLLM && !isMemoryAppend && !isMemoryReset) {
    res.writeHead(404); res.end("Not found"); return;
  }

  let body = "";
  req.on("data", c => body += c);
  req.on("end", async () => {
    try {
      if (isMemoryReset) {
        resetMemory();
        return sendJson(res, 200, { ok: true });
      }
      const parsed = body ? JSON.parse(body) : {};
      if (isMemoryAppend) {
        appendMemory({
          agentNo: parsed.agentNo,
          header:  parsed.header,
          content: parsed.content || "",
        });
        return sendJson(res, 200, { ok: true });
      }
      // /chat or /decide
      const providerName = parsed.provider || cfg.defaultProvider;
      if (!providerName) throw new Error("no provider configured (fill apiKey in config.json)");
      if (!cfg.available.includes(providerName)) {
        throw new Error(`provider "${providerName}" not configured`);
      }
      const opts = {
        system: parsed.system,
        user: parsed.user,
        tools: req.url === "/decide" ? parsed.tools : null,
        maxTokens: parsed.maxTokens || cfg.maxTokens,
      };
      console.log(`[llm-proxy] ${req.url} provider=${providerName}`);
      const result = await dispatch(providerName, cfg.providers[providerName], opts);
      logPrompt(req.url, providerName, opts, result);
      sendJson(res, 200, result);
    } catch (err) {
      console.error("[llm-proxy] error:", err.message);
      sendJson(res, 500, { error: err.message });
    }
  });
});

function startProxy(port) {
  return new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(port, "127.0.0.1", () => {
      const actual = server.address().port;
      console.log(`[llm-proxy] listening on http://127.0.0.1:${actual}`);
      console.log(`[llm-proxy] configured providers: ${cfg.available.join(", ") || "(none)"}`);
      console.log(`[llm-proxy] default provider: ${cfg.defaultProvider || "(none)"}`);
      Object.keys(REGISTRY).forEach(p => {
        if (!cfg.available.includes(p)) console.log(`[llm-proxy] WARN: ${p} not configured`);
      });
      resolve(actual);
    });
  });
}

if (require.main === module) {
  startProxy(cfg.port).catch(err => {
    console.error("[llm-proxy] startup failed:", err);
    process.exit(1);
  });
}

module.exports = { startProxy };
