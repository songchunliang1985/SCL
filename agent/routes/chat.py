"""主聊天接口 —— SSE 流式响应"""
import json
import threading
from flask import Blueprint, request, Response, stream_with_context, jsonify, current_app

bp = Blueprint('chat', __name__)


def get_registry():
    return current_app.extensions['registry']


def sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@bp.route("/api/stop", methods=["POST"])
def stop_session():
    sid = request.get_json().get("session_id")
    cancel_flags = get_registry().cancel_flags
    if sid and sid in cancel_flags:
        cancel_flags[sid].set()
        return jsonify({"ok": True})
    return jsonify({"error": "会话不存在或未在进行"}), 404


@bp.route("/chat", methods=["POST"])
def chat():
    reg = get_registry()
    data = request.get_json()
    messages = data.get("messages", [])
    session_id = data.get("session_id")
    rag_mode = data.get("rag_mode", False)

    cancel_evt = threading.Event()
    if session_id:
        reg.cancel_flags[session_id] = cancel_evt

    def generate():
        try:
            for event_str in reg.agent.run_stream(messages, cancel_event=cancel_evt, rag_mode=rag_mode):
                if 'event: reply_done\n' in event_str or 'event: reply\n' in event_str:
                    try:
                        json_str = event_str.split("data: ", 1)[1].strip()
                        reply_data = json.loads(json_str)
                        if not reply_data.get("is_prefix"):
                            content = reply_data.get("full_content") or reply_data.get("content", "")
                            if session_id and content:
                                reg.session_store.save_message(session_id, messages, content)
                            if reg.memory_store and content:
                                _user_msg = next(
                                    (m.get("content") for m in reversed(messages) if m.get("role") == "user"),
                                    "",
                                )
                                if isinstance(_user_msg, list):
                                    _user_msg = " ".join(
                                        p.get("text", "") for p in _user_msg if isinstance(p, dict)
                                    )
                                threading.Thread(
                                    target=reg.memory_store.extract_and_save,
                                    args=(_user_msg or "", content),
                                    daemon=True,
                                ).start()
                    except Exception:
                        pass
                yield event_str
            yield sse_event("done", {})
        finally:
            if session_id:
                reg.cancel_flags.pop(session_id, None)

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
