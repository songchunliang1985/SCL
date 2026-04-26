"""
MCP Server: Web — 联网搜索、网页抓取
"""

import json
import os
import re
import requests
from ddgs import DDGS

# 读取本模块配置
_dir = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(_dir, "config.json"), "r") as f:
    _cfg = json.load(f)

FETCH_TIMEOUT = _cfg.get("fetch_timeout", 15)
FETCH_MAX_LENGTH = _cfg.get("fetch_max_length", 3000)
SEARCH_MAX_RESULTS = _cfg.get("search_max_results", 5)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "联网搜索，获取最新的网络信息。当用户询问最新新闻、实时信息、或你不确定的事实时使用此工具。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_webpage",
            "description": "抓取指定网页的文本内容。当需要读取某个具体网址的详细内容时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "要抓取的网页 URL"}
                },
                "required": ["url"],
            },
        },
    },
]


def web_search(query: str) -> str:
    try:
        raw_results = DDGS().text(query, max_results=SEARCH_MAX_RESULTS, timelimit="m")
        results = []
        for r in raw_results:
            results.append({
                "title": r.get("title", ""),
                "snippet": r.get("body", ""),
                "url": r.get("href", ""),
            })
        return json.dumps({"query": query, "results": results or [{"info": "未找到结果"}]}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"query": query, "error": str(e)}, ensure_ascii=False)


def fetch_webpage(url: str) -> str:
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
        resp = requests.get(url, headers=headers, timeout=FETCH_TIMEOUT)
        resp.raise_for_status()
        html = resp.text
        html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
        html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL)
        text = re.sub(r'<[^>]+>', ' ', html)
        text = re.sub(r'\s+', ' ', text).strip()[:FETCH_MAX_LENGTH]
        return json.dumps({"url": url, "content": text}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"url": url, "error": str(e)}, ensure_ascii=False)


TOOL_MAP = {
    "web_search": web_search,
    "fetch_webpage": fetch_webpage,
}

TOOL_LABELS = {
    "web_search": "🔍 联网搜索",
    "fetch_webpage": "🌐 抓取网页",
}
