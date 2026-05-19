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

    /* ============ 自己的代理服务端 ============
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
