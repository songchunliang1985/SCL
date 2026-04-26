"""
MCP Server: RAG — Agentic 知识库检索增强

检索策略：
  rag_search  — 单次混合检索（向量 + BM25 关键词），适合精确查找
  rag_ask     — Agentic 多轮检索，自动查询扩展 + 多路搜索 + RRF 融合，适合复杂问题

文档管理：
  rag_ingest  — 导入文件/文件夹
  rag_list    — 列出已导入文件
  rag_delete  — 删除指定文件
"""

import json
import os
import hashlib

_DIR = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(_DIR, "config.json"), "r") as f:
    _cfg = json.load(f)

# 当检索结果为空或相关度过低时，注入此指令强制 LLM 拒绝回答
# 嵌在工具返回值里比 system prompt 更有效，LLM 紧接着就能看到
_NO_RESULT_INSTRUCTION = (
    "⚠️ 【强制指令】知识库中未找到与该问题相关的内容。"
    "你必须直接回复用户：'知识库中没有找到相关内容，无法回答。'"
    "严禁使用任何预训练知识补充、猜测或扩展，严禁编造答案。"
)

_FOUND_INSTRUCTION = (
    "📎 以上为检索结果。请基于这些内容回答，每个事实声明标注来源文件名 `[来源: xxx]`，"
    "不要编造任何检索结果中没有的信息。"
)

CHUNK_SIZE       = _cfg.get("chunk_size", 300)
CHUNK_OVERLAP    = _cfg.get("chunk_overlap", 80)
RETRIEVAL_TOP_K  = _cfg.get("retrieval_top_k", 15)
RERANK_TOP_K     = _cfg.get("rerank_top_k", 4)
RERANK_CANDIDATES = _cfg.get("rerank_candidates", 8)
RERANK_THRESHOLD = _cfg.get("rerank_threshold", 0.1)
LOW_RELEVANCE_THRESHOLD = _cfg.get("low_relevance_threshold", 0.35)
DB_PATH          = os.path.abspath(os.path.expanduser(_cfg.get("db_path", "~/agent/data/chroma_bge")))
EMBEDDING_MODEL  = _cfg.get("embedding_model", "BAAI/bge-small-zh-v1.5")
RERANK_MODEL     = _cfg.get("rerank_model", "BAAI/bge-reranker-base")

# HyDE + Adaptive + Trace 配置
_HYDE_ENABLED       = _cfg.get("hyde", {}).get("enabled", True)
_HYDE_MAX_SUB       = _cfg.get("hyde", {}).get("max_sub_queries", 3)
_HYDE_MAX_TOKENS    = _cfg.get("hyde", {}).get("max_tokens", 200)
_ADAPTIVE_ENABLED   = _cfg.get("adaptive", {}).get("enabled", True)
_ADAPTIVE_MAX_ROUNDS = _cfg.get("adaptive", {}).get("max_rounds", 2)
_ADAPTIVE_RETRY_THRESHOLD = _cfg.get("adaptive", {}).get("retry_threshold", 0.4)
_ADAPTIVE_RETRY_TOPK_MUL = _cfg.get("adaptive", {}).get("retry_top_k_multiplier", 1.5)
_TRACE_ENABLED      = _cfg.get("trace", {}).get("enabled", True)

# 懒加载：向量库、重排模型、BM25 索引
_client   = None
_col      = None
_reranker = None
_bm25     = None        # BM25Okapi 实例
_bm25_corpus = []       # [(doc_text, metadata), ...]


# ── 向量库初始化 ───────────────────────────────────────

def _get_collection():
    global _client, _col
    if _col is not None:
        return _col
    import chromadb
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
    os.makedirs(DB_PATH, exist_ok=True)
    _client = chromadb.PersistentClient(path=DB_PATH)
    emb_fn = SentenceTransformerEmbeddingFunction(model_name=EMBEDDING_MODEL)
    _col = _client.get_or_create_collection("rag_docs_bge", embedding_function=emb_fn)
    return _col


def _get_reranker():
    global _reranker
    if _reranker is not None:
        return _reranker
    from sentence_transformers import CrossEncoder
    _reranker = CrossEncoder(RERANK_MODEL)
    return _reranker


# ── BM25 关键词索引 ────────────────────────────────────

def _tokenize(text: str) -> list[str]:
    """用 jieba 分词，过滤停用词和单字"""
    try:
        import jieba
        words = jieba.lcut(text)
    except ImportError:
        # jieba 未安装时退化为按字切
        words = list(text)
    stop = {"的", "了", "是", "在", "有", "和", "与", "或", "等", "对", "为", "从", "到",
            "被", "把", "将", "于", "以", "及", "中", "内", "外", "上", "下", "个", "一",
            "不", "也", "都", "就", "而", "但", "如", "该", "其", "此", "这", "那",
            "what", "how", "when", "where", "which", "who", "the", "a", "an", "is", "are"}
    return [w.strip() for w in words if len(w.strip()) > 1 and w.strip() not in stop]


def _rebuild_bm25():
    """从 ChromaDB 读取所有文档，重建 BM25 索引。在 ingest 后调用。"""
    global _bm25, _bm25_corpus
    try:
        from rank_bm25 import BM25Okapi
    except ImportError:
        # rank-bm25 未安装时跳过，BM25 功能降级
        _bm25 = None
        _bm25_corpus = []
        return

    col = _get_collection()
    total = col.count()
    if total == 0:
        _bm25 = None
        _bm25_corpus = []
        return

    all_data = col.get(include=["documents", "metadatas"])
    docs  = all_data["documents"]
    metas = all_data["metadatas"]

    _bm25_corpus = list(zip(docs, metas))
    tokenized = [_tokenize(d) for d in docs]
    _bm25 = BM25Okapi(tokenized)


def _search_bm25(query: str, top_k: int) -> list[tuple[float, str, dict]]:
    """BM25 关键词检索，返回 [(score, doc, meta), ...]"""
    global _bm25, _bm25_corpus
    if _bm25 is None:
        _rebuild_bm25()
    if _bm25 is None or not _bm25_corpus:
        return []

    tokens = _tokenize(query)
    if not tokens:
        return []

    scores = _bm25.get_scores(tokens)
    ranked = sorted(
        zip(scores, [c[0] for c in _bm25_corpus], [c[1] for c in _bm25_corpus]),
        key=lambda x: x[0], reverse=True
    )
    return [(float(s), d, m) for s, d, m in ranked[:top_k] if s > 0]


# ── HyDE 查询生成（LLM 驱动） ──────────────────────────

def _generate_hyde_queries(question: str) -> list[str]:
    """调用 LLM 生成假设文档片段(HyDE) + 子问题拆解，用作检索查询。

    返回至多 (1 + _HYDE_MAX_SUB) 条查询，失败时返回 []。
    """
    import requests as _requests
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        return []

    prompt = (
        f"你是一个信息检索助手。用户的问题是：\n"
        f"「{question}」\n\n"
        f"请完成两个任务：\n"
        f"1. 假设你手头有一份包含答案的文档，写出这段\"理想答案\"的关键段落（用文档口吻、{_HYDE_MAX_TOKENS}字以内）\n"
        f"2. 把问题拆成至多{_HYDE_MAX_SUB}个独立的子问题，每个一行\n\n"
        f"输出格式（严格遵守）：\n"
        f"【假设答案】\n<这里写假设答案>\n"
        f"【子问题】\n<每行一个子问题>"
    )

    try:
        resp = _requests.post(
            "https://api.deepseek.com/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": _HYDE_MAX_TOKENS + 100,
                "temperature": 0.3,
            },
            timeout=15,
        )
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"]
    except Exception:
        return []

    queries = []
    import re as _re
    # 提取假设答案
    hyde_match = _re.search(r'【假设答案】\s*\n?(.*?)(?:【子问题】|$)', text, _re.DOTALL)
    if hyde_match:
        hyde_text = hyde_match.group(1).strip()
        if hyde_text and len(hyde_text) > 10:
            queries.append(hyde_text)

    # 提取子问题
    sub_match = _re.search(r'【子问题】\s*\n?(.*)', text, _re.DOTALL)
    if sub_match:
        for line in sub_match.group(1).strip().splitlines():
            line = line.strip().lstrip("0123456789.、- )")
            if len(line) > 3 and line != question:
                queries.append(line)
                if len(queries) >= _HYDE_MAX_SUB + 1:
                    break

    return queries


# ── 查询扩展（规则式，作为 HyDE 的 fallback） ──────────

def _expand_queries(question: str) -> list[str]:
    """
    从一个问题生成多个搜索角度：
    1. 原始问题
    2. 去除疑问词后的陈述式（提高向量匹配率）
    3. jieba 关键词短查询（提高 BM25 召回率）
    4. 按连接词拆分的子问题
    """
    queries = [question]
    import re

    # 去除疑问词，变为陈述句
    q_clean = re.sub(r'^(请问|请|麻烦|帮我|告诉我|我想知道|查一下|查询)', '', question).strip()
    q_clean = re.sub(r'[？?]$', '', q_clean).strip()
    if q_clean and q_clean != question:
        queries.append(q_clean)

    # 按连接词拆分子问题（"和"、"以及"、"还有" 分隔的并列问题）
    parts = re.split(r'[，,]?\s*(?:和|以及|还有|同时|另外)\s*', q_clean)
    for p in parts:
        p = p.strip()
        if len(p) > 4 and p not in queries:
            queries.append(p)

    # jieba 提取关键词作为短查询
    try:
        import jieba.analyse
        keywords = jieba.analyse.extract_tags(question, topK=5)
        if keywords:
            kw_query = " ".join(keywords)
            if kw_query not in queries:
                queries.append(kw_query)
    except Exception:
        pass

    return queries[:5]  # 最多 5 个查询角度


# ── RRF 融合（Reciprocal Rank Fusion） ───────────────

def _rrf_fusion(ranked_lists: list[list[tuple]], k: int = 60) -> list[tuple[float, str, dict]]:
    """
    把多个排名列表融合为一个统一排名。
    RRF 公式：score(d) = Σ 1/(k + rank(d))
    k=60 是经验值，越大越平滑不同列表的差异。
    """
    scores: dict[str, float] = {}
    doc_map: dict[str, tuple[str, dict]] = {}

    for ranked in ranked_lists:
        for rank, (_, doc, meta) in enumerate(ranked):
            # 用内容哈希作为去重键
            key = hashlib.md5(doc.encode()).hexdigest()
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank + 1)
            doc_map[key] = (doc, meta)

    merged = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [(score, doc_map[key][0], doc_map[key][1]) for key, score in merged]


# ── 核心检索（向量 + BM25 混合） ─────────────────────

def _coarse_search(query: str, top_k: int) -> list[tuple[float, str, dict]]:
    """粗检索：向量 + BM25 + RRF 融合，不做 Rerank（快速）。"""
    col = _get_collection()
    count = col.count()
    if count == 0:
        return []

    n_coarse = min(RETRIEVAL_TOP_K, count)

    vec_results = col.query(query_texts=[query], n_results=n_coarse)
    vec_ranked = [
        (1.0, doc, meta)
        for doc, meta in zip(vec_results["documents"][0], vec_results["metadatas"][0])
    ]

    bm25_ranked = _search_bm25(query, n_coarse)

    fused = _rrf_fusion([vec_ranked, bm25_ranked] if bm25_ranked else [vec_ranked])
    return fused[:top_k]


def _rerank(query: str, candidates: list[tuple], top_k: int) -> list[tuple[float, str, dict]]:
    """对候选结果做 Rerank 精排，返回 [(score, doc, meta), ...]。"""
    if not candidates:
        return []
    import numpy as np
    reranker = _get_reranker()
    docs_list = [c[1] for c in candidates]
    metas_list = [c[2] for c in candidates]
    pairs = [[query, doc] for doc in docs_list]
    raw_scores = reranker.predict(pairs)
    rerank_scores = (1 / (1 + np.exp(-np.array(raw_scores)))).tolist()
    if isinstance(rerank_scores, float):
        rerank_scores = [rerank_scores]
    ranked = sorted(
        zip(rerank_scores, docs_list, metas_list),
        key=lambda x: x[0], reverse=True
    )
    return [(float(s), d, m) for s, d, m in ranked[:top_k] if s >= RERANK_THRESHOLD]


def _hybrid_search(query: str, top_k: int) -> list[tuple[float, str, dict]]:
    """混合检索：粗检索（大范围）→ 取 top 候选 → Rerank 精排。"""
    coarse = _coarse_search(query, RETRIEVAL_TOP_K)
    candidates = coarse[:RERANK_CANDIDATES]  # 只送少量候选去精排，控制速度
    return _rerank(query, candidates, top_k)


# ── 文本提取 ──────────────────────────────────────────

def _extract_text(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()

    if ext == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(path)
        return "\n".join(page.extract_text() or "" for page in reader.pages)

    elif ext in (".xlsx", ".xls"):
        import openpyxl
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        rows = []
        for ws in wb.worksheets:
            for row in ws.iter_rows(values_only=True):
                line = " | ".join(str(c) for c in row if c is not None)
                if line.strip():
                    rows.append(line)
        return "\n".join(rows)

    elif ext == ".csv":
        with open(path, "r", encoding="utf-8-sig") as f:
            return f.read()

    elif ext in (".html", ".htm"):
        import re
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
        raw = re.sub(r'<style[^>]*>.*?</style>', '', raw, flags=re.DOTALL)
        raw = re.sub(r'<script[^>]*>.*?</script>', '', raw, flags=re.DOTALL)
        raw = re.sub(r'<[^>]+>', ' ', raw)
        return re.sub(r'\s+', ' ', raw).strip()

    else:
        for encoding in ("utf-8", "gbk", "gb2312", "gb18030", "utf-8-sig"):
            try:
                with open(path, "r", encoding=encoding) as f:
                    return f.read()
            except (UnicodeDecodeError, LookupError):
                continue
        return ""


def _chunk_text(text: str) -> list:
    """
    按语义边界切片：优先在段落、句子处断开，避免硬切截断语义。
    策略：段落 → 句子 → 字数兜底
    """
    import re

    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]

    def split_sentences(para):
        parts = re.split(r'(?<=[。！？!?\.…])\s*', para)
        return [p.strip() for p in parts if p.strip()]

    sentences = []
    for para in paragraphs:
        if len(para) <= CHUNK_SIZE:
            sentences.append(para)
        else:
            sentences.extend(split_sentences(para))

    chunks = []
    current = ""
    for sent in sentences:
        if len(sent) > CHUNK_SIZE:
            if current:
                chunks.append(current)
                current = ""
            for i in range(0, len(sent), CHUNK_SIZE - CHUNK_OVERLAP):
                chunks.append(sent[i:i + CHUNK_SIZE])
            continue

        if len(current) + len(sent) + 1 <= CHUNK_SIZE:
            current = (current + "\n" + sent).strip() if current else sent
        else:
            if current:
                chunks.append(current)
            overlap_text = current[-CHUNK_OVERLAP:] if len(current) > CHUNK_OVERLAP else current
            current = (overlap_text + "\n" + sent).strip() if overlap_text else sent

    if current:
        chunks.append(current)

    return [c for c in chunks if c.strip()]


# ── 工具实现 ──────────────────────────────────────────

SUPPORTED_EXTS = {".pdf", ".xlsx", ".xls", ".txt", ".md", ".csv", ".html", ".htm",
                  ".json", ".xml", ".yaml", ".yml", ".log", ".py", ".js", ".ts", ".java", ".go", ".rs"}


def rag_ingest(path: str) -> str:
    abs_path = os.path.abspath(os.path.expanduser(path))

    files = []
    if os.path.isdir(abs_path):
        for root, _, fnames in os.walk(abs_path):
            for fn in fnames:
                if os.path.splitext(fn)[1].lower() in SUPPORTED_EXTS:
                    files.append(os.path.join(root, fn))
    elif os.path.isfile(abs_path):
        files = [abs_path]
    else:
        return json.dumps({"error": f"路径不存在: {path}"}, ensure_ascii=False)

    col = _get_collection()
    total_chunks = 0
    processed = []
    errors = []

    for fp in files:
        try:
            text = _extract_text(fp)
            if not text.strip():
                errors.append(f"{os.path.basename(fp)}: 未能提取到文本")
                continue

            existing = col.get(where={"source": fp})
            if existing["ids"]:
                col.delete(ids=existing["ids"])

            chunks = _chunk_text(text)
            ids, docs, metas = [], [], []
            for i, chunk in enumerate(chunks):
                ids.append(hashlib.md5(f"{fp}:{i}".encode()).hexdigest())
                docs.append(chunk)
                metas.append({"source": fp, "chunk": i, "filename": os.path.basename(fp)})

            col.add(ids=ids, documents=docs, metadatas=metas)
            total_chunks += len(chunks)
            processed.append({"file": os.path.basename(fp), "chunks": len(chunks)})
        except Exception as e:
            errors.append(f"{os.path.basename(fp)}: {e}")

    # 导入后重建 BM25 索引
    _rebuild_bm25()

    return json.dumps({
        "message": f"成功导入 {len(processed)} 个文件，共 {total_chunks} 个文本块",
        "processed": processed,
        "errors": errors,
    }, ensure_ascii=False)


def _build_results(ranked: list, top_k: int) -> tuple[list, float]:
    """将排好序的 (score, doc, meta) 列表转为结果 dict 列表。返回 (results, max_relevance)"""
    results = []
    max_rel = 0.0
    for score, doc, meta in ranked:
        if score < RERANK_THRESHOLD:
            continue
        s = round(float(score), 3)
        results.append({"content": doc, "source": meta.get("filename", ""), "relevance": s})
        if s > max_rel:
            max_rel = s
        if len(results) >= top_k:
            break
    return results, max_rel


def _run_single_round(question: str, queries: list[str], top_k: int) -> tuple[list, float, list, int]:
    """执行单轮检索：对 queries 做粗召回 + RRF + 精排。返回 (results, max_rel, used_queries, coarse_total)"""
    all_ranked_lists = []
    queries_used = []
    coarse_total = 0
    for q in queries:
        ranked = _coarse_search(q, RETRIEVAL_TOP_K)
        if ranked:
            all_ranked_lists.append(ranked)
            queries_used.append(q)
            coarse_total += len(ranked)

    if not all_ranked_lists:
        return [], 0.0, queries_used, 0

    fused = _rrf_fusion(all_ranked_lists)
    candidates = fused[:RERANK_CANDIDATES]
    ranked_final = _rerank(question, candidates, len(candidates))
    results, max_rel = _build_results(ranked_final, top_k)
    return results, max_rel, queries_used, coarse_total


def rag_search(query: str, top_k: int = None) -> str:
    """单次混合检索（向量 + BM25）。适合精确的单一查询。"""
    import time as _time
    t0 = _time.time()

    if top_k is None:
        top_k = RERANK_TOP_K

    col = _get_collection()
    if col.count() == 0:
        return json.dumps({"message": "知识库为空，请先用 rag_ingest 导入文档",
                           "results": [], "instruction": _NO_RESULT_INSTRUCTION}, ensure_ascii=False)

    items = _hybrid_search(query, top_k)
    elapsed = round((_time.time() - t0) * 1000)

    if not items:
        resp = {"query": query, "count": 0, "results": [], "instruction": _NO_RESULT_INSTRUCTION}
        if _TRACE_ENABLED:
            resp["trace"] = {"method": "hybrid", "elapsed_ms": elapsed}
        return json.dumps(resp, ensure_ascii=False)

    results, max_rel = _build_results(items, top_k)
    if max_rel < LOW_RELEVANCE_THRESHOLD:
        resp = {"query": query, "count": 0, "results": [],
                "max_relevance_found": max_rel, "instruction": _NO_RESULT_INSTRUCTION}
        if _TRACE_ENABLED:
            resp["trace"] = {"method": "hybrid", "rerank_input": len(items),
                             "rerank_output": len(results), "max_relevance": max_rel,
                             "elapsed_ms": elapsed}
        return json.dumps(resp, ensure_ascii=False)

    resp = {"query": query, "count": len(results), "results": results}
    if _TRACE_ENABLED:
        resp["trace"] = {"method": "hybrid", "rerank_input": len(items),
                         "rerank_output": len(results), "max_relevance": max_rel,
                         "elapsed_ms": elapsed}
    return json.dumps(resp, ensure_ascii=False)


def rag_ask(question: str, top_k: int = None) -> str:
    """
    Agentic 多轮检索：HyDE 查询扩展 + 自适应循环 + 多路混合搜索 + RRF 融合。

    流程：
    1. HyDE: LLM 生成假设答案 + 子问题拆解（若开启）
    2. fallback: 规则式查询扩展
    3. 自适应循环：首轮检索 → 若相关度低则换策略再搜
    4. RRF 融合 + Rerank 精排
    """
    import time as _time
    t0 = _time.time()
    trace_info = {"method": "hybrid"}

    if top_k is None:
        top_k = RERANK_TOP_K + 2

    col = _get_collection()
    if col.count() == 0:
        return json.dumps({"message": "知识库为空，请先用 rag_ingest 导入文档", "results": []}, ensure_ascii=False)

    # 1. 生成查询（HyDE 优先，规则式 fallback）
    all_queries = []
    if _HYDE_ENABLED:
        hyde_queries = _generate_hyde_queries(question)
        if hyde_queries:
            all_queries = hyde_queries
            trace_info["expansion"] = "hyde"
            trace_info["hyde_queries"] = hyde_queries

    if not all_queries:
        all_queries = _expand_queries(question)
        trace_info["expansion"] = "rule"
        trace_info["rule_queries"] = all_queries

    # 2. 首轮检索
    round_num = 1
    results, max_rel, queries_used, coarse_total = _run_single_round(
        question, all_queries, top_k
    )
    trace_info["rounds"] = [{"round": 1, "queries": queries_used,
                              "coarse_total": coarse_total, "max_relevance": max_rel}]

    # 3. 自适应重试：首轮相关度低且 adaptive 开启
    if _ADAPTIVE_ENABLED and max_rel < _ADAPTIVE_RETRY_THRESHOLD and round_num < _ADAPTIVE_MAX_ROUNDS:
        round_num += 1
        # 换策略：纯关键词查询 + 扩大 top_k
        retry_top_k = int(top_k * _ADAPTIVE_RETRY_TOPK_MUL)
        kw_queries = _expand_queries(question)
        # 取最后 2 条（通常是关键词短查询）或全部
        retry_queries = kw_queries[-2:] if len(kw_queries) > 2 else kw_queries

        r2_results, r2_max_rel, r2_used, r2_coarse = _run_single_round(
            question, retry_queries, retry_top_k
        )
        trace_info["rounds"].append({"round": 2, "queries": r2_used,
                                      "coarse_total": r2_coarse, "max_relevance": r2_max_rel,
                                      "strategy": "keyword_retry"})

        if r2_results and r2_max_rel > max_rel:
            results = r2_results
            max_rel = r2_max_rel
            queries_used = queries_used + r2_used

    elapsed = round((_time.time() - t0) * 1000)
    if _TRACE_ENABLED:
        trace_info["elapsed_ms"] = elapsed
        trace_info["total_rounds"] = round_num

    # 4. 结果判断
    if not results:
        resp = {"question": question, "count": 0, "results": [],
                "queries_used": queries_used, "instruction": _NO_RESULT_INSTRUCTION}
        if _TRACE_ENABLED:
            resp["trace"] = trace_info
        return json.dumps(resp, ensure_ascii=False)

    if max_rel < LOW_RELEVANCE_THRESHOLD:
        resp = {"question": question, "count": 0, "results": [],
                "queries_used": queries_used, "max_relevance_found": max_rel,
                "instruction": _NO_RESULT_INSTRUCTION}
        if _TRACE_ENABLED:
            resp["trace"] = trace_info
        return json.dumps(resp, ensure_ascii=False)

    resp = {"question": question, "count": len(results),
            "queries_used": queries_used, "results": results}
    if _TRACE_ENABLED:
        resp["trace"] = trace_info
    return json.dumps(resp, ensure_ascii=False)


def rag_list() -> str:
    col = _get_collection()
    total = col.count()
    if total == 0:
        return json.dumps({"message": "知识库为空", "files": [], "total_chunks": 0}, ensure_ascii=False)

    all_meta = col.get(include=["metadatas"])["metadatas"]
    file_stats = {}
    for m in all_meta:
        src = m.get("source", "")
        name = m.get("filename", src)
        if src not in file_stats:
            file_stats[src] = {"filename": name, "chunks": 0}
        file_stats[src]["chunks"] += 1

    files = [{"filename": v["filename"], "path": k, "chunks": v["chunks"]} for k, v in file_stats.items()]
    return json.dumps({"total_chunks": total, "file_count": len(files), "files": files}, ensure_ascii=False)


def rag_delete(filename: str) -> str:
    col = _get_collection()
    all_data = col.get(include=["metadatas"])
    ids_to_delete = [
        doc_id for doc_id, meta in zip(all_data["ids"], all_data["metadatas"])
        if filename in meta.get("source", "") or filename == meta.get("filename", "")
    ]
    if not ids_to_delete:
        return json.dumps({"error": f"未找到: {filename}"}, ensure_ascii=False)

    col.delete(ids=ids_to_delete)
    # 删除后重建 BM25 索引
    _rebuild_bm25()
    return json.dumps({"message": f"已删除 {len(ids_to_delete)} 个文本块", "filename": filename}, ensure_ascii=False)


# ── MCP 注册 ──────────────────────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "rag_ingest",
            "description": "将文件或整个文件夹导入知识库（支持 PDF、Excel、TXT、Markdown、CSV）。导入后可用 rag_ask 或 rag_search 检索。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径或文件夹路径"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rag_ask",
            "description": (
                "【推荐】Agentic 多轮检索：自动将问题扩展为多个搜索角度，混合向量+关键词检索，融合去重后返回最相关片段。"
                "适合复杂问题、需要从多角度检索、或不确定关键词时使用。"
                "返回结果中包含 queries_used（实际使用的查询列表）和每条结果的 relevance 分数，"
                "如果分数普遍偏低（< 0.3），可再用 rag_search 补充精确查询。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "用户的完整问题"},
                    "top_k":    {"type": "integer", "description": "返回结果数，默认 6"},
                },
                "required": ["question"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rag_search",
            "description": (
                "单次混合检索（向量语义 + BM25 关键词），适合精确查找已知术语、条款、数字等。"
                "可多次调用不同关键词来补充检索。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "检索关键词或短句"},
                    "top_k": {"type": "integer", "description": "返回结果数，默认 4"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rag_list",
            "description": "列出知识库中已导入的所有文件。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rag_delete",
            "description": "从知识库中删除某个文件的向量数据。",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "文件名或路径（部分匹配即可）"},
                },
                "required": ["filename"],
            },
        },
    },
]

TOOL_MAP = {
    "rag_ingest":  rag_ingest,
    "rag_ask":     rag_ask,
    "rag_search":  rag_search,
    "rag_list":    rag_list,
    "rag_delete":  rag_delete,
}

TOOL_LABELS = {
    "rag_ingest":  "📥 导入知识库",
    "rag_ask":     "🤖 Agentic 检索",
    "rag_search":  "🔍 知识库检索",
    "rag_list":    "📚 查看知识库",
    "rag_delete":  "🗑️ 删除知识库文件",
}

PERMISSION_TOOLS = set()
