# 狼人杀 · 12 人神局 · AI Agent 自动对战

12 个 LLM 驱动的 AI Agent 自动玩一局 12 人神局狼人杀（4 狼 + 预言家 + 女巫 + 猎人 + 守卫 + 4 民）。
本地 Node 代理统一对接 4 个 LLM 后端：**Bedrock / DeepSeek / Claude API / OpenAI**，前端 UI 实时切换。

```
┌──────────────────┐    HTTP    ┌──────────────────┐    HTTPS   ┌────────────────────┐
│  index.html      │ ────────►  │  llm-proxy.js    │ ─────────► │  Bedrock / Claude  │
│  (前端 UI + 引擎) │  :3001     │  (provider 路由)  │            │  / DeepSeek / OpenAI│
└──────────────────┘            └──────────────────┘            └────────────────────┘
        ▲                                ▲
        │  pywebview 窗口（可选）          │  读取 config.json（支持热重载）
        └──── launcher.py ────────────────┘
```

---

## 目录

- [快速开始](#快速开始)
- [环境要求](#环境要求)
- [安装](#安装)
- [配置 config.json](#配置-configjson)
- [启动](#启动)
- [使用说明](#使用说明)
- [文件结构](#文件结构)
- [HTTP API](#http-api)
- [常见问题](#常见问题)

---

## 快速开始

```bash
# 1. 安装依赖（只用 DeepSeek/Claude/OpenAI 可跳过）
npm install

# 2. 编辑 config.json，至少填入一个 provider 的 apiKey
#    （未填的 provider 在 UI 下拉框中会显示「(未配置)」）

# 3. 启动代理
node llm-proxy.js

# 4. 用浏览器打开 index.html
#    或者改用 Python 套壳窗口：python launcher.py
```

`config.json` 里至少有一个 provider 被识别为已配置，前端「开始游戏」按钮才会解锁。

---

## 环境要求

| 组件 | 版本 | 是否必需 |
|------|------|----------|
| Node.js | ≥ 18（自带 `fetch`） | ✅ |
| 浏览器 | Chrome / Edge / Firefox 最新版 | ✅（二选一） |
| Python | ≥ 3.8 + `pywebview` | 仅 `launcher.py` 模式需要 |
| AWS 凭据 | IAM accessKey + Bedrock 模型权限 | 仅用 Bedrock 时需要 |

---

## 安装

```bash
cd wolf-game
npm install        # 仅安装 @aws-sdk/client-bedrock-runtime
```

> 如果完全不用 Bedrock，`npm install` 也可以跳过 —— 代理启动时 Bedrock 因缺凭据被识别为未配置，其余 provider 走原生 `fetch`，不需要 npm 依赖。

如需用 Python 套壳窗口（隐藏 console、绕开 Electron / EDR 拦截）：

```bash
pip install pywebview
```

---

## 配置 config.json

`config.json` 长这样：

```json
{
  "defaultProvider": "bedrock",
  "port": 3001,
  "maxTokens": 200,
  "providers": {
    "bedrock": {
      "region": "us-west-2",
      "accessKeyId": "AKIA...",
      "secretAccessKey": "...",
      "model": "anthropic.claude-sonnet-4-5-20250929-v1:0"
    },
    "deepseek": {
      "apiKey": "sk-...",
      "baseURL": "https://api.deepseek.com/v1",
      "model": "deepseek-chat"
    },
    "claude": {
      "apiKey": "sk-ant-...",
      "baseURL": "https://api.anthropic.com",
      "model": "claude-sonnet-4-5-20250929"
    },
    "openai": {
      "apiKey": "sk-...",
      "baseURL": "https://api.openai.com/v1",
      "model": "gpt-4o-mini"
    }
  }
}
```

字段说明：

- `defaultProvider`：前端没指定 provider 时的默认值。
- `port`：代理监听端口（默认 3001）。
- `maxTokens`：默认 200，发言/决策时前端会覆盖成 500（留给【思考】段）。
- 各 provider：
  - **bedrock**：`region` + `accessKeyId` + `secretAccessKey` + `model`（modelId，如 `anthropic.claude-sonnet-4-5-20250929-v1:0`）
  - **deepseek / openai**：OpenAI 兼容协议，`baseURL` + `apiKey` + `model`
  - **claude**：原生 Anthropic API，`baseURL` + `apiKey` + `model`

**重要**：

1. 配置文件里出现 `FILL`、`YOUR`、`AKIA_YOUR` 等占位符会被识别为「未配置」（`llm-proxy.js` 的 `isConfigured()`），UI 下拉框会标灰显示 `(未配置)`。
2. `config.json` **支持热重载**：保存后约 1 秒生效，无需重启 `node llm-proxy.js`。
3. 仓库里 `config.json` 的默认 model 名（`deepseek-v4-pro` / `claude-sonnet-4-6` / `gpt-5.4-mini`）是占位，请改成你账号有权限的实际 model id，否则 LLM 调用 4xx。

---

## 启动

### 方式 A：浏览器（最简单）

```bash
node llm-proxy.js          # 代理在 127.0.0.1:3001 监听
# 然后双击 index.html 或拖进浏览器
```

控制台会打印：

```
[llm-proxy] listening on http://127.0.0.1:3001
[llm-proxy] configured providers: bedrock, claude
[llm-proxy] default provider: bedrock
```

### 方式 B：Python 套壳窗口（pywebview）

```bash
python launcher.py
```

`launcher.py` 会：
1. 先 `taskkill` 掉占用 3001 端口的旧 node 进程（Windows）
2. 启动 `node llm-proxy.js`（Windows 下隐藏 console 窗口）
3. 轮询 `/config` 等待代理就绪（最长 10s）
4. 用 pywebview 弹一个 1400×900 独立窗口加载 `index.html`
5. 窗口关闭时清理 node 子进程

Windows 下双击 `launcher.pyw` 可以无控制台启动。

---

## 使用说明

UI 顶部按钮 / 选项：

| 控件 | 作用 |
|------|------|
| 🎬 开始游戏 | 探测到至少一个已配置 provider 后才解锁 |
| ⏸ 暂停 / ↻ 重开 | 暂停 / 重置整局 |
| 速度 | 极慢 / 慢 / 中 / 快 / 极速 |
| LLM | 切换 provider（未配置的会标灰），切换后**当前局**剩余决策即生效 |
| 上帝视角 | 显示所有玩家真实身份 |
| 朗读 | 用 Web Speech API 朗读发言（按性别分配 voice） |

运行后会在工程目录生成 `prompts.log`，记录每次 `/chat` 和 `/decide` 的 system / user / tools / response，方便回放和调试。

---

## 文件结构

```
wolf-game/
├── index.html              # 前端入口，UI + provider 探测 + 启动钩子
├── styles.css              # 全部样式（圆桌、座位、雾、星空）
├── game.js                 # 游戏引擎（昼夜流程、投票、PK、警长、TTS）
├── agents.js               # Agent 类、12 个性格预设、规则版兜底策略
├── llm-adapter.example.js  # LLM 适配器：构造 prompt + tools，调本地代理
├── llm-proxy.js            # Node 代理：/chat /decide /config，4 provider 路由
├── launcher.py             # Python pywebview 套壳启动器
├── launcher.pyw            # 双击启动入口（无 console）
├── config.json             # provider 凭据 + 默认端口（git 提交时请脱敏）
├── package.json            # npm 配置（仅 @aws-sdk/client-bedrock-runtime）
└── prompts.log             # 运行时生成的 LLM 请求日志
```

各文件职责：

- **`game.js`** — 整局状态机：发牌 → 警长竞选 → 第 N 夜（狼刀 / 女巫 / 预言家 / 守卫）→ 第 N 天（公布死讯 → 发言 → 投票 / PK）→ 判胜负。
- **`agents.js`** — 每个 Agent 有性格（aggro/deception/talkative）、私人记忆（狼队友、查验结果、毒药状态）、怀疑度。**LLM 失败时自动 fallback 到规则版**（`LLM.speak/decide` 失败返回 null，触发兜底逻辑）。
- **`llm-adapter.example.js`** — 把 game 内部状态打包成 prompt：角色 SOP、本场已有发言、内心日记、上轮复盘、tools schema（Anthropic 风格）。调 `/chat` 拿发言、`/decide` 拿结构化决策。
- **`llm-proxy.js`** — 接受 Anthropic 风格 tools，内部转 OpenAI function tools；DeepSeek 显式 `thinking.disabled` 防 tool_choice 报错。

---

## HTTP API

代理提供 3 个端点（CORS 全开，仅监听 127.0.0.1）：

### `GET /config`

返回当前可用 provider，不泄露 secret：

```json
{
  "availableProviders": ["bedrock", "claude"],
  "default": "bedrock"
}
```

### `POST /chat`

文本发言。请求：

```json
{
  "provider": "bedrock",
  "system": "你是 3 号 …",
  "user": "当前阶段：第 1 天 白天发言 …",
  "maxTokens": 500
}
```

响应：

```json
{ "text": "【思考】… 【发言】我 3 号，跳预言家，昨晚验 7 号是狼。" }
```

### `POST /decide`

结构化决策（投票 / 夜行动）。请求加 `tools`（Anthropic schema）：

```json
{
  "provider": "claude",
  "system": "…",
  "user": "…",
  "tools": [{
    "name": "vote",
    "description": "投票放逐目标",
    "input_schema": {
      "type": "object",
      "properties": {
        "thinking": { "type": "string" },
        "target":   { "type": "integer" }
      },
      "required": ["thinking", "target"]
    }
  }]
}
```

响应：

```json
{ "toolName": "vote", "input": { "thinking": "7 号查杀稳投", "target": 7 } }
```

OpenAI / DeepSeek 路径下，代理内部自动把 Anthropic tools 转 OpenAI function tools，对前端透明。

---

## 常见问题

### 「开始游戏」按钮一直灰着

`index.html` 每 3 秒探测一次 `/config`。可能原因：

1. `node llm-proxy.js` 没启动 → 启动它。
2. 端口被占用 → 改 `config.json` 的 `port`，并同步改 `index.html` 里的 `PROXY_PORT`（搜 `3001`），或杀掉占用进程。Windows 一键杀：`netstat -ano | findstr :3001` 找 PID → `taskkill /F /PID <pid>`，或者直接用 `launcher.py`，它会自动杀旧进程。
3. `config.json` 里所有 provider 都被识别为占位符 → 至少填一个真 apiKey（不要包含 `FILL` / `YOUR`）。

### LLM 调用 4xx / 5xx

打开 `prompts.log` 看具体响应：

- **Bedrock**: 检查 `region` 是否开通了所选 model、IAM 是否有 `bedrock:InvokeModel` 权限。
- **Claude**: 检查 `model` 名是 API 实际 ID。
- **DeepSeek / OpenAI**: `model` 不存在或没权限 → 改成你账号有的 model。

### 想增加一个新 provider

1. `llm-proxy.js` 里加一个 `invokeXxx()` 函数（参考 `invokeOpenAICompat`）。
2. 加进 `dispatch()` 的 `switch`、`AVAILABLE` 的过滤名单、`isConfigured()` 的判断。
3. `index.html` 的 `<select id="providerSel">` 加一个 `<option>`。
4. `config.json` 加对应字段。

### 数据安全

- `llm-proxy.js` **只监听 127.0.0.1**，不暴露到公网。
- `config.json` 含明文 apiKey，**不要 commit 进公共仓库**。建议加进 `.gitignore` 并提供 `config.example.json` 模板。
- 运行时 `prompts.log` 会包含完整 system/user prompt，**不会包含 apiKey**，但发言里可能含游戏剧情，自行斟酌是否分享。

---

## License

ISC
