# Dragon Agent

基于 Flask + MCP 的本地 AI Agent 服务。LLM 工具调用 + Agentic RAG 知识库 + 浏览器自动化 + OCR + 流式 SSE 推送。

---

## 功能

| 模块 | 说明 |
|------|------|
| 多轮对话 | 会话持久化，DeepSeek v4-pro / v4-flash 可切换 |
| Agentic RAG | HyDE 查询扩展 + 向量+BM25 双路 + RRF 融合 + Cross-Encoder 重排 |
| 浏览器自动化 | Playwright 真实浏览器，导航 / 点击 / 截图 / 取文 |
| OCR | PaddleOCR 中英文图像文字识别（图片 → 文字后喂给 LLM） |
| 文件操作 | 浏览 / 读 / 写 / 搜索，按路径授权 |
| 技能系统 | `skills/` 下 Markdown 技能，热加载 |
| 内网穿透 | cloudflared 自动建隧道并发邮件 |
| MCP 热重载 | 运行时增删工具模块无需重启 |

---

## 模型一览

| 用途 | 模型 | 来源 |
|------|------|------|
| 主对话 + 工具调用 | `deepseek-v4-pro` / `deepseek-v4-flash` | DeepSeek API |
| HyDE 查询扩展 | `deepseek-chat` | DeepSeek API |
| 向量 Embedding | `BAAI/bge-small-zh-v1.5` | 本地 SentenceTransformer |
| Cross-Encoder 重排 | `BAAI/bge-reranker-base` | 本地 |
| 中文分词（BM25） | `jieba` | 本地 |
| OCR | PaddleOCR `PP-OCRv4` | 本地 |

---

## RAG 架构

### 导入阶段（rag_ingest）

```
PDF / Excel / TXT / MD / CSV / 代码
        │
        ▼
   提取纯文本
        │
        ▼
   语义切片  ← 段落优先 → 句子兜底 → 字符强切
   chunk_size=300  overlap=80
        │
        ▼
   BAAI/bge-small-zh-v1.5 向量化
        │
        ▼
   ChromaDB 持久化（~/agent/data/chroma_bge）
        │
        ▼
   重建 BM25 索引（jieba 分词）
```

### Agentic 检索（rag_ask）

```
用户问题
   │
   ▼
HyDE 查询扩展（deepseek-chat 生成"假设答案" + 子问题拆解）
   │
   ▼  多条查询并行
双路检索：向量(ChromaDB Top-15) + BM25(jieba Top-15)
   │
   ▼
RRF 融合（Reciprocal Rank Fusion，k=60）
   │
   ▼
Cross-Encoder 精排（BAAI/bge-reranker-base，输出 Top-4）
   │
   ▼  若最高相关度 < 0.4
自适应重试：换关键词策略 + 扩大 Top-K（最多 2 轮）
   │
   ▼
返回 chunks + relevance + trace
（相关度 < 0.35 → 注入"无结果"指令强制拒答）
```

### 单轮检索（rag_search）

向量 + BM25 + RRF + Rerank，无 HyDE 无重试，适合精确查找已知术语。

---

## RAG 严格性保证

RAG 模式（前端开关）下三层防线，按顺序生效：

1. **工具裁剪** — 仅 `rag_ask / rag_search / rag_list / rag_delete / rag_ingest` 暴露给模型，物理上无法调联网/浏览器
2. **强制指令注入** — 检索结果为空或相关度低时，工具返回值里直接塞 `_NO_RESULT_INSTRUCTION`，模型下一轮立即看到
3. **Agent 层 reinject** — 模型若跳过工具直接答，agent 强制再循环要求先 `rag_ask`（任意步生效，非仅首步）

---

## 可靠性保证

| 机制 | 实现位置 | 说明 |
|------|----------|------|
| API 自动重试 | `core/agent_runner.py` | 502/503/429 指数退避重试，最多 3 次 |
| Context Window 保护 | `core/context_trim.py` | 超过 80k 字符时逐轮裁剪旧消息，保留 system 和最近对话 |
| 并发安全 RAG 状态 | `core/agent_runner.py` | `RagState` 每次请求独立创建，无跨请求共享 |
| 工具并行执行 | `core/agent_runner.py` | 同步骤多个非文件工具并行执行（ThreadPoolExecutor），文件工具保持串行等待授权 |
| Session 文件锁 | `core/session.py` | `threading.Lock` 保护 JSON 读写原子性 |
| cancel_flags 清理 | `routes/chat.py` | `try/finally` 确保连接断开时也清理 Event，防内存泄漏 |

---

## 项目结构

```
agent/
├── app.py                  Flask 入口
├── config.py               PROVIDERS / 超时 / 端口
├── core/
│   ├── agent_runner.py     多轮 LLM + 工具循环（并行执行 / 重试 / 裁剪）
│   ├── llm_client.py       SSE 流式 DeepSeek 客户端（含 reasoning_content 回传）
│   ├── context_trim.py     消息裁剪（防 context window 溢出）
│   ├── rag_hooks.py        RAG 状态追踪 hook（per-request，并发安全）
│   ├── hooks.py            通用 hook 管道（支持 copy()）
│   ├── session.py          会话持久化（带线程锁）
│   ├── permissions.py      文件授权管理
│   ├── tunnel.py           cloudflared 隧道
│   └── registry.py         服务注册表
├── routes/                 Flask 蓝图
├── mcp_servers/
│   ├── filesystem/         文件读写、搜索
│   ├── web/                联网搜索、网页抓取
│   ├── playwright/         浏览器自动化
│   ├── rag/                Agentic RAG
│   ├── ocr/                PaddleOCR
│   └── utils/              天气、计算器、时间
├── prompts/                SYSTEM_PROMPT + 定价
├── skills/                 Markdown 技能定义
├── templates/index.html    Web UI
└── data/                   会话 / 向量库 / RAG 文档
```

---

## 安装

```bash
pip install flask requests python-dotenv
pip install chromadb sentence-transformers rank-bm25 jieba          # RAG
pip install playwright && playwright install chromium               # 浏览器
pip install paddlepaddle paddleocr                                  # OCR
```

## 配置 `.env`

```
DEEPSEEK_API_KEY=sk-xxxxx       # 必填
NOTIFY_EMAIL=you@example.com    # 可选：隧道地址通知收件人
SMTP_USER=sender@163.com        # 可选
SMTP_PASSWORD=xxxxx             # 可选
```

## 启动

```bash
python app.py                   # 默认 http://localhost:5050
```

或双击 `启动Agent.command`。

---

## RAG 调参

`mcp_servers/rag/config.json`：

| 参数 | 含义 | 默认 |
|------|------|------|
| `chunk_size` / `chunk_overlap` | 切片大小 / 重叠 | 300 / 80 |
| `retrieval_top_k` | 粗检索 Top-K（向量 + BM25 各取此数） | 15 |
| `rerank_top_k` | Rerank 输出条数（`rag_ask` 调用时可动态覆盖） | 4 |
| `low_relevance_threshold` | 相关度阈值，低于则判无结果 | 0.35 |
| `hyde.enabled` | 是否启用 LLM 查询扩展 | true |
| `adaptive.enabled` | 首轮低相关度时自动重试 | true |
| `adaptive.max_rounds` | 最大重试轮数 | 2 |

---

## 注意事项

- `.env` 含密钥，已在 `.gitignore` 排除
- 内网穿透需 `brew install cloudflared`
- 首次启动 RAG 会从 HuggingFace 下载 bge 模型（约 100MB），需联网
- DeepSeek v4-pro/flash 不支持图片输入，图片走 OCR 转文字后再喂模型
