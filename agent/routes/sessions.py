"""会话 CRUD 路由"""
import uuid
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app

bp = Blueprint('sessions', __name__)


def get_registry():
    return current_app.extensions['registry']


@bp.route("/api/sessions", methods=["GET"])
def list_sessions():
    store = get_registry().session_store
    sessions = store.load()
    result = [
        {"id": sid, "title": s.get("title", "新对话"),
         "created_at": s.get("created_at", ""), "updated_at": s.get("updated_at", ""),
         "message_count": len(s.get("messages", []))}
        for sid, s in sessions.items()
    ]
    result.sort(key=lambda x: x["updated_at"], reverse=True)
    return jsonify(result)


@bp.route("/api/sessions", methods=["POST"])
def create_session():
    store = get_registry().session_store
    sessions = store.load()
    sid = str(uuid.uuid4())[:8]
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sessions[sid] = {"title": "新对话", "created_at": now, "updated_at": now, "messages": []}
    store.save(sessions)
    return jsonify({"id": sid, "title": "新对话", "created_at": now, "updated_at": now, "message_count": 0})


@bp.route("/api/sessions/<sid>", methods=["GET"])
def get_session(sid):
    sessions = get_registry().session_store.load()
    s = sessions.get(sid)
    if not s:
        return jsonify({"error": "会话不存在"}), 404
    return jsonify({"id": sid, **s})


@bp.route("/api/sessions/<sid>", methods=["DELETE"])
def delete_session(sid):
    store = get_registry().session_store
    sessions = store.load()
    if sid in sessions:
        del sessions[sid]
        store.save(sessions)
    return jsonify({"ok": True})


@bp.route("/api/sessions/<sid>/title", methods=["PUT"])
def update_title(sid):
    store = get_registry().session_store
    sessions = store.load()
    if sid not in sessions:
        return jsonify({"error": "会话不存在"}), 404
    sessions[sid]["title"] = request.get_json().get("title", "新对话")
    store.save(sessions)
    return jsonify({"ok": True})
