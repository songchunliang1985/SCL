"""流式 LLM API 客户端"""
import json
import threading
import requests
import config as cfg


class LlmClient:
    """封装对 LLM API 的流式调用逻辑。
    支持多提供商，自动检测多模态消息并切换视觉模型。
    """

    def stream(self, model: str, provider: dict, messages: list, tools: list, cancel_event=None):
        """发起流式 LLM 请求。

        参数：
            model        : 模型 ID
            provider     : 提供商配置字典（含 api_url, api_key 等）
            messages     : 完整的对话消息列表
            tools        : 工具定义列表
            cancel_event : threading.Event，set() 后中断

        yield 类型：
            ("content_chunk", str)
            ("tool_calls", dict)
            ("usage", dict)
        """
        from queue import Queue, Empty

        if not provider or not provider.get("api_key"):
            raise ValueError(f"模型 {model} 的 API Key 未配置")

        # DeepSeek 不支持图片输入，提前拦截给出明确错误
        has_images = any(
            isinstance(m.get("content"), list) and any(c.get("type") == "image_url" for c in m["content"])
            for m in messages if isinstance(m, dict)
        )
        if has_images:
            raise ValueError("当前模型不支持图片输入，请删除图片后重试")

        headers = {"Authorization": f"Bearer {provider['api_key']}", "Content-Type": "application/json"}
        body = {
            "model": model,
            "messages": messages,
            "stream": True,
            "stream_options": {"include_usage": True},
            "tools": tools,
            "tool_choice": "auto",
        }

        resp = requests.post(provider["api_url"], headers=headers, json=body, timeout=cfg.API_TIMEOUT, stream=True)
        if resp.status_code >= 400:
            raise Exception(f"{resp.status_code} {resp.reason}: {resp.text}")
        resp.raise_for_status()
        resp.encoding = "utf-8"

        line_q = Queue()
        _SENTINEL = object()

        def _reader():
            try:
                for line in resp.iter_lines(decode_unicode=True):
                    line_q.put(line)
                line_q.put(_SENTINEL)
            except Exception as e:
                line_q.put(e)
            finally:
                try:
                    resp.close()
                except Exception:
                    pass

        threading.Thread(target=_reader, daemon=True).start()

        tool_calls_map = {}
        content_buf = []
        reasoning_buf = []
        streaming_text = True
        usage_data = None

        try:
            while True:
                if cancel_event and cancel_event.is_set():
                    resp.close()
                    return
                try:
                    item = line_q.get(timeout=0.3)
                except Empty:
                    continue

                if item is _SENTINEL:
                    break
                if isinstance(item, Exception):
                    raise item

                line = item
                if not line or not line.startswith("data: "):
                    continue
                payload = line[6:]
                if payload.strip() == "[DONE]":
                    break
                try:
                    chunk = json.loads(payload)
                except json.JSONDecodeError:
                    continue

                if chunk.get("usage"):
                    usage_data = chunk["usage"]

                delta = chunk.get("choices", [{}])[0].get("delta", {})

                if delta.get("tool_calls"):
                    streaming_text = False
                    for tc in delta["tool_calls"]:
                        idx = tc.get("index", 0)
                        if idx not in tool_calls_map:
                            tool_calls_map[idx] = {
                                "id": tc.get("id", ""),
                                "type": "function",
                                "function": {"name": "", "arguments": ""},
                            }
                        if tc.get("id"):
                            tool_calls_map[idx]["id"] = tc["id"]
                        fn = tc.get("function", {})
                        if fn.get("name"):
                            tool_calls_map[idx]["function"]["name"] = fn["name"]
                        if fn.get("arguments"):
                            tool_calls_map[idx]["function"]["arguments"] += fn["arguments"]

                if delta.get("reasoning_content"):
                    reasoning_buf.append(delta["reasoning_content"])

                if delta.get("content"):
                    if streaming_text:
                        yield ("content_chunk", delta["content"])
                    content_buf.append(delta["content"])
        except GeneratorExit:
            resp.close()
            return

        if tool_calls_map:
            tool_calls = [tool_calls_map[i] for i in sorted(tool_calls_map.keys())]
            text_content = "".join(content_buf) if content_buf else None
            msg = {"role": "assistant", "content": text_content, "tool_calls": tool_calls}
            if reasoning_buf:
                msg["reasoning_content"] = "".join(reasoning_buf)
            yield ("tool_calls", msg)

        if usage_data:
            yield ("usage", {"model": model, **usage_data})
