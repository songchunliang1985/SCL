# RAG 知识整理

整理自与 Claude 的对话，涵盖 RAG 基础原理、GraphRAG、LightRAG 及集成方案。

---

## 一、普通 RAG 原理

RAG（Retrieval-Augmented Generation，检索增强生成）解决的核心问题：LLM 只知道训练数据，不知道你自己的文档。

### 执行流程

```
文档 → 切片（Chunk）→ 向量化（Embedding）→ 存入向量数据库
                                                    ↓
用户提问 → 向量检索（找最相似的块）→ 把内容 + 问题发给 LLM → 回答
```

### 本项目当前实现

| 组件 | 技术选型 |
|------|---------|
| 向量模型 | BAAI/bge-small-zh-v1.5（本地） |
| 向量数据库 | ChromaDB（本地持久化） |
| 重排模型 | BAAI/bge-reranker-base（CrossEncoder） |
| 切片策略 | 段落 → 句子 → 字数兜底，支持 overlap |

### 检索流程（两阶段）

1. **粗召回**：向量相似度，取 Top-20
2. **精排（Rerank）**：CrossEncoder 重打分，sigmoid 归一化，取 Top-4，过滤低分

---

## 二、GraphRAG 原理

微软开源方案，核心区别：把文档构建成**知识图谱**，而非仅做向量检索。

### 普通 RAG vs GraphRAG

```
普通 RAG：  问题 → 找最像的段落 → 回答       （平面检索）
GraphRAG：  问题 → 找相关实体 → 沿图走邻居 → 汇总 → 回答  （图上游走）
```

### 建图流程（只做一次）

**Step 1：切片**
```
文档 → 按段落/字数切成 chunk（默认 300 tokens）
```

**Step 2：LLM 抽取实体和关系**
```
对每个 chunk，调用 LLM：
  "从这段文字里抽出所有实体（人/公司/地点/概念）
   以及实体之间的关系"

示例 chunk："马云创立了阿里巴巴，总部在杭州"
→ 实体：马云(人)、阿里巴巴(公司)、杭州(地点)
→ 关系：马云 --[创立]--> 阿里巴巴
         阿里巴巴 --[总部在]--> 杭州
```

**Step 3：构建知识图谱**
```
合并所有 chunk 的实体/关系，去重
节点 = 实体
边   = 关系（权重 = 在多少 chunk 里出现过）
```

**Step 4：社区检测（Leiden 算法）**
```
把图里关系紧密的节点聚成"社区"
社区1：[马云、张勇、阿里巴巴、淘宝、天猫]
社区2：[马化腾、微信、腾讯、QQ]
```

**Step 5：生成社区摘要**
```
对每个社区调用 LLM 生成摘要 → 向量化存储
原始 chunk 也向量化存储
```

最终存三层：
```
原始 chunk（向量）
知识图谱（图结构）
社区摘要（向量）
```

### 两种检索模式

**Local Search（精确实体问答）**
```
问题："马云和阿里巴巴是什么关系？"
1. 向量检索 → 找相关 chunk
2. 图中拿出"马云"节点的所有邻居和边
3. chunk + 图结构 → LLM → 回答
```

**Global Search（全局主题聚合）**
```
问题："这批文档主要讲了哪些话题？"
→ 普通 RAG 完全回答不了
→ GraphRAG：取所有社区摘要 → 层级汇总 → LLM 综合回答
```

### 能力对比

| 能力 | 普通 RAG | GraphRAG |
|------|---------|---------|
| 精确段落检索 | ✅ 很好 | ✅ |
| 跨文档关系推理 | ❌ | ✅ |
| 全局主题总结 | ❌ | ✅ |
| 构建速度 | 快（秒级） | 慢（分钟~小时） |
| 构建成本 | 免费（本地模型） | 需要 LLM API 费用 |
| 本地化 | ✅ 完全本地 | ⚠️ 需要 LLM |

---

## 三、LightRAG

GraphRAG 之后的改良版，专门解决"贵和慢"的问题。

### 优势

- 调用次数比 GraphRAG 少 **60-70%**
- 支持**增量更新**（加文档不用重建整个图）
- 代码更简单

```bash
pip install lightrag-hku
```

---

## 四、解决"贵和慢"的方案对比

| 方案 | 解决了什么 | 没解决什么 |
|------|-----------|-----------|
| LangChain | 代码组织框架 | 不省钱，只是连接层 |
| LightRAG | 减少调用次数 60-70% | 还是要 LLM |
| GLiNER | 抽取不用 LLM，本地小模型 | 关系质量略差 |
| 本地 Ollama | 完全免费 | 需要本地算力 |
| **Ollama + LightRAG** | **免费 + 少调用** | 速度比 API 慢 |

### 推荐组合

```
普通文档检索  →  当前 BGE + ChromaDB（够用，完全免费）
需要关系分析  →  LightRAG + Ollama 本地模型（免费）
重要文档精析  →  LightRAG + DeepSeek Chat（约 ¥5/10MB，建一次永久用）
```

---

## 五、10MB 文档建图成本估算

### Token 量计算

```
10MB 中文文本 ≈ 350万汉字 ≈ 350万 tokens
切片后：350万 / 300 ≈ 11,700 个 chunk
每个 chunk：输入 500 tokens + 输出 200 tokens
```

### 费用

| 模型 | 费用 |
|------|------|
| DeepSeek Chat | ≈ ¥12 |
| DeepSeek Reasoner | ≈ ¥67 |
| DeepSeek Chat + LightRAG | ≈ ¥5（调用量减少 60%） |

### 时间

```
GraphRAG：约 3 小时（11,700 次 API 调用）
LightRAG：约 1 小时（4,700 次 API 调用）

之后每次检索：几分钱（不重建图）
```

---

## 六、LlamaIndex 是什么

把"你自己的文档"喂给 LLM 的工具箱，封装了完整 RAG 管道。

### 四个步骤

```
Load（读取）→ Index（切片+向量化）→ Retrieve（检索）→ Generate（生成）
```

### 和本项目对比

| 本项目 | LlamaIndex 对应 |
|--------|----------------|
| `_extract_text()` | Document Loader |
| `_chunk_text()` | Text Splitter |
| BGE 模型 | Embedding Model |
| ChromaDB | Vector Store |
| `rag_search()` | Query Engine |

本项目已手动实现了 LlamaIndex 的核心功能，更轻量可控。

### LlamaIndex 的额外价值

- **高级检索策略内置**：HyDE（假设文档嵌入）、句子窗口、自动合并
- **一行切换 GraphRAG**：`KnowledgeGraphIndex.from_documents(docs)`
- **少写代码**：原本 200 行，LlamaIndex 几行搞定

---

## 七、适用场景建议

| 文档场景 | 建议 |
|---------|------|
| 合同/报告，需要"找段落" | 现有 RAG 够用，不需要 GraphRAG |
| 大量文档，需要"找关系/找主题" | 值得接入 LightRAG |
| 文档量 < 50页 | 完全没必要上 GraphRAG |
| 文档量 > 500页且有关系推理需求 | GraphRAG/LightRAG 有明显优势 |
| 隐私数据，不能上云 | Ollama 本地模型 |

---

## 八、学习资源

| 资源 | 地址 | 特点 |
|------|------|------|
| Pinecone RAG 学习中心 | https://www.pinecone.io/learn/retrieval-augmented-generation/ | 最全面，含 GraphRAG，免费 |
| DeepLearning.AI RAG 课程 | https://learn.deeplearning.ai/courses/retrieval-augmented-generation/information | 实操为主，配合向量库 |
| LlamaIndex 官方文档 | https://developers.llamaindex.ai/python/framework/understanding/rag/ | 框架文档，从零构建指南 |
| Boot.dev RAG 课程 | https://www.boot.dev/courses/learn-retrieval-augmented-generation | Python 从零实现，项目驱动 |
| Class Central RAG 课程汇总 | https://www.classcentral.com/report/best-rag-courses/ | 多平台课程对比汇总 |
