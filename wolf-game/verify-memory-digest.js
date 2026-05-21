/* 端到端验证：每天压缩摘要 memory 系统（已模块化到 web/memory.js）
   1.1 LLM 路径 → digest 写入 agent.memoryDigestByDay
   1.2 原始数据 memoryByDay 仍保留（人工 review）
   1.3 _publicContext 暴露 recentMemoryDigests（不再暴露 recentMemory）
   1.4 memory/agent-N.md 含摘要 + <details> 折叠原始
   2   LLM 抛错 → 规则 fallback（按 suspicion 排"信任/怀疑"）
   3   prompt 段长度对比（压缩比断言）
   4   12 agents 并发摘要
   5   ★准确性强化：狼人 fallback 不在"信任/怀疑"里暴露已知队友
   6   ★准确性强化：写 day N 摘要时 LLM 能看到 day N-1 的 digest（承接而非漂移） */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const { spawn } = require("child_process");
const proxy = spawn("node", ["server/llm-proxy.js"], { cwd: __dirname, stdio: ["ignore", "pipe", "pipe"] });
let proxyReady = false;
proxy.stdout.on("data", d => { if (/listening on/.test(d.toString())) proxyReady = true; });
proxy.stderr.on("data", d => process.stderr.write("[proxy] " + d));

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

(async () => {
  for (let i = 0; i < 50 && !proxyReady; i++) await sleep(50);
  if (!proxyReady) throw new Error("llm-proxy not ready after 2.5s");

  await fetch("http://127.0.0.1:3001/memory/reset", { method: "POST" });

  const sandbox = {
    console, setTimeout, clearTimeout, fetch,
    Math, Promise, Error, JSON, Object, Array, Number, Boolean, String, RegExp, Date, Map, Set, Symbol,
    URLSearchParams,
    document: {
      getElementById: () => null,
      querySelectorAll: () => [],
      addEventListener: () => {},
    },
    window: { addEventListener: () => {}, electron: null },
    location: { search: "" },
  };
  sandbox.globalThis = sandbox;
  sandbox.window.fetch = fetch;
  vm.createContext(sandbox);

  const load = (p) => vm.runInContext(fs.readFileSync(path.join(__dirname, p), "utf-8"), sandbox, { filename: p });
  // 加载顺序：agents → llm-adapter（提供 window.LLM_HOOK / window.MEMORY）→ memory → tts → game
  load("web/agents.js");
  vm.runInContext("globalThis.Agent = Agent;", sandbox);
  load("web/llm-adapter.js");
  load("web/memory.js");
  vm.runInContext("globalThis.Memory = Memory;", sandbox);
  load("web/tts.js");
  vm.runInContext("globalThis.TTS = TTS;", sandbox);
  load("web/game.js");
  vm.runInContext("globalThis.Game = Game; globalThis.GAME_GENERATION = GAME_GENERATION;", sandbox);

  sandbox.window.CURRENT_PROVIDER = "claude";
  sandbox.window.LLM_AGENT.use("local");

  // 让 game 实例调 Memory.flushAll（与 game.js dayPhase 末尾一致的调用形式）
  const Memory = sandbox.Memory;
  const flushAll = (g) => Memory.flushAll(g.agents, g.day, g.speechHistory, g.history);

  // ── Test 1: LLM 路径 ──
  sandbox.window.LLM_HOOK.summarize = async ({ system, user }) => {
    if (!/你正在扮演/.test(system)) throw new Error("system prompt missing role-play header");
    if (!/本日个人记忆摘要/.test(system)) throw new Error("system prompt missing digest instruction");
    return "今日 3 号悍跳预言家，我对位真预报查杀 6 号；信任 7/9 号金水链，怀疑 3/11 号节奏可疑；明日带头投 3 号。";
  };

  const game = new sandbox.Game();
  game.reset();
  game.day = 1;
  game.speechHistory = [
    { day: 1, agentNo: 1, publicRole: null,   kind: "day", text: "我先听听大家" },
    { day: 1, agentNo: 3, publicRole: "seer", kind: "day", text: "我3号跳预言家，查 5 号好人" },
    { day: 1, agentNo: 5, publicRole: "seer", kind: "day", text: "我5号才是真预，3号悍跳" },
    { day: 1, agentNo: 7, publicRole: null,   kind: "day", text: "3 号金水保留，5 号节奏怪" },
    { day: 1, agentNo: 9, publicRole: null,   kind: "day", text: "倾向 3 号是真预" },
    { day: 1, agentNo: 11, publicRole: null,  kind: "day", text: "都听我的，投 9 号" },
  ];
  const agent1 = game.agents[0];
  agent1.thinkingLog = [
    { day: 1, kind: "day", thinking: "5 号节奏太急，疑似狼" },
    { day: 1, kind: "vote", thinking: "投 5 号" },
  ];

  await flushAll(game);

  if (!agent1.memoryDigestByDay[1]) throw new Error("FAIL: agent1.memoryDigestByDay[1] empty");
  if (!agent1.memoryDigestByDay[1].includes("3 号悍跳")) throw new Error("FAIL: digest content mismatch (LLM path)");
  console.log("✅ Test 1.1: LLM 路径 → digest 写入 agent.memoryDigestByDay");

  const raw = agent1.memoryByDay[1];
  if (!raw || raw.otherSpeeches.length !== 5) throw new Error(`FAIL: raw otherSpeeches len=${raw?.otherSpeeches?.length}, want 5`);
  if (raw.myActions.length !== 2) throw new Error(`FAIL: raw myActions len=${raw.myActions.length}, want 2`);
  console.log("✅ Test 1.2: 原始数据 memoryByDay 仍保留");

  const ctx = agent1._publicContext(game);
  if (!ctx.me.recentMemoryDigests || ctx.me.recentMemoryDigests.length !== 1) {
    throw new Error(`FAIL: recentMemoryDigests len=${ctx.me.recentMemoryDigests?.length}`);
  }
  if (ctx.me.recentMemoryDigests[0].day !== 1) throw new Error("FAIL: recentMemoryDigests[0].day");
  if (ctx.me.recentMemory !== undefined) throw new Error("FAIL: recentMemory should not be on context anymore");
  console.log("✅ Test 1.3: _publicContext 暴露 recentMemoryDigests（不再暴露原始 recentMemory）");

  await sleep(300);

  const md = fs.readFileSync(path.join(__dirname, "memory/agent-1.md"), "utf-8");
  if (!/^\*\*摘要\*\*：/m.test(md)) throw new Error("FAIL: md missing '摘要' marker");
  if (!/<details><summary>原始材料<\/summary>/.test(md)) throw new Error("FAIL: md missing <details> raw section");
  if (!md.includes("3 号悍跳预言家")) throw new Error("FAIL: md missing digest content");
  if (!md.includes('"我3号跳预言家，查 5 号好人"')) throw new Error("FAIL: md missing raw speech");
  console.log("✅ Test 1.4: memory/agent-1.md 含摘要 + 折叠的原始材料");

  // ── Test 2: Fallback 路径（LLM 抛错）──
  await fetch("http://127.0.0.1:3001/memory/reset", { method: "POST" });
  sandbox.window.LLM_HOOK.summarize = async () => { throw new Error("simulated LLM down"); };
  game.day = 2;
  game.speechHistory = game.speechHistory.concat([
    { day: 2, agentNo: 3, publicRole: "seer", kind: "day", text: "查 7 号好人" },
    { day: 2, agentNo: 5, publicRole: "seer", kind: "day", text: "查 7 号是狼" },
  ]);
  agent1.thinkingLog.push({ day: 2, kind: "day", thinking: "7 号关键，看双预反查" });
  agent1.suspicion = [0, 0.05, 0.05, 0.1, 0.3, 0.85, 0.2, 0.4, 0.1, 0.15, 0.5, 0.7];
  // 强制非狼身份，避免 assignRoles 随机让 agent1 成狼 + 队友恰好是 idx=5/11
  // 触发新 fallback 的"狼人排除队友"逻辑（Test 5 专门测这个）
  agent1.role = "villager";
  agent1.knownWolves = [];

  await flushAll(game);
  const digest2 = agent1.memoryDigestByDay[2];
  if (!digest2) throw new Error("FAIL: fallback digest missing");
  if (!/信任/.test(digest2) || !/怀疑/.test(digest2)) {
    throw new Error(`FAIL: fallback digest format unexpected: ${digest2}`);
  }
  if (!/2号|3号/.test(digest2)) throw new Error(`FAIL: fallback trust list wrong: ${digest2}`);
  if (!/6号|12号/.test(digest2)) throw new Error(`FAIL: fallback suspect list wrong: ${digest2}`);
  console.log(`✅ Test 2: LLM 抛错时走 fallback 规则摘要：${digest2}`);

  // ── Test 3: prompt 段长度对比 ──
  function buildMemoryBlockOLD(recentMemory) {
    if (!recentMemory || recentMemory.length === 0) return "";
    const lines = ["=== 你的个人备忘（最近 3 天，你视角）==="];
    recentMemory.forEach(entry => {
      lines.push(`【第${entry.day}天】`);
      if (entry.otherSpeeches?.length) {
        lines.push("  他人发言：");
        entry.otherSpeeches.forEach(s => {
          const tag = s.publicRole ? `[已跳${s.publicRole}]` : "[未跳]";
          lines.push(`    · ${s.no}号${tag}："${s.text}"`);
        });
      }
      if (entry.myActions?.length) {
        lines.push("  我的行动：");
        entry.myActions.forEach(a => lines.push(`    · ${a.kind}：「${a.thinking}」`));
      }
    });
    lines.push("=== 备忘结束 ===");
    return lines.join("\n");
  }
  const oldRecent = [1, 2].map(d => ({ day: d, ...agent1.memoryByDay[d] }));
  const oldBlock = buildMemoryBlockOLD(oldRecent);

  let capturedUser = null;
  const realFetch = sandbox.fetch;
  sandbox.fetch = sandbox.window.fetch = async (url, opts) => {
    if (typeof url === "string" && url.includes("/chat")) {
      capturedUser = JSON.parse(opts.body).user;
      return { ok: true, json: async () => ({ text: "【思考】x【发言】y" }) };
    }
    return realFetch(url, opts);
  };
  sandbox.window.LLM_HOOK.summarize = async () => "stub";
  await sandbox.window.LLM_HOOK.speak({
    agent: agent1, game: { day: 3, phase: "day" },
    context: agent1._publicContext(game), kind: "day",
  });
  sandbox.fetch = sandbox.window.fetch = realFetch;

  const newBlockMatch = capturedUser.match(/=== 你的个人记忆[\s\S]*?=== 记忆结束[^\n]*===/);
  const newBlock = newBlockMatch ? newBlockMatch[0] : "";

  console.log(`📏 改造前 memory 段长度: ${oldBlock.length} 字符`);
  console.log(`📏 改造后 memory 段长度: ${newBlock.length} 字符`);
  const ratio = (newBlock.length / oldBlock.length * 100).toFixed(1);
  console.log(`📏 压缩比: ${ratio}% (越小越好)`);
  if (newBlock.length >= oldBlock.length) throw new Error("FAIL: new block should be smaller than old block");
  console.log("✅ Test 3: 压缩摘要 prompt 段显著小于原始数据块");

  // ── Test 4: 12 agents 并发 ──
  await fetch("http://127.0.0.1:3001/memory/reset", { method: "POST" });
  sandbox.window.LLM_HOOK.summarize = async () => "并发测试摘要";
  game.day = 3;
  const t0 = Date.now();
  await flushAll(game);
  const elapsed = Date.now() - t0;
  const populated = game.agents.filter(a => a.memoryDigestByDay[3]).length;
  console.log(`✅ Test 4: 12 agents 并发摘要耗时 ${elapsed}ms，已生成 ${populated} 份 digest`);
  if (populated < 10) throw new Error(`FAIL: only ${populated}/12 agents got digest`);

  // ── Test 5: ★准确性强化：狼人 fallback 不暴露已知队友 ──
  // 模拟一只狼，knownWolves=[4,7]（idx），suspicion 中 4 号/7 号最低
  // 旧实现：fallback "信任 5 号、8 号"（暴露自家队友！）
  // 新实现：fallback 应排除 4/7，从其他人里挑信任
  await fetch("http://127.0.0.1:3001/memory/reset", { method: "POST" });
  const wolfGame = new sandbox.Game();
  wolfGame.reset();
  wolfGame.day = 2;
  const wolf = wolfGame.agents[0];
  wolf.role = "wolf";
  wolf.knownWolves = [4, 7];                          // 5 号、8 号是队友
  wolf.suspicion =      [0,    0.5,  0.6,  0.6,  0.0,  0.7,  0.6,  0.0,  0.6,  0.55, 0.8,  0.55];
  //                    自己   2号  3号  4号  5号*  6号  7号  8号*  9号  10号  11号  12号
  // suspicion 最低（除自己外）：idx=4(5号=狼*), idx=7(8号=狼*), idx=1(2号), idx=11(12号)
  // 修复后：5/8 号必须被排除，应该信任 2号/12号
  // suspicion 最高：idx=10(11号=0.8), idx=5(6号=0.7), idx=2/3/6/8 都 0.6
  wolfGame.speechHistory = [{ day: 2, agentNo: 3, publicRole: "seer", kind: "day", text: "我跳预言家" }];
  // mock summarize 也 throw 让走 fallback
  sandbox.window.LLM_HOOK.summarize = async () => { throw new Error("force fallback"); };
  await Memory.flushAll(wolfGame.agents, 2, wolfGame.speechHistory, []);
  const wolfDigest = wolf.memoryDigestByDay[2];
  console.log(`   狼视角 fallback 摘要：${wolfDigest}`);
  if (/5号/.test(wolfDigest) || /8号/.test(wolfDigest)) {
    throw new Error(`FAIL: wolf digest leaks teammate (5号/8号 should not appear): ${wolfDigest}`);
  }
  if (!/2号|12号/.test(wolfDigest)) {
    throw new Error(`FAIL: wolf digest should trust non-teammates (2号 or 12号): ${wolfDigest}`);
  }
  console.log("✅ Test 5: 狼视角 fallback 不暴露已知队友（5/8 号 = knownWolves 已被排除）");

  // ── Test 6: ★准确性强化：写 day N 摘要时 LLM 看到 day N-1 的 digest（承接）──
  await fetch("http://127.0.0.1:3001/memory/reset", { method: "POST" });
  const carryGame = new sandbox.Game();
  carryGame.reset();
  const carryAgent = carryGame.agents[0];
  carryAgent.memoryDigestByDay[1] = "昨日我认为 3 号是真预言家，要继续保护";
  // mock summarize 检查 user prompt 里是否带了昨日摘要
  // 注意：flushAll 并发调用 12 次 summarize，要锁定到 carryAgent (idx=0, 1 号 阿狸) 这次
  let capturedPrevDigest = null;
  sandbox.window.LLM_HOOK.summarize = async ({ system, user }) => {
    if (/1 号 阿狸/.test(system)) {
      const m = user.match(/你昨日的记忆[^：]*：(.+?)\n\n请输出/s);
      capturedPrevDigest = m ? m[1].trim() : null;
    }
    return "今日摘要 承接昨日 3 号判断";
  };
  carryGame.day = 2;
  carryGame.speechHistory = [{ day: 2, agentNo: 3, publicRole: "seer", kind: "day", text: "查 7 号好人" }];
  await Memory.flushAll(carryGame.agents, 2, carryGame.speechHistory, []);
  if (!capturedPrevDigest) throw new Error("FAIL: prev digest not passed to LLM prompt");
  if (!capturedPrevDigest.includes("3 号是真预言家")) {
    throw new Error(`FAIL: prev digest content wrong: ${capturedPrevDigest}`);
  }
  console.log(`✅ Test 6: 写 day 2 摘要时 LLM prompt 含昨日摘要：「${capturedPrevDigest}」`);

  console.log("\n🎉 ALL TESTS PASSED");
  proxy.kill();
  process.exit(0);
})().catch(err => {
  console.error("\n❌ TEST FAILED:", err);
  proxy.kill();
  process.exit(1);
});
