"""消息列表字符估算与裁剪，防止超出 context window。"""

_MAX_CHARS = 80_000  # 约 40k tokens，为 DeepSeek 64k context 留安全余量


def _estimate_chars(messages: list) -> int:
    total = 0
    for m in messages:
        content = m.get("content") or ""
        if isinstance(content, list):
            content = " ".join(c.get("text", "") for c in content if isinstance(c, dict))
        total += len(str(content))
        if m.get("tool_calls"):
            total += len(str(m["tool_calls"]))
    return total


def trim_messages(messages: list) -> list:
    """若消息总字符超出阈值，逐轮删除最旧的完整对话轮次，始终保留 system 消息。

    每次删除单位：一条 user 消息 + 其后所有非 user 消息（工具调用/结果/assistant 回复）。
    这样保证剩余 messages 始终以 user 消息开头，格式合法。
    """
    if _estimate_chars(messages) <= _MAX_CHARS:
        return messages

    system  = [m for m in messages if m.get("role") == "system"]
    history = [m for m in messages if m.get("role") != "system"]

    while _estimate_chars(system + history) > _MAX_CHARS:
        if not history or history[0].get("role") != "user":
            break
        history.pop(0)
        while history and history[0].get("role") != "user":
            history.pop(0)

    return system + history
