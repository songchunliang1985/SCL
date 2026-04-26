"""
RAG 检索效果测试脚本
用法：python3 rag_test.py
"""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp_servers.rag import rag_search, rag_list, _cfg

# ── 打印当前配置 ──────────────────────────────────────
print("=" * 60)
print("当前配置")
print("=" * 60)
print(f"  chunk_size    : {_cfg['chunk_size']}  （每块字数）")
print(f"  chunk_overlap : {_cfg['chunk_overlap']}  （重叠字数）")
print(f"  top_k         : {_cfg['top_k']}   （返回几条）")
print(f"  embedding_model: {_cfg['embedding_model']}")

# ── 打印知识库文件 ─────────────────────────────────────
from mcp_servers.rag import rag_list
files_data = json.loads(rag_list())
print(f"\n知识库共 {files_data.get('file_count', 0)} 个文件，"
      f"{files_data.get('total_chunks', 0)} 个切片")
for f in files_data.get("files", []):
    print(f"  📄 {f['filename']}  ({f['chunks']} 块)")

# ── 输入问题 ──────────────────────────────────────────
print("\n" + "=" * 60)
query = input("输入你的问题：").strip()
if not query:
    print("问题为空，退出")
    sys.exit()

# ── 执行检索 ──────────────────────────────────────────
result = json.loads(rag_search(query))

print(f"\n检索到 {result['count']} 条结果：")
print("=" * 60)

for i, item in enumerate(result["results"], 1):
    relevance = item["relevance"]
    # 相关度用颜色区分
    if relevance >= 0.7:
        tag = "🟢 高相关"
    elif relevance >= 0.5:
        tag = "🟡 中等"
    else:
        tag = "🔴 低相关"

    print(f"\n【第{i}条】{tag}  相关度: {relevance}  来源: {item['source']}")
    print("-" * 40)
    # 显示前300字
    text = item["content"].strip()
    print(text[:300] + ("..." if len(text) > 300 else ""))

print("\n" + "=" * 60)
print("改完 config.json 记得重新导入文档，再跑本脚本对比！")
