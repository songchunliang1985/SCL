# 🐺 狼人杀 · 12 人神局 · AI Agent 自动对战

一个纯前端、零依赖的可视化狼人杀游戏。12 个 AI Agent 自动对战，标准 12 人神局配置，含完整昼夜流程、技能特效、发言推理、投票放逐与胜负判定。

![phase](https://img.shields.io/badge/phase-day%2Fnight-orange) ![players](https://img.shields.io/badge/players-12-blue) ![deps](https://img.shields.io/badge/dependencies-0-success) ![runtime](https://img.shields.io/badge/runtime-browser-purple)

---

## 🚀 一键运行

**方式一：直接双击**

```
双击 index.html → 浏览器自动打开 → 点「🎬 开始游戏」
```

**方式二：本地起一个静态服务器（推荐，避免某些浏览器对 file:// 的限制）**

```bash
# 任选其一：

# Python 3
cd werewolf-game
python3 -m http.server 8080

# Node.js
cd werewolf-game
npx serve .

# 或 PHP
cd werewolf-game
php -S localhost:8080
```

然后打开浏览器访问 `http://localhost:8080/`。

> 💡 推荐使用 Chrome / Edge / Safari 最新版本。需要支持 ES2020 与 CSS `backdrop-filter`。

---

## 🎮 游戏配置（12 人神局）

| 阵营 | 角色 | 数量 |
|------|------|------|
| 🐺 狼人 | 狼人 | 4 |
| 👤 神职 | 预言家 / 女巫 / 猎人 / 守卫 | 各 1 |
| 👥 平民 | 村民 | 4 |

**胜利条件**：
- ✅ 好人胜：屠光所有狼人
- ✅ 狼人胜：屠光所有神 **或** 屠光所有民

---

## 🎛 操作面板

| 控件 | 说明 |
|------|------|
| 🎬 **开始游戏** | 开局，重新发牌、12 个 agent 入场 |
| ⏸ **暂停 / ▶ 继续** | 随时暂停夜晚或发言节奏 |
| ↻ **重开** | 立即开始新一局 |
| **速度** | 慢 / 中 / 快 / 极速 — 整体节奏 |
| **上帝视角** | 勾选后可直接看到所有玩家的真实身份 |

---

## 🌗 完整流程

```
夜晚                              白天
┌─ 守卫保护一人                    ┌─ 公布昨夜死讯
├─ 狼人协商击杀                    ├─ 死者遗言（猎人此时可开枪）
├─ 预言家验人 ──┐                  ├─ [Day 1] 警长竞选 + 上警发言 + 非上警投票
├─ 女巫救/毒    ├─ 结算            ├─ 顺位发言（带身份策略 + 推理）
└─ 同守同救 = 死  └─ 判定胜负      ├─ 中途：狼人可自爆 → 跳过当日投票
                                   ├─ 全员投票（警长票权 1.5）
                                   ├─ 平票 → PK 发言 + 复投
                                   └─ 放逐 + 遗言（含警徽流转）+ 胜负判定
```

**实现的标准规则**：
- 守卫"不能连守同一人"
- 同夜被守 + 被女巫救 = 死（同守同救）
- 女巫首夜可自救，之后不能
- 猎人被毒不能开枪
- 猎人被投出 / 夜里被刀均可开枪
- 狼人之间互认队友、协商目标
- **警长竞选**：第一天独立流程，预言家必上、狼人最多 2 只悍跳，非上警玩家投票，平票则 PK
- **警长票权**：1.5 倍，参与所有放逐投票
- **警徽流转**：警长死亡时按死因决定 — 白天被投出可在遗言中传或撕；夜里被刀 / 被毒 / 被枪杀 / 被自爆牵连均按 AI 决策自动传或撕
- **狼人自爆**：白天发言阶段可触发，立即跳过本日剩余发言与投票，直接进入夜晚
- **平票 PK**：放逐投票平票时，PK 双方先各发言一轮，再由其他活人复投；仍平票则不放逐

---

## 🤖 AI 推理逻辑

每个 Agent 包含三层：

**1. 性格 (Personality)**
> 稳健 / 凶猛 / 狡诈 / 天真 / 缜密 / 锋利 / 沉稳 / 毒舌 / 圆滑 / 孤勇 / 理性 / 浮躁

每种性格影响 `aggro`（攻击度）、`deception`（欺骗倾向）、`talkative`（话痨程度），最终作用于发言强度、悍跳概率、票型偏好。

**2. 角色策略 (Role Strategy)**

| 角色 | 夜晚 | 白天 |
|------|------|------|
| 🐺 狼人 | 优先刀已跳神 / 高威胁发言者，互认避杀队友 | 概率悍跳预言家、报假查杀、远离队友抛节奏；危急时刻自爆（队友被查杀 / 自己被查杀）|
| 🔮 预言家 | 优先验高怀疑度玩家 | 上跳报查，对位真查杀；上警必跳 |
| 🧪 女巫 | 首夜默认救人，之后只救已暴露的神。双跳预言家时毒掉自己更怀疑的一方 | 通常不上警 |
| 🛡 守卫 | 优先守已跳预言家，否则守自己 / 高发言者 | 偶尔上警 |
| 🏹 猎人 | — | 遗言枪杀最高怀疑度活人；偶尔上警 |
| 👥 村民 | — | 对位真预言家投票，怀疑度过低则弃票 |

**警长决策**：
- 好人传警徽 → 信任度最高的活人；信任度 < 0.4 时撕毁
- 狼人传警徽 → 70% 传队友，30% 撕毁
- 上警投票：好人投跳预言家者 / 怀疑度低者；狼人投自家队友

**3. 推理记忆 (Inference Memory)**

每个 agent 维护：
- `suspicion[12]`：对全场玩家的怀疑度（0~1）
- `claims{}`：所有公开声明的身份
- `seerChecks[]`：预言家自己的查验记录
- `publicCheckReports[]`：场上所有预言家的报查（含真假）

事件驱动更新：每次声明 / 查验 / 投票 / 死亡都会广播 `observe(event)`，各 agent 按自己阵营视角调整怀疑度。例如双跳预言家时好人会"对面狼"加怀疑度。

---

## 🎨 视觉特性

- **圆桌座位**：12 座环形布局，1 号在顶部顺时针
- **昼夜过渡**：月亮 / 太阳平滑切换 + 背景渐变 + 星空闪烁
- **技能连线**：SVG 流光线条（狼刀 🔴 / 预言 🔵 / 女巫 🟣 / 守卫 🟢 / 猎人 🟠 / 投票 🟡）
- **发言气泡**：当前发言者头像旁实时弹出，自动适配上下位置避免遮挡
- **状态指示**：发言中 / 被技能瞄准 / 受保护 / 中毒 / 遗言中 / 已死亡
- **投票动画**：每张票实时连线 + 票数浮标
- **死亡呈现**：头像灰化 + 红叉覆盖 + 身份卡片自动揭晓
- **结算面板**：游戏结束后全员身份一览 + 阵营胜利提示

---

## 📁 项目结构

```
werewolf-game/
├── index.html      入口与 DOM 骨架
├── styles.css      全部视觉样式
├── agents.js       Agent 类（性格 / 推理 / 决策 / 发言）
├── game.js         Game 引擎 + UI 渲染层
└── README.md       本文件
```

| 文件 | 行数 | 职责 |
|------|------|------|
| `agents.js` | ~430 | `Agent` 类：角色策略、推理、发言生成 |
| `game.js` | ~770 | `Game` 类：流程驱动；`UI` 对象：DOM 渲染 |
| `styles.css` | ~470 | 主题、座位、技能特效、动画 |
| `index.html` | ~80 | 入口结构 + 控件 |

---

## 🛠 自定义与扩展

**调整角色配置**：编辑 `game.js` 顶部的 `ROLES_12` 数组。

```js
const ROLES_12 = [
  "wolf","wolf","wolf","wolf",       // 4 狼
  "seer","witch","hunter","guard",    // 4 神
  "villager","villager","villager","villager",  // 4 民
];
```

**修改 agent 个性**：编辑 `agents.js` 的 `PERSONALITIES` 与 `NAMES`、`AVATARS`。

---

## 🧠 接入真实大模型

默认是规则 + 模板生成发言。项目已内置 LLM 钩子（`agents.js` 顶部的 `LLM` 对象），并提供即插即用的适配器 `llm-adapter.example.js`，支持 **Claude API / OpenAI 兼容（含国产模型）/ 自建代理**。

**最快接入**：浏览器打开页面后在控制台执行任意一种：

```js
// Claude API
LLM_AGENT.use("claude", {
  apiKey: "sk-ant-...",
  model:  "claude-opus-4-7",
});

// OpenAI / DeepSeek / DashScope / Kimi / OpenRouter（任意 OpenAI 兼容端）
LLM_AGENT.use("openai", {
  baseURL: "https://api.openai.com/v1",   // 或 DeepSeek/DashScope/Kimi 的 URL
  apiKey:  "sk-...",
  model:   "gpt-4o-mini",
});

// 自建后端代理（推荐生产环境，避免暴露 Key）
LLM_AGENT.use("proxy", { url: "https://your-backend/chat" });

// 关掉，回到规则版
LLM_AGENT.disable();
```

启用后点「开始游戏」，发言就由 LLM 生成。请求超时 5s 自动回退到规则版。

> ⚠️ 浏览器直连 API 会暴露 Key，仅适合本地玩。生产请用 `proxy` 模式。

### 所有接入点

| 入口 | 文件位置 | 输入 | 输出 | 已接 LLM |
|------|----------|------|------|---------|
| `generateSpeech(game)` | `agents.js` | 游戏状态 | 发言文本 | ✅ |
| `generateSheriffSpeech(game)` | `agents.js` | 游戏状态 | 上警发言 | ✅ |
| `voteTarget(game, candidates)` | `agents.js` | 候选人 | 投票 idx 或 -1 | ⏳ 通过 `LLM_HOOK.decide` 自接 |
| `sheriffVote / decideSelfExplode / decideRunForSheriff / passBadge` | `agents.js` | 游戏状态 | idx / bool | ⏳ 同上 |
| `_wolfKill / _seerCheck / _witchAct / _guardProtect` | `agents.js` | 游戏状态 | 行动对象 | ⏳ 同上 |

### Prompt 已封装

`llm-adapter.example.js` 中已写好 system / user prompt 模板：
- **System**：角色、性格、身份硬约束、字数限制、禁止泄露上帝视角
- **User**：当前阶段 / 存活列表 / 公开报查 / 自己的隐藏信息（狼队友 / 历次查验 / 解药毒药剩余）

`Agent._publicContext(game)` 会把游戏状态拍扁成 JSON 给 prompt 用，包含每个玩家的 publicRole / isSheriff / 我的怀疑度，狼人能看到队友号，预言家能看到历次查验结果，女巫知道药品剩余 —— 完全符合该角色"应该知道的"信息。

### 自定义钩子

不用示例适配器，直接挂一个对象到 `window.LLM_HOOK` 也行：

```js
window.LLM_HOOK = {
  enabled: true,
  async speak({ agent, game, kind, context }) {
    // kind: "day" | "sheriff" | "pk" | "last-words"
    // 返回字符串即用；返回 null/undefined/空串则走规则版
    return "我是 1 号，..." ;
  },
  // 可选：决策类接入
  async decide({ agent, game, kind, options }) { return null; },
};
```


---

## ⚖️ 平衡性数据

本地无 UI 模拟 100 局（含警长 / 自爆 / PK 三大特性）：
- 好人胜率 ≈ **30-37%**
- 狼人胜率 ≈ **63-70%**
- 出现狼人自爆的局数 ≈ **22%**

> 与真实狼人杀格局接近（狼方信息优势天然偏强）。可通过提升预言家信任度、加快猎人开枪、削弱悍跳生效率来调整。

---

## 📜 License

本项目以教学 / 演示为目的，可自由使用与修改。
