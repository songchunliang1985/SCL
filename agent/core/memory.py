"""跨会话记忆：提取并持久化对话中的用户关键信息。"""
import json
import os
import threading
import requests
from datetime import datetime

_EXTRACT_URL = "https://api.deepseek.com/chat/completions"


class MemoryStore:
    """持久化记忆存储。每次对话结束后异步提取事实，下次对话注入 system prompt。"""

    def __init__(self, memory_file: str):
        self._file = memory_file
        self._lock = threading.Lock()

    def _api_key(self) -> str:
        return os.environ.get("DEEPSEEK_API_KEY", "")

    def load_recent(self, n: int = 8) -> list[str]:
        """返回最近 n 条记忆文本，用于注入 system prompt。"""
        with self._lock:
            if not os.path.exists(self._file):
                return []
            try:
                with open(self._file, "r", encoding="utf-8") as f:
                    memories = json.load(f)
                return [m["fact"] for m in memories[-n:]]
            except Exception:
                return []

    def save_facts(self, facts: list[str]):
        """追加若干事实条目，最多保留 100 条（FIFO）。"""
        if not facts:
            return
        with self._lock:
            memories = []
            if os.path.exists(self._file):
                try:
                    with open(self._file, "r", encoding="utf-8") as f:
                        memories = json.load(f)
                except Exception:
                    pass
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            memories.extend({"fact": f, "created_at": now} for f in facts)
            memories = memories[-100:]
            with open(self._file, "w", encoding="utf-8") as f:
                json.dump(memories, f, ensure_ascii=False, indent=2)

    def extract_and_save(self, user_msg: str, reply: str):
        """调 LLM 从对话中提取关键事实并保存。设计为在 daemon thread 中调用。"""
        api_key = self._api_key()
        if not api_key or not user_msg or len(user_msg.strip()) < 10:
            return

        prompt = (
            "从以下对话中提取值得长期记忆的用户信息（偏好、身份、重要结论），"
            "每条一行，最多 3 条。若无值得记忆的内容，输出空。\n\n"
            f"用户：{user_msg[:300]}\n助手：{reply[:300]}"
        )
        try:
            resp = requests.post(
                _EXTRACT_URL,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 150,
                    "temperature": 0.1,
                },
                timeout=10,
            )
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"].strip()
            if not text:
                return
            facts = [
                line.strip().lstrip("-•·123456789.) ")
                for line in text.splitlines()
                if line.strip()
            ]
            self.save_facts([f for f in facts if len(f) > 5])
        except Exception:
            pass  # 记忆提取失败不影响主流程
