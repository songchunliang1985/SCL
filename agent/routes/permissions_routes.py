"""权限管理路由"""
import os
from flask import Blueprint, request, jsonify, current_app

bp = Blueprint('permissions', __name__)


def get_registry():
    return current_app.extensions['registry']


@bp.route("/api/allowed_paths", methods=["GET"])
def get_allowed_paths():
    return jsonify(sorted(list(get_registry().permission_mgr.allowed_paths)))


@bp.route("/api/allowed_paths", methods=["POST"])
def add_allowed_path():
    data = request.get_json()
    abs_path = os.path.abspath(os.path.expanduser(data.get("path", "")))
    if os.path.exists(abs_path):
        get_registry().permission_mgr.allowed_paths.add(abs_path)
        return jsonify({"ok": True, "path": abs_path})
    return jsonify({"error": f"路径不存在: {abs_path}"}), 400


@bp.route("/api/allowed_paths", methods=["DELETE"])
def remove_allowed_path():
    abs_path = os.path.abspath(os.path.expanduser(request.get_json().get("path", "")))
    get_registry().permission_mgr.allowed_paths.discard(abs_path)
    return jsonify({"ok": True})


@bp.route("/api/approve_tool", methods=["POST"])
def approve_tool():
    data = request.get_json()
    req_id = data.get("request_id")
    approved = data.get("approved", False)
    mgr = get_registry().permission_mgr
    if req_id in mgr.pending_approvals:
        if approved:
            path = mgr.pending_approvals[req_id]["path"]
            auth_path = path if os.path.isdir(path) else os.path.dirname(path)
            mgr.allowed_paths.add(auth_path)
            mgr.pending_approvals[req_id]["approved"] = True
        mgr.pending_approvals[req_id]["event"].set()
        return jsonify({"ok": True})
    return jsonify({"error": "请求不存在或已过期"}), 404


@bp.route("/api/browse", methods=["POST"])
def browse_directory():
    data = request.get_json()
    abs_path = os.path.realpath(os.path.abspath(os.path.expanduser(data.get("path", "~"))))
    _home = os.path.realpath(os.path.expanduser("~"))
    if not (abs_path == _home or abs_path.startswith(_home + os.sep)):
        return jsonify({"error": "不允许访问该路径"}), 403
    if not os.path.isdir(abs_path):
        return jsonify({"error": "不是一个目录"}), 400
    entries = []
    try:
        for name in sorted(os.listdir(abs_path)):
            if name.startswith("."):
                continue
            full = os.path.join(abs_path, name)
            is_dir = os.path.isdir(full)
            entries.append({
                "name": name, "type": "directory" if is_dir else "file",
                "path": full, "size": os.path.getsize(full) if not is_dir else None,
            })
    except PermissionError:
        return jsonify({"error": "没有权限"}), 403
    return jsonify({"path": abs_path, "parent": os.path.dirname(abs_path), "entries": entries})
