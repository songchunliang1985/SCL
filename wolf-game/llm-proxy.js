/**
 * LLM 多 provider 代理
 * 4 个后端通用入口：bedrock / deepseek / claude / openai
 *
 * 启动：node llm-proxy.js
 *
 * 端点：
 *   POST /chat    body: { provider?, system, user, maxTokens? }      → { text }
 *   POST /decide  body: { provider?, system, user, tools, maxTokens?} → { toolName, input }
 *   GET  /config                                                      → { availableProviders, default }
 *
 * 前端始终传 Anthropic 风格 tools，proxy 内部按需转换为 OpenAI function tools。
 */

"use strict";

const http = require("http");
const fs = require("fs");
const path = require("path");
const {
  BedrockRuntimeClient,
  InvokeModelCommand,
} = require("@aws-sdk/client-bedrock-runtime");

// ─── 读取配置 ──────────────────────────────────────────────────
const CONFIG_PATH = path.join(__dirname, "config.json");
if (!fs.existsSync(CONFIG_PATH)) {
  console.error("[llm-proxy] config.json not found.");
  process.exit(1);
}
// ─── Prompt 日志 ──────────────────────────────────────────────
const LOG_FILE = path.join(__dirname, "prompts.log");
function logPrompt(endpoint, provider, reqBody, response) {
  const ts = new Date().toISOString().slice(0, 19).replace("T", " ");
  const sep = "=".repeat(90);
  const lines = [
    sep,
    `[${ts}] ${endpoint}  provider=${provider}`,
    sep,
    "── SYSTEM ──",
    reqBody.system || "(empty)",
    "",
    "── USER ──",
    reqBody.user || "(empty)",
  ];
  if (reqBody.tools && reqBody.tools.length) {
    lines.push("", "── TOOLS ──", reqBody.tools.map(t => `· ${t.name}`).join("\n"));
  }
  lines.push("", "── RESPONSE ──", JSON.stringify(response, null, 2), "", "");
  try {
    fs.appendFileSync(LOG_FILE, lines.join("\n"), "utf-8");
  } catch (e) {
    console.error("[llm-proxy] prompt log write failed:", e.message);
  }
}

// ─── 全局可变 state（支持 hot reload） ─────────────────────────
let config = {};
let PROVIDERS = {};
let AVAILABLE = [];
let DEFAULT_PROVIDER = "bedrock";
let PORT = 3001;
let MAX_TOKENS = 200;
let bedrockClient = null;

function isConfigured(name) {
  const p = PROVIDERS[name];
  if (!p) return false;
  if (name === "bedrock") {
    return p.accessKeyId && !/^FILL|^AKIA_YOUR/i.test(p.accessKeyId);
  }
  return p.apiKey && !/FILL|YOUR/i.test(p.apiKey);
}

function loadConfig(isReload = false) {
  try {
    config = JSON.parse(fs.readFileSync(CONFIG_PATH, "utf-8"));
  } catch (e) {
    console.error(`[llm-proxy] config.json parse error: ${e.message}`);
    if (!isReload) process.exit(1);
    return;   // 重载失败时保留旧配置
  }
  PROVIDERS = config.providers || {};
  if (!isReload) {
    // 首次加载才设置 PORT / MAX_TOKENS（运行中改 port 没意义）
    PORT = config.port || 3001;
    MAX_TOKENS = config.maxTokens || 200;
  }
  DEFAULT_PROVIDER = config.defaultProvider || "bedrock";
  AVAILABLE = ["bedrock", "deepseek", "claude", "openai"].filter(isConfigured);
  // 重建 Bedrock client（凭据可能改了）
  if (isConfigured("bedrock")) {
    const b = PROVIDERS.bedrock;
    bedrockClient = new BedrockRuntimeClient({
      region: b.region,
      credentials: { accessKeyId: b.accessKeyId, secretAccessKey: b.secretAccessKey },
    });
  } else {
    bedrockClient = null;
  }
  if (isReload) {
    console.log(`[llm-proxy] config reloaded | configured: ${AVAILABLE.join(", ") || "(none)"} | default: ${DEFAULT_PROVIDER}`);
  }
}

loadConfig(false);

// ─── Hot reload：监听 config.json 修改 ─────────────────────────
let reloadDebounceTimer = null;
fs.watchFile(CONFIG_PATH, { interval: 1000 }, (curr, prev) => {
  if (curr.mtimeMs === prev.mtimeMs) return;
  clearTimeout(reloadDebounceTimer);
  // 节流：编辑器保存可能触发多次 stat
  reloadDebounceTimer = setTimeout(() => loadConfig(true), 300);
});

// ─── Anthropic tools → OpenAI function tools 转换 ──────────────
function toOpenAITools(tools) {
  return tools.map(t => ({
    type: "function",
    function: { name: t.name, description: t.description, parameters: t.input_schema },
  }));
}

// ─── 4 个 invokeXxx 适配函数 ───────────────────────────────────

async function invokeBedrock({ system, user, tools, maxTokens }) {
  if (!bedrockClient) throw new Error("bedrock not configured");
  const body = {
    anthropic_version: "bedrock-2023-05-31",
    max_tokens: maxTokens || MAX_TOKENS,
    system,
    messages: [{ role: "user", content: user }],
  };
  if (tools?.length) { body.tools = tools; body.tool_choice = { type: "any" }; }

  const cmd = new InvokeModelCommand({
    modelId: PROVIDERS.bedrock.model,
    contentType: "application/json",
    accept: "application/json",
    body: JSON.stringify(body),
  });
  const resp = await bedrockClient.send(cmd);
  const result = JSON.parse(Buffer.from(resp.body).toString("utf-8"));

  if (tools?.length) {
    const tu = (result.content || []).find(c => c.type === "tool_use");
    return { toolName: tu?.name || null, input: tu?.input || null };
  }
  const txt = (result.content || []).find(c => c.type === "text");
  return { text: txt?.text || "" };
}

async function invokeClaude({ system, user, tools, maxTokens }) {
  const p = PROVIDERS.claude;
  const body = {
    model: p.model,
    max_tokens: maxTokens || MAX_TOKENS,
    system,
    messages: [{ role: "user", content: user }],
  };
  if (tools?.length) { body.tools = tools; body.tool_choice = { type: "any" }; }

  const resp = await fetch(`${p.baseURL}/v1/messages`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-api-key": p.apiKey,
      "anthropic-version": "2023-06-01",
    },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw new Error(`Claude API ${resp.status}: ${await resp.text()}`);
  const data = await resp.json();

  if (tools?.length) {
    const tu = (data.content || []).find(c => c.type === "tool_use");
    return { toolName: tu?.name || null, input: tu?.input || null };
  }
  const txt = (data.content || []).find(c => c.type === "text");
  return { text: txt?.text || "" };
}

async function invokeOpenAICompat({ provider, system, user, tools, maxTokens }) {
  const p = PROVIDERS[provider];
  const body = {
    model: p.model,
    messages: [
      { role: "system", content: system },
      { role: "user", content: user },
    ],
    max_tokens: maxTokens || MAX_TOKENS,
    temperature: 0.8,
  };
  if (tools?.length) {
    body.tools = toOpenAITools(tools);
    body.tool_choice = "required";
  }
  // DeepSeek V4 系列默认开 thinking（即 reasoner），但 thinking 模式不支持 tool_calls。
  // 我们的 speak 用文本层 CoT（【思考】+【发言】），decide 用 tool_use —— 两者都不需要内部 thinking。
  // 显式 disable，避免 400 "does not support this tool_choice"。
  if (provider === "deepseek") {
    body.thinking = { type: "disabled" };
  }

  const resp = await fetch(`${p.baseURL}/chat/completions`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${p.apiKey}`,
    },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw new Error(`${provider} ${resp.status}: ${await resp.text()}`);
  const data = await resp.json();

  if (tools?.length) {
    const tc = data.choices?.[0]?.message?.tool_calls?.[0];
    if (!tc) return { toolName: null, input: null };
    let input = null;
    try { input = JSON.parse(tc.function.arguments); } catch {}
    return { toolName: tc.function.name, input };
  }
  return { text: data.choices?.[0]?.message?.content || "" };
}

const invokeDeepSeek = (opts) => invokeOpenAICompat({ ...opts, provider: "deepseek" });
const invokeOpenAI   = (opts) => invokeOpenAICompat({ ...opts, provider: "openai" });

async function dispatch(provider, opts) {
  if (!AVAILABLE.includes(provider)) {
    throw new Error(`provider "${provider}" not configured (fill apiKey in config.json)`);
  }
  switch (provider) {
    case "bedrock":  return invokeBedrock(opts);
    case "deepseek": return invokeDeepSeek(opts);
    case "claude":   return invokeClaude(opts);
    case "openai":   return invokeOpenAI(opts);
    default: throw new Error(`unknown provider: ${provider}`);
  }
}

// ─── HTTP server ──────────────────────────────────────────────
function sendJson(res, status, obj) {
  res.writeHead(status, { "Content-Type": "application/json; charset=utf-8" });
  res.end(JSON.stringify(obj));
}

const server = http.createServer(async (req, res) => {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");
  if (req.method === "OPTIONS") { res.writeHead(204); res.end(); return; }

  // GET /config — 不返回 secret，仅声明哪些 provider 已配
  if (req.method === "GET" && req.url === "/config") {
    return sendJson(res, 200, {
      availableProviders: AVAILABLE,
      default: AVAILABLE.includes(DEFAULT_PROVIDER) ? DEFAULT_PROVIDER : (AVAILABLE[0] || null),
    });
  }

  if (req.method !== "POST" || (req.url !== "/chat" && req.url !== "/decide")) {
    res.writeHead(404); res.end("Not found"); return;
  }

  let body = "";
  req.on("data", c => body += c);
  req.on("end", async () => {
    try {
      const parsed = JSON.parse(body);
      const provider = parsed.provider || DEFAULT_PROVIDER;
      const opts = {
        system: parsed.system,
        user: parsed.user,
        tools: req.url === "/decide" ? parsed.tools : null,
        maxTokens: parsed.maxTokens,
      };
      console.log(`[llm-proxy] ${req.url} provider=${provider}`);
      const result = await dispatch(provider, opts);
      logPrompt(req.url, provider, opts, result);
      sendJson(res, 200, result);
    } catch (err) {
      console.error("[llm-proxy] error:", err.message);
      sendJson(res, 500, { error: err.message });
    }
  });
});

// V2.10：暴露为函数，供 Electron main.js 和 CLI 两用
function startProxy(port) {
  return new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(port, "127.0.0.1", () => {
      const actualPort = server.address().port;
      console.log(`[llm-proxy] listening on http://127.0.0.1:${actualPort}`);
      console.log(`[llm-proxy] configured providers: ${AVAILABLE.join(", ") || "(none)"}`);
      console.log(`[llm-proxy] default provider: ${DEFAULT_PROVIDER}`);
      ["bedrock", "deepseek", "claude", "openai"].forEach(p => {
        if (!AVAILABLE.includes(p)) console.log(`[llm-proxy] WARN: ${p} not configured`);
      });
      resolve(actualPort);
    });
  });
}

if (require.main === module) {
  // CLI 模式：用 config.json 中的 PORT
  startProxy(PORT).catch(err => {
    console.error("[llm-proxy] startup failed:", err);
    process.exit(1);
  });
}

module.exports = { startProxy };
