"""会话持久化管理"""
import json
import os
from datetime import datetime


class SessionStore:
    """封装会话 JSON 文件的读写操作。"""

    def __init__(self, sessions_file: str):
        self._sessions_file = sessions_file

    def load(self) -> dict:
        if os.path.exists(self._sessions_file):
            with open(self._sessions_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def save(self, sessions: dict):
        with open(self._sessions_file, "w", encoding="utf-8") as f:
            json.dump(sessions, f, ensure_ascii=False, indent=2)

    def save_message(self, sid: str, messages: list, reply: str):
        sessions = self.load()
        if sid not in sessions:
            return
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sessions[sid]["messages"] = messages + [{"role": "assistant", "content": reply}]
        sessions[sid]["updated_at"] = now
        if sessions[sid]["title"] == "新对话" and messages:
            for m in messages:
                if m["role"] == "user":
                    content = m["content"]
                    if isinstance(content, list):
                        content = next((c.get("text", "") for c in content if c.get("type") == "text"), "图片对话")
                    title = content[:30] + ("..." if len(content) > 30 else "")
                    sessions[sid]["title"] = title
                    break
        self.save(sessions)
