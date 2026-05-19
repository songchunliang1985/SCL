/* =============================================================
   LLM 适配器示例 —— 给 12 人狼人杀接入真实大模型
   =============================================================

   用法（任选一种）：

   方式 A：在 index.html 里在 game.js 之前加一行：
     <script src="llm-adapter.example.js"></script>
   然后在浏览器控制台执行：
     LLM_AGENT.use("claude", { apiKey: "sk-ant-...", model: "claude-opus-4-7" });
     // 或 OpenAI 兼容（含国产模型如 DeepSeek / 通义 / Kimi 等）:
     LLM_AGENT.use("openai", {
       baseURL: "https://api.openai.com/v1",   // 或 DashScope / DeepSeek 的 URL
       apiKey:  "sk-...",
       model:   "gpt-4o-mini",
     });
     // AWS Bedrock 上的 Claude Sonnet 4.6（注意 CORS，仅本地玩，生产请用 bedrock-proxy）：
     LLM_AGENT.use("bedrock", {
       region:          "us-east-1",
       accessKeyId:     "AKIA...",
       secretAccessKey: "...",
       sessionToken:    "...",     // 可选，使用 STS 临时凭证时传
       modelId:         "us.anthropic.claude-sonnet-4-6-20251029-v1:0",  // 或 inference profile
     });
     // 自建后端代理 Bedrock（推荐生产）：
     LLM_AGENT.use("bedrock-proxy", { url: "https://your-backend/bedrock-chat" });
     // 然后点「开始游戏」即可。

   方式 B：直接把上面的对象赋值给 window.LLM_HOOK：
     window.LLM_HOOK = { enabled: true, async speak({agent,game,kind,context}){...} };

   注意：浏览器直连模型 API 会暴露 API Key。生产环境请通过自己的后端代理。
   ============================================================= */

(function () {
  "use strict";

  const ROLE_CN = {
    wolf: "狼人", seer: "预言家", witch: "女巫",
    hunter: "猎人", guard: "守卫", villager: "村民",
  };

  // ===== Prompt 模板 =====
  function buildSystemPrompt(agent) {
    return [
      "你正在扮演中文狼人杀游戏（12 人神局）里的一个 AI 玩家，需要按指定角色和性格做出符合玩家直觉的发言。",
      "",
      "硬性规则：",
      "1. 一句话最多 50 字，整段发言不超过 3 句话，控制在 80 字以内。",
      "2. 必须用第一人称、中文口语化表达。",
      "3. 必须以「N号」自我介绍开头（N 是你的座位号）。",
      "4. 严禁泄露任何上帝视角的信息：作为狼人不能直接说出队友是谁；作为女巫不能说出今晚救/毒了谁，除非剧情驱动；作为守卫不能直接报昨晚守的人。",
      "5. 预言家上跳必须报昨晚的查验结果。",
      "6. 不要使用任何 Markdown、表情符号以外的特殊格式，不要换行。",
      "",
      `你的身份：${agent.no} 号 ${agent.name}，角色 = ${ROLE_CN[agent.role] || agent.role}，性格 = ${agent.personality.name}`,
      "请严格按角色和性格说话。",
    ].join("\n");
  }

  function buildUserPrompt(payload) {
    const { game, context, kind } = payload;
    const phase =
      kind === "sheriff" ? "警长竞选发言" :
      kind === "pk"      ? "PK 发言" :
      kind === "last-words" ? "遗言" :
      `第 ${game.day} 天 白天发言`;

    const aliveList = context.players.filter(p => p.alive)
      .map(p => `${p.no}号${p.publicRole ? `[已跳${ROLE_CN[p.publicRole] || p.publicRole}]` : ""}${p.isSheriff ? "🎖" : ""}`)
      .join("、");

    const reports = context.publicCheckReports.length
      ? context.publicCheckReports.map(r =>
          `${r.from}号验${r.target}号为${r.result === "wolf" ? "狼" : "好人"}`).join("；")
      : "（暂无公开报查）";

    const myInfo = [];
    if (context.me.role === "wolf") {
      myInfo.push(`我的狼队友：${context.me.knownWolves.join("、")}号`);
    }
    if (context.me.role === "seer" && context.me.seerChecks.length) {
      myInfo.push("我历次查验：" + context.me.seerChecks.map(c =>
        `第${c.day}夜 ${c.no}号=${c.isWolf ? "狼" : "好人"}`).join("；"));
    }
    if (context.me.role === "witch") {
      myInfo.push(`我女巫：解药${context.me.witchHasSave ? "在" : "已用"}，毒药${context.me.witchHasPoison ? "在" : "已用"}`);
    }

    return [
      `当前阶段：${phase}`,
      `场上存活：${aliveList}`,
      `公开报查：${reports}`,
      myInfo.length ? "我的隐藏信息：\n" + myInfo.join("\n") : "",
      "",
      "请生成你的发言（直接输出发言内容，不要任何前缀解释）：",
    ].filter(Boolean).join("\n");
  }

  // ===== AWS SigV4 签名（用浏览器原生 Web Crypto，不引 aws-sdk）=====
  async function sha256Hex(input) {
    const data = typeof input === "string" ? new TextEncoder().encode(input) : input;
    const buf = await crypto.subtle.digest("SHA-256", data);
    return [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2, "0")).join("");
  }
  async function hmac(key, data) {
    const keyBuf = typeof key === "string" ? new TextEncoder().encode(key) : key;
    const dataBuf = typeof data === "string" ? new TextEncoder().encode(data) : data;
    const k = await crypto.subtle.importKey("raw", keyBuf, { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
    return new Uint8Array(await crypto.subtle.sign("HMAC", k, dataBuf));
  }
  async function sigV4SignBedrock({ region, accessKeyId, secretAccessKey, sessionToken, modelId, body }) {
    const service = "bedrock";
    const host = `bedrock-runtime.${region}.amazonaws.com`;
    // Bedrock 的模型 ID 含 ":"，需要按 URI 段编码
    const path = `/model/${encodeURIComponent(modelId)}/invoke`;
    const now = new Date();
    const amzDate = now.toISOString().replace(/[:-]|\.\d{3}/g, ""); // 20250929T123456Z
    const dateStamp = amzDate.slice(0, 8);

    const payloadHash = await sha256Hex(body);
    // 参与签名的 header（小写，按名字字典序）
    const signedHeadersMap = {
      "content-type":         "application/json",
      "host":                 host,
      "x-amz-content-sha256": payloadHash,
      "x-amz-date":           amzDate,
    };
    if (sessionToken) signedHeadersMap["x-amz-security-token"] = sessionToken;
    const sortedNames = Object.keys(signedHeadersMap).sort();
    const canonicalHeaders = sortedNames.map(h => `${h}:${signedHeadersMap[h]}`).join("\n") + "\n";
    const signedHeaders = sortedNames.join(";");

    const canonicalRequest = ["POST", path, "", canonicalHeaders, signedHeaders, payloadHash].join("\n");
    const algorithm = "AWS4-HMAC-SHA256";
    const credentialScope = `${dateStamp}/${region}/${service}/aws4_request`;
    const stringToSign = [algorithm, amzDate, credentialScope, await sha256Hex(canonicalRequest)].join("\n");

    let k = await hmac("AWS4" + secretAccessKey, dateStamp);
    k = await hmac(k, region);
    k = await hmac(k, service);
    k = await hmac(k, "aws4_request");
    const sigBytes = await hmac(k, stringToSign);
    const signature = [...sigBytes].map(b => b.toString(16).padStart(2, "0")).join("");

    const authorization = `${algorithm} Credential=${accessKeyId}/${credentialScope}, SignedHeaders=${signedHeaders}, Signature=${signature}`;

    // 实际请求头：浏览器禁止手动设 Host（fetch 自动加，签名包含 host AWS 端会校验）
    const fetchHeaders = {
      "Content-Type":          "application/json",
      "X-Amz-Content-Sha256":  payloadHash,
      "X-Amz-Date":            amzDate,
      "Authorization":         authorization,
    };
    if (sessionToken) fetchHeaders["X-Amz-Security-Token"] = sessionToken;
    return { url: `https://${host}${path}`, headers: fetchHeaders };
  }

  // ===== Provider 实现 =====
  const providers = {
    /* ============ Anthropic Claude API ============ */
    claude({ apiKey, model = "claude-opus-4-7", baseURL = "https://api.anthropic.com" }) {
      return async function speak(payload) {
        const resp = await fetch(`${baseURL}/v1/messages`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "x-api-key": apiKey,
            "anthropic-version": "2023-06-01",
            "anthropic-dangerous-direct-browser-access": "true",
          },
          body: JSON.stringify({
            model,
            max_tokens: 200,
            system: buildSystemPrompt(payload.agent),
            messages: [{ role: "user", content: buildUserPrompt(payload) }],
          }),
        });
        if (!resp.ok) throw new Error(`Claude API ${resp.status}: ${await resp.text()}`);
        const data = await resp.json();
        return data.content?.[0]?.text || "";
      };
    },

    /* ============ OpenAI 兼容（含国产模型）============
       适配 OpenAI / DeepSeek / DashScope-Compatible / Kimi / Together / OpenRouter 等 */
    openai({ apiKey, model = "gpt-4o-mini", baseURL = "https://api.openai.com/v1" }) {
      return async function speak(payload) {
        const resp = await fetch(`${baseURL}/chat/completions`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${apiKey}`,
          },
          body: JSON.stringify({
            model,
            temperature: 0.85,
            max_tokens: 200,
            messages: [
              { role: "system", content: buildSystemPrompt(payload.agent) },
              { role: "user",   content: buildUserPrompt(payload) },
            ],
          }),
        });
        if (!resp.ok) throw new Error(`OpenAI API ${resp.status}: ${await resp.text()}`);
        const data = await resp.json();
        return data.choices?.[0]?.message?.content || "";
      };
    },

    /* ============ AWS Bedrock 直连（含 SigV4 签名）============
       注意：浏览器直连 Bedrock 会撞 CORS（Bedrock 端默认不开），仅适合：
         · 通过 CORS 代理转发
         · 本地用 Chrome --disable-web-security 玩
       生产请用 bedrock-proxy（后端 boto3 / AWS SDK 调 Bedrock）。
       常见模型 ID：
         · us.anthropic.claude-sonnet-4-6-20251029-v1:0   (Sonnet 4.6 跨区 inference profile，推荐)
         · us.anthropic.claude-sonnet-4-5-20250929-v1:0   (Sonnet 4.5 inference profile)
         · us.anthropic.claude-opus-4-7-...               (Opus 4.7 — 如 region 已开放)
         · 实际 modelId 各 region 不同，用 `aws bedrock list-inference-profiles --region <r>` 查询
    */
    bedrock({ region = "us-east-1", accessKeyId, secretAccessKey, sessionToken, modelId, anthropicVersion = "bedrock-2023-05-31" }) {
      if (!accessKeyId || !secretAccessKey || !modelId) {
        throw new Error("bedrock provider: accessKeyId / secretAccessKey / modelId 必填");
      }
      return async function speak(payload) {
        const body = JSON.stringify({
          anthropic_version: anthropicVersion,
          max_tokens: 200,
          system: buildSystemPrompt(payload.agent),
          messages: [{ role: "user", content: buildUserPrompt(payload) }],
        });
        const { url, headers } = await sigV4SignBedrock({
          region, accessKeyId, secretAccessKey, sessionToken, modelId, body,
        });
        const resp = await fetch(url, { method: "POST", headers, body });
        if (!resp.ok) throw new Error(`Bedrock ${resp.status}: ${await resp.text()}`);
        const data = await resp.json();
        return data.content?.[0]?.text || "";
      };
    },

    /* ============ Bedrock 后端代理 ============
       推荐生产用。前端只发明文，后端用 AWS SDK 签名并转发 Bedrock。
       服务端实现示例（Node.js + @aws-sdk/client-bedrock-runtime）：

         import { BedrockRuntimeClient, InvokeModelCommand } from "@aws-sdk/client-bedrock-runtime";
         const client = new BedrockRuntimeClient({ region: "us-east-1" });
         app.post("/bedrock-chat", async (req, res) => {
           const { system, user } = req.body;
           const cmd = new InvokeModelCommand({
             modelId: "us.anthropic.claude-sonnet-4-6-20251029-v1:0",
             contentType: "application/json",
             body: JSON.stringify({
               anthropic_version: "bedrock-2023-05-31",
               max_tokens: 200,
               system,
               messages: [{ role: "user", content: user }],
             }),
           });
           const r = await client.send(cmd);
           const data = JSON.parse(new TextDecoder().decode(r.body));
           res.json({ text: data.content?.[0]?.text || "" });
         });
    */
    "bedrock-proxy"({ url }) {
      return async function speak(payload) {
        const resp = await fetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            system: buildSystemPrompt(payload.agent),
            user:   buildUserPrompt(payload),
            // 透传一些上下文方便后端调参 / 模型选择
            meta: { agent: payload.agent.name, no: payload.agent.no, role: payload.agent.role, kind: payload.kind, day: payload.game.day },
          }),
        });
        if (!resp.ok) throw new Error(`Bedrock proxy ${resp.status}: ${await resp.text()}`);
        const data = await resp.json();
        return data.text || data.content || "";
      };
    },

    /* ============ 自己的代理服务端（通用）============
       推荐生产环境用这个，把 API Key 放在你自己后端，前端只请求你的 /chat */
    proxy({ url }) {
      return async function speak(payload) {
        const resp = await fetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            system: buildSystemPrompt(payload.agent),
            user:   buildUserPrompt(payload),
          }),
        });
        if (!resp.ok) throw new Error(`Proxy ${resp.status}: ${await resp.text()}`);
        const data = await resp.json();
        return data.text || data.content || "";
      };
    },
  };

  // ===== 暴露开关 =====
  window.LLM_AGENT = {
    use(providerName, config) {
      const factory = providers[providerName];
      if (!factory) throw new Error("unknown provider: " + providerName);
      const speakFn = factory(config);
      window.LLM_HOOK = {
        enabled: true,
        async speak(payload) {
          // 简单超时保护，5s 没拿到 LLM 文本就回退规则版
          return await Promise.race([
            speakFn(payload),
            new Promise((_, rej) => setTimeout(() => rej(new Error("LLM timeout 5s")), 5000)),
          ]);
        },
        // decide 留空，决策类继续走规则；如需接入参考上面的 speak 模式
      };
      console.log(`[LLM_AGENT] enabled with ${providerName}, model=${config.model || "default"}`);
    },
    disable() {
      if (window.LLM_HOOK) window.LLM_HOOK.enabled = false;
      console.log("[LLM_AGENT] disabled, fallback to rule-based.");
    },
  };
})();
