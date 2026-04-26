"""RAG 知识库路由"""
import os
import json
from flask import Blueprint, request, jsonify, current_app
from werkzeug.utils import secure_filename

bp = Blueprint('rag', __name__)

# RAG 文档存储目录
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAG_DOCS_DIR = os.path.join(_BASE_DIR, "data", "rag_docs")
os.makedirs(RAG_DOCS_DIR, exist_ok=True)


@bp.route("/api/rag/ingest", methods=["POST"])
def rag_ingest_api():
    files = request.files.getlist("files")
    if not files:
        return jsonify({"error": "没有文件"}), 400
    from mcp_servers.rag import rag_ingest
    results = []
    for f in files:
        filename = secure_filename(f.filename)
        if not filename:
            results.append({"error": f"文件名非法，已跳过: {f.filename}"})
            continue
        save_path = os.path.join(RAG_DOCS_DIR, filename)
        if not os.path.realpath(save_path).startswith(os.path.realpath(RAG_DOCS_DIR) + os.sep):
            results.append({"error": f"非法路径，已拒绝: {f.filename}"})
            continue
        f.save(save_path)
        results.append(json.loads(rag_ingest(save_path)))
    return jsonify({"ok": True, "results": results})


@bp.route("/api/rag/search", methods=["POST"])
def rag_search_api():
    data = request.get_json()
    query = data.get("query", "")
    top_k = data.get("top_k", 5)
    if not query:
        return jsonify({"results": []})
    from mcp_servers.rag import rag_search
    return jsonify(json.loads(rag_search(query, top_k)))


@bp.route("/api/rag/list", methods=["GET"])
def rag_list_api():
    from mcp_servers.rag import rag_list
    return jsonify(json.loads(rag_list()))


@bp.route("/api/rag/delete", methods=["POST"])
def rag_delete_api():
    data = request.get_json()
    filename = data.get("filename", "")
    if not filename:
        return jsonify({"error": "缺少文件名"}), 400
    from mcp_servers.rag import rag_delete
    return jsonify(json.loads(rag_delete(filename)))
