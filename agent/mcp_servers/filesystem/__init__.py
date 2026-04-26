"""
MCP Server: Filesystem — 文件系统浏览、读写、搜索
"""

import json
import os
import glob as glob_mod
from datetime import datetime

# 读取本模块配置
_dir = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(_dir, "config.json"), "r") as f:
    _cfg = json.load(f)

READ_MAX_LINES = _cfg.get("read_max_lines", 500)
MAX_FILE_SIZE = _cfg.get("max_file_size", 10 * 1024 * 1024)
SEARCH_MAX_RESULTS = _cfg.get("search_max_results", 100)

# 路径穿越防护：允许访问的根目录，默认用户主目录
# 可在 config.json 中用 "allowed_root" 字段覆盖
_raw_root = _cfg.get("allowed_root", "~")
ALLOWED_ROOT = os.path.realpath(os.path.expanduser(_raw_root))


def _check_path(abs_path: str) -> bool:
    """返回 True 表示路径在允许范围内，False 表示路径穿越。"""
    real = os.path.realpath(abs_path)
    return real == ALLOWED_ROOT or real.startswith(ALLOWED_ROOT + os.sep)

# 需要权限检查的工具名集合（供 app.py 使用）
PERMISSION_TOOLS = {"list_directory", "read_file", "write_file", "search_files", "file_info"}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "列出指定目录下的文件和文件夹。用于浏览本地文件系统。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "目录路径，如 ~/Desktop 或 /path/to/folder"},
                    "show_hidden": {"type": "boolean", "description": "是否显示隐藏文件，默认不显示"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取本地文件的内容。支持文本文件如 .py, .txt, .json, .md 等。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径"},
                    "max_lines": {"type": "integer", "description": "最多读取行数，默认500"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "写入内容到本地文件（覆盖写入）。可用于创建或修改文件。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径"},
                    "content": {"type": "string", "description": "要写入的内容"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_files",
            "description": "按文件名模式在目录中搜索文件，如搜索所有 .py 文件。",
            "parameters": {
                "type": "object",
                "properties": {
                    "directory": {"type": "string", "description": "搜索起始目录"},
                    "pattern": {"type": "string", "description": "文件名匹配模式，如 *.py、*.txt、test_*"},
                    "recursive": {"type": "boolean", "description": "是否递归搜索子目录，默认是"},
                },
                "required": ["directory", "pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "file_info",
            "description": "获取文件或目录的详细信息（大小、创建时间、修改时间等）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件或目录路径"},
                },
                "required": ["path"],
            },
        },
    },
]


def list_directory(path: str = "~", show_hidden: bool = False) -> str:
    abs_path = os.path.abspath(os.path.expanduser(path))
    if not os.path.isdir(abs_path):
        return json.dumps({"error": f"不是一个目录: {path}"}, ensure_ascii=False)
    entries = []
    try:
        for name in sorted(os.listdir(abs_path)):
            if not show_hidden and name.startswith("."):
                continue
            full = os.path.join(abs_path, name)
            is_dir = os.path.isdir(full)
            size = os.path.getsize(full) if not is_dir else None
            entries.append({"name": name, "type": "directory" if is_dir else "file", "size": size})
    except PermissionError:
        return json.dumps({"error": f"没有权限访问: {path}"}, ensure_ascii=False)
    return json.dumps({"path": abs_path, "count": len(entries), "entries": entries}, ensure_ascii=False)


def read_file(path: str, max_lines: int = None) -> str:
    if max_lines is None:
        max_lines = READ_MAX_LINES
    abs_path = os.path.abspath(os.path.expanduser(path))
    if not _check_path(abs_path):
        return json.dumps({"error": f"路径超出允许范围，拒绝访问: {path}"}, ensure_ascii=False)
    if not os.path.isfile(abs_path):
        return json.dumps({"error": f"文件不存在: {path}"}, ensure_ascii=False)
    size = os.path.getsize(abs_path)
    if size > MAX_FILE_SIZE:
        return json.dumps({"error": f"文件过大 ({size} bytes)"}, ensure_ascii=False)
    try:
        with open(abs_path, "r", encoding="utf-8") as f:
            lines = []
            for i, line in enumerate(f):
                if i >= max_lines:
                    lines.append(f"\n... 已截断，共读取 {max_lines} 行")
                    break
                lines.append(line)
        return json.dumps({"path": abs_path, "size": size, "content": "".join(lines)}, ensure_ascii=False)
    except UnicodeDecodeError:
        return json.dumps({"error": "无法读取，可能是二进制文件"}, ensure_ascii=False)


def write_file(path: str, content: str) -> str:
    abs_path = os.path.abspath(os.path.expanduser(path))
    if not _check_path(abs_path):
        return json.dumps({"error": f"路径超出允许范围，拒绝写入: {path}"}, ensure_ascii=False)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    with open(abs_path, "w", encoding="utf-8") as f:
        f.write(content)
    return json.dumps({"path": abs_path, "size": os.path.getsize(abs_path), "message": "写入成功"}, ensure_ascii=False)


def search_files(directory: str = "~", pattern: str = "*", recursive: bool = True) -> str:
    abs_dir = os.path.abspath(os.path.expanduser(directory))
    if recursive:
        search_pattern = os.path.join(abs_dir, "**", pattern)
    else:
        search_pattern = os.path.join(abs_dir, pattern)
    matches = sorted(glob_mod.glob(search_pattern, recursive=recursive))[:SEARCH_MAX_RESULTS]
    results = []
    for m in matches:
        is_dir = os.path.isdir(m)
        results.append({"path": m, "type": "directory" if is_dir else "file", "size": os.path.getsize(m) if not is_dir else None})
    return json.dumps({"directory": abs_dir, "pattern": pattern, "count": len(results), "results": results}, ensure_ascii=False)


def file_info(path: str) -> str:
    abs_path = os.path.abspath(os.path.expanduser(path))
    if not os.path.exists(abs_path):
        return json.dumps({"error": f"路径不存在: {path}"}, ensure_ascii=False)
    stat = os.stat(abs_path)
    info = {
        "path": abs_path,
        "type": "directory" if os.path.isdir(abs_path) else "file",
        "size": stat.st_size,
        "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
        "permissions": oct(stat.st_mode)[-3:],
    }
    try:
        info["created"] = datetime.fromtimestamp(stat.st_birthtime).strftime("%Y-%m-%d %H:%M:%S")
    except AttributeError:
        info["created"] = info["modified"]
    return json.dumps(info, ensure_ascii=False)


TOOL_MAP = {
    "list_directory": list_directory,
    "read_file": read_file,
    "write_file": write_file,
    "search_files": search_files,
    "file_info": file_info,
}

TOOL_LABELS = {
    "list_directory": "📂 浏览目录",
    "read_file": "📄 读取文件",
    "write_file": "✏️ 写入文件",
    "search_files": "🔎 搜索文件",
    "file_info": "ℹ️ 文件信息",
}
