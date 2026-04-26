# Dragon Agent

基于 Flask + MCP 架构的本地 AI Agent 服务。模块化面向对象设计，支持工具调用、知识库问答、图片/视频生成、浏览器自动化、技能热加载等功能，SSE 流式推送 Web 界面。

---

## 功能一览

| 功能 | 说明 |
|------|------|
| 多轮对话 | 会话持久化，历史消息保存在本地 JSON 文件 |
| 工具调用 | MCP 架构动态加载工具，支持文件读写、网络搜索、系统命令等 |
| 知识库问答 (RAG) | 上传文档后语义检索，RAG 模式下 LLM 仅使用检索结果回答 |
| AI 图片生成 | 通义万象 wan2.6-t2i 文生图，支持多种分辨率 |
| AI 视频生成 | 通义万象 wan2.6-t2v 文生视频/图生视频，720P 5 秒 |
| 浏览器自动化 | Playwright 控制真实浏览器，导航、截图、点击、输入、内容获取 |
| OCR 识别 | PaddleOCR 图片文字识别（中英文） |
| 技能系统 | skills/ 目录热加载 Markdown 技能指令，运行时增删无需重启 |
| 文件权限管理 | 文件操作前弹出授权确认，用户可管理已授权路径 |
| 流式输出 | SSE (Server-Sent Events) 实时推送 LLM 回复 |
| 内网穿透 | 集成 cloudflared，自动建立公网隧道并邮件通知 |
| 多模型切换 | 支持 DeepSeek Chat，含图片时自动切换 Qwen 视觉模型 |
| MCP 热重载 | 运行时重新加载 MCP 工具模块，无需重启服务 |

---

## 核心概念通俗解读

如果你对 HTTP、SSE、Agent 这些概念不熟悉，这一节帮你快速理解整个系统到底在干什么。

### 整体比喻：一个餐厅

```
顾客（浏览器）  →  服务员（Flask）  →  厨师（AgentRunner）  →  帮手们（MCP 工具）
```

1. 你在网页上打字问问题 = 顾客点菜
2. Flask 收到请求 = 服务员接单
3. AgentRunner 拿着问题去问 DeepSeek = 厨师开始做菜
4. DeepSeek 说 "我需要先搜个网" = 厨师叫帮手去拿食材
5. 搜索结果拿回来，DeepSeek 继续生成回答 = 食材到了，继续做菜
6. 最终回答一个字一个字传到你的屏幕上 = 菜一盘盘端上桌

### HTTP —— 一问一答

HTTP 就是浏览器和服务器之间说话的方式，像打电话：

```
浏览器: "嘿，给我会话列表"
服务器: "好，给你 [{会话1}, {会话2}]"
（结束，连接断开）
```

你拨号（发请求）→ 对方接听（服务器处理）→ 对方说完（返回结果）→ 挂断。适合 "一下子就能回答" 的事情，比如获取会话列表、切换模型。

### SSE —— 持续广播（流式输出的秘密）

SSE = Server-Sent Events = 服务器持续发消息。

HTTP 是打电话说完就挂，SSE 是开了个广播频道不挂断。为什么需要它？因为 AI 回答是一个字一个字生成的：

```
普通 HTTP：等 AI 想完所有内容（可能 30 秒）→ 一次性全部返回
           用户体验：盯着空白屏幕 30 秒，突然蹦出一大段文字

SSE：     AI 每想出几个字 → 立刻推过来 → 屏幕上实时冒出文字
           用户体验：像看对方打字一样，实时看到回答（打字机效果）
```

你在 ChatGPT、DeepSeek 网页上看到的文字 "打字机效果"，就是 SSE。具体过程：

```
浏览器: "我要问问题，开一个 SSE 通道"
服务器: "好，通道建好了，我开始说——"

  → event: thinking      "第1步：正在思考..."
  → event: tool_call     "调用了网络搜索"
  → event: tool_result   "搜索结果：xxx"
  → event: thinking      "第2步：正在组织回答..."
  → event: reply_chunk   "人工"
  → event: reply_chunk   "智能"
  → event: reply_chunk   "是指..."
  → event: reply_done    "完成"
  → event: done          "全部结束"

浏览器: "收到，关闭通道"
```

前端 JS 监听这些事件，收到 `reply_chunk` 就往聊天气泡里追加文字，收到 `tool_call` 就显示 "正在调用搜索..."。

### Agent 循环 —— 最核心的逻辑

普通聊天机器人只能对话，Agent 能 "动手干活"。`agent_runner.py` 做的事：

```
拿到用户问题
│
├→ 问 DeepSeek："这个问题你怎么看？"
│
│  DeepSeek 可能说两种话：
│  ├─ "我直接回答：xxx"  →  显示给用户，结束
│  └─ "我需要用工具：搜索 AI 新闻"
│          │
│          ├→ 执行搜索，拿到结果
│          ├→ 把结果告诉 DeepSeek
│          ├→ DeepSeek 继续想...（可能又要用工具）
│          └→ 循环最多 30 次，直到给出最终回答
```

一句话总结：**Agent = LLM + 工具调用循环**。

### 各模块用人话说

| 模块 | 干什么的 | 类比 |
|------|---------|------|
| `app.py` | 开门迎客，把人带到对的地方 | 前台 |
| `core/registry.py` | 记录所有部门在哪 | 公司通讯录 |
| `core/session.py` | 记住每次聊天内容 | 档案室 |
| `core/permissions.py` | 决定能不能动某个文件 | 保安 |
| `core/llm_client.py` | 跟 DeepSeek 对话 | 外联部（打电话给 AI） |
| `core/agent_runner.py` | 接到问题 → 问 AI → 用工具 → 再问 AI → 直到有答案 | 项目经理 |
| `core/tunnel.py` | 让外网也能访问 | IT 部门搞远程 |
| `routes/*.py` | 各个 API 接口 | 不同服务窗口 |
| `mcp_servers/` | 搜索、读文件、画图等各种工具 | 工具箱 |

---

## 项目架构

```
agent/
├── app.py                     # Flask 应用工厂 + 入口 (87 行)
├── config.py                  # 配置中心：提供商、API Key、参数
├── app_backup.py              # 重构前的单体备份
│
├── core/                      # 核心业务模块（面向对象）
│   ├── __init__.py            # 统一导出所有核心类
│   ├── registry.py            # ServiceRegistry 服务注册表
│   ├── session.py             # SessionStore 会话持久化
│   ├── permissions.py         # PermissionManager 路径权限
│   ├── tunnel.py              # TunnelManager 内网穿透
│   ├── llm_client.py          # LlmClient 流式 LLM 调用
│   └── agent_runner.py        # AgentRunner Agent 主循环
│
├── routes/                    # Flask 路由蓝图
│   ├── __init__.py            # register_blueprints() 统一注册
│   ├── chat.py                # /chat SSE 流式聊天 + /api/stop
│   ├── sessions.py            # /api/sessions 会话 CRUD
│   ├── models.py              # /api/model 模型切换
│   ├── permissions_routes.py  # /api/allowed_paths 权限管理
│   ├── rag.py                 # /api/rag/* 知识库操作
│   ├── ocr.py                 # /api/ocr 文字识别
│   └── tunnel_routes.py       # /api/tunnel 隧道状态
│
├── mcp_servers/               # MCP 工具模块（热插拔）
│   ├── __init__.py            # McpLoader + SkillManager
│   ├── filesystem/            # 文件读写、搜索、目录浏览
│   ├── web/                   # 网络搜索、网页抓取
│   ├── browser/               # Playwright 浏览器自动化
│   ├── image_gen/             # 图片/视频生成（通义万象）
│   ├── rag/                   # RAG 向量检索
│   ├── ocr/                   # PaddleOCR 文字识别
│   └── utils/                 # 系统工具（命令执行等）
│
├── prompts/                   # 提示词与定价
│   ├── __init__.py            # SYSTEM_PROMPT 系统提示词
│   └── pricing.py             # 模型 token 定价
│
├── skills/                    # 技能目录（热加载）
│   ├── translate/skill.md     # 翻译技能
│   └── .../skill.md           # 更多技能
│
├── templates/
│   └── index.html             # Web 前端界面
│
├── data/                      # 运行时数据（自动创建）
│   ├── sessions.json          # 会话持久化
│   └── rag_docs/              # RAG 知识库文档
│
├── mcp_config.json            # MCP 工具启用/禁用配置
├── .env                       # 环境变量（API Key 等敏感信息）
├── 启动Agent.command          # macOS 双击启动
└── 停止Agent.command          # macOS 双击停止
```

---

## 核心设计

### ServiceRegistry 模式

所有核心服务实例集中注册在 `ServiceRegistry` 中，存储于 `app.extensions['registry']`：

```python
class ServiceRegistry:
    session_store   # SessionStore    会话管理
    permission_mgr  # PermissionManager 权限管理
    tunnel          # TunnelManager   隧道管理
    llm_client      # LlmClient      LLM 调用
    agent           # AgentRunner     Agent 主循环
    current_model   # str             当前模型 ID
    cancel_flags    # dict            取消信号
```

路由蓝图通过 `current_app.extensions['registry']` 访问服务，无全局变量依赖。

### LlmClient 无状态设计

`stream()` 方法接受显式的 `model` 和 `provider` 参数，不依赖全局状态：

```python
llm_client.stream(model="deepseek-chat", provider=provider_cfg, messages=..., tools=...)
```

### AgentRunner 依赖注入

通过 `model_resolver` 回调动态获取当前模型，实现运行时模型切换：

```python
agent = AgentRunner(tools, tool_map, tool_labels, file_tools,
                    permission_mgr, llm_client, model_resolver=lambda: (model, provider))
```

### MCP 热插拔

工具模块从 `mcp_config.json` 动态加载，支持运行时热重载：

```python
from mcp_servers import load_all
tools, tool_map, tool_labels, file_tools = load_all()

# 运行时重载
from mcp_servers import _mcp_loader
tools, tool_map, tool_labels, file_tools = _mcp_loader.reload()
```

---

## 架构流程图

```
┌──────────────────────────────────────────────────────────┐
│                     浏览器 (前端)                          │
│               templates/index.html + JS                   │
└─────────────────────────┬────────────────────────────────┘
                          │ HTTP / SSE
┌─────────────────────────▼────────────────────────────────┐
│                  Flask 应用 (app.py)                       │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐ │
│  │              routes/ (蓝图路由层)                     │ │
│  │  chat.py │ sessions.py │ models.py │ rag.py │ ...   │ │
│  └────────────────────────┬────────────────────────────┘ │
│                           │                               │
│  ┌────────────────────────▼────────────────────────────┐ │
│  │           core/ (核心业务层)                          │ │
│  │                                                      │ │
│  │  ServiceRegistry ──┬── SessionStore   (会话持久化)    │ │
│  │                    ├── PermissionManager (路径权限)   │ │
│  │                    ├── TunnelManager  (内网穿透)      │ │
│  │                    ├── LlmClient      (流式 LLM)     │ │
│  │                    └── AgentRunner    (Agent 循环)    │ │
│  └─────────────────────────────────────────────────────┘ │
│                           │                               │
│  ┌────────────────────────▼────────────────────────────┐ │
│  │        mcp_servers/ (工具插件层，热插拔)              │ │
│  │  filesystem │ web │ browser │ image_gen │ rag │ ocr  │ │
│  └─────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
                          │
         ┌────────────────┼────────────────┐
         │                │                │
  ┌──────▼──────┐  ┌──────▼──────┐  ┌─────▼───────┐
  │  DeepSeek   │  │ Qwen 视觉   │  │  DashScope  │
  │  Chat API   │  │ VL-Max API  │  │ 图片/视频API │
  └─────────────┘  └─────────────┘  └─────────────┘
```

---

## 安装

```bash
git clone https://github.com/songchunliang1985/SCL.git
cd SCL/agent
```

之后按下面"快速开始"配环境变量、装依赖、启动。

---

## 快速开始

### 1. 安装依赖

```bash
pip install flask requests python-dotenv

# 可选功能
pip install playwright && playwright install chromium   # 浏览器自动化
pip install sentence-transformers faiss-cpu              # RAG 知识库
pip install paddlepaddle paddleocr                       # OCR 识别
```

### 2. 配置环境变量

创建 `.env` 文件（或设置系统环境变量）：

```bash
# 必填
DEEPSEEK_API_KEY=sk-your-deepseek-key

# 可选：图片/视频生成 + Qwen 视觉模型
DASHSCOPE_API_KEY=sk-your-dashscope-key

# 可选：隧道邮件通知
NOTIFY_EMAIL=your@email.com
SMTP_USER=your-account@163.com
SMTP_PASSWORD=your_smtp_password
```

### 3. 配置 MCP 工具

编辑 `mcp_config.json`，启用或禁用工具模块：

```json
{
  "servers": {
    "utils":      { "enabled": true },
    "web":        { "enabled": true },
    "filesystem": { "enabled": true },
    "playwright": { "enabled": true },
    "ocr":        { "enabled": true },
    "image_gen":  { "enabled": true },
    "rag":        { "enabled": true }
  }
}
```

### 4. 启动服务

```bash
python app.py
```

浏览器访问 http://localhost:5050

**macOS 用户**也可以双击 `启动Agent.command` 启动，双击 `停止Agent.command` 停止。

---

## 使用指南

### 基础对话
在聊天框输入问题，Agent 自动判断是否需要调用工具，流式返回回答。

### 会话管理
- 左侧边栏显示历史会话，点击切换
- 每次对话自动保存，重启服务后历史不丢失
- 支持重命名、删除会话

### 文件系统授权
首次访问文件时弹出权限确认对话框，授权后该路径下所有文件均可访问。

### RAG 知识库
1. 点击上传文档（支持 PDF、TXT、MD 等格式）
2. 开启 "RAG 模式" 开关
3. Agent 会先从知识库检索，再基于检索结果回答

### 技能系统
在 `skills/` 目录下创建子目录和 `skill.md` 文件：

```markdown
---
name: 翻译助手
description: 中英文互译，支持术语保留
---

（详细行为指南...）
```

无需重启，下次请求自动加载。

---

## API 参考

### 聊天

| 接口 | 方法 | 说明 |
|------|------|------|
| `/chat` | POST | 主聊天接口，返回 SSE 事件流 |
| `/api/stop` | POST | 中断进行中的会话 |

**请求体：**
```json
{
  "messages": [{"role": "user", "content": "你好"}],
  "session_id": "abc12345",
  "rag_mode": false
}
```

**SSE 事件类型：**

| event | 说明 |
|-------|------|
| `thinking` | 思考步骤进度 |
| `reply_chunk` | 流式文本片段 |
| `reply_done` | 文本回复完成 |
| `reply` | 单条完整回复 |
| `tool_call` | 工具调用开始 |
| `tool_result` | 工具执行结果 |
| `permission_request` | 请求文件路径授权 |
| `error` | 错误信息 |
| `done` | 请求结束 |

### 会话管理

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/sessions` | GET | 获取所有会话列表 |
| `/api/sessions` | POST | 创建新会话 |
| `/api/sessions/<sid>` | GET | 获取会话详情（含消息历史） |
| `/api/sessions/<sid>` | DELETE | 删除会话 |
| `/api/sessions/<sid>/title` | PUT | 修改会话标题 |

### 模型管理

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/model` | GET | 获取当前模型及可用模型列表 |
| `/api/model` | POST | 切换模型 `{"model": "deepseek-chat"}` |

### 权限管理

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/allowed_paths` | GET | 已授权路径列表 |
| `/api/allowed_paths` | POST | 添加授权路径 `{"path": "/Users/xxx/project"}` |
| `/api/allowed_paths` | DELETE | 移除授权路径 |
| `/api/approve_tool` | POST | 响应权限确认 `{"request_id": "...", "approved": true}` |
| `/api/browse` | POST | 浏览目录 `{"path": "~"}` |

### RAG 知识库

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/rag/ingest` | POST | 上传文档 (multipart/form-data) |
| `/api/rag/search` | POST | 语义检索 `{"query": "...", "top_k": 5}` |
| `/api/rag/list` | GET | 列出已摄入文档 |
| `/api/rag/delete` | POST | 删除文档 `{"filename": "xxx.pdf"}` |

### 其他

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/ocr` | POST | OCR 识别 `{"image_data": "<base64>", "lang": "ch"}` |
| `/api/tunnel` | GET | 隧道状态和公网 URL |

---

## 配置参考

### config.py 主要配置项

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `PROVIDERS` | - | 各 LLM 提供商的 API 地址、Key、模型列表 |
| `MAX_TOOL_LOOPS` | 30 | 最大工具调用循环次数 |
| `API_TIMEOUT` | 120 | LLM API 请求超时（秒） |
| `PERMISSION_TIMEOUT` | 120 | 等待用户授权超时（秒） |
| `WEB_PORT` | 5050 | Web 服务监听端口 |
| `NOTIFY_EMAIL` | - | 隧道通知邮箱 |

### .env 环境变量

| 变量名 | 说明 |
|--------|------|
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥 |
| `DASHSCOPE_API_KEY` | 阿里云 DashScope 密钥（图片/视频/视觉模型） |
| `NOTIFY_EMAIL` | 隧道公网地址通知邮箱 |
| `SMTP_USER` | 发信邮箱账号 |
| `SMTP_PASSWORD` | 发信邮箱密码/授权码 |

---

## 注意事项

- `.env` 文件包含 API Key 等敏感信息，已在 `.gitignore` 中排除，请勿提交到公开仓库
- 内网穿透需要安装 `cloudflared`（macOS: `brew install cloudflared`）
- 浏览器自动化需要先安装 Playwright 和 Chromium
- RAG 功能首次使用需要下载向量模型，建议提前初始化
- `app_backup.py` 是重构前的单体文件备份，可在确认新架构稳定后删除
