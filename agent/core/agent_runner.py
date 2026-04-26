"""Agent 主循环 —— 多轮 LLM + 工具执行"""
import json
import os
import uuid
import threading
from datetime import datetime

import config as cfg
from mcp_servers import load_skills_index, get_skill_content


class AgentRunner:
    """封装 Agent 的完整执行流程。"""

    def __init__(self, tools: list, tool_map: dict, tool_labels: dict,
                 file_tools: set, permission_mgr, llm_client, model_resolver):
        """
        参数:
            model_resolver: callable，返回 (model_id, provider_dict) 元组
        """
        self._tools = tools
        self._tool_map = tool_map
        self._tool_labels = tool_labels
        self._file_tools = file_tools
        self._permission_mgr = permission_mgr
        self._llm_client = llm_client
        self._model_resolver = model_resolver

        # 注册 use_skill 工具
        _use_skill_tool = {
            "type": "function",
            "function": {
                "name": "use_skill",
                "description": "加载并激活一个技能的详细指令。当你判断用户的问题匹配某个技能时调用此工具，返回该技能的完整行为指南。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "skill_name": {
                            "type": "string",
                            "description": "技能文件夹名称，如 translate、code-review"
                        }
                    },
                    "required": ["skill_name"],
                },
            },
        }
        self._tools.append(_use_skill_tool)
        self._tool_map["use_skill"] = lambda skill_name: self._handle_use_skill(skill_name)
        self._tool_labels["use_skill"] = "📋 加载技能"

    @staticmethod
    def _sse_event(event: str, data: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    def _handle_use_skill(self, skill_name: str) -> str:
        content = get_skill_content(skill_name)
        if content is None:
            available = [s["key"] for s in load_skills_index()]
            return json.dumps({"error": f"技能 '{skill_name}' 不存在", "available_skills": available}, ensure_ascii=False)
        return json.dumps({"skill": skill_name, "instructions": content}, ensure_ascii=False)

    def _try_parse_text_tool_call(self, text: str):
        """尝试把模型输出的文本解析为工具调用（兜底处理各种格式）。"""
        import re as _re
        match = _re.search(r'\{[\s\S]+\}', text)
        if not match:
            return None
        try:
            obj = json.loads(match.group())
        except json.JSONDecodeError:
            return None

        fn_name, fn_args = None, {}
        _NAME_KEYS = ("command", "name", "action", "tool", "function", "tool_name")
        _ARGS_KEYS = ("kwargs", "arguments", "action_input", "parameters", "input", "params")

        for k in _NAME_KEYS:
            if k in obj and isinstance(obj[k], str) and obj[k] in self._tool_map:
                fn_name = obj[k]
                break

        if not fn_name:
            for v in obj.values():
                if isinstance(v, str) and v in self._tool_map:
                    fn_name = v
                    break

        if not fn_name:
            return None

        for k in _ARGS_KEYS:
            if k in obj and isinstance(obj[k], dict):
                fn_args = obj[k]
                break
        else:
            fn_args = {k: v for k, v in obj.items()
                       if k not in _NAME_KEYS and not isinstance(v, dict)
                       and k not in ("thoughts", "thought", "thinking", "reason", "reasoning")}

        return {
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": f"fallback_{fn_name}",
                "type": "function",
                "function": {"name": fn_name, "arguments": json.dumps(fn_args, ensure_ascii=False)},
            }],
        }

    def _run_long_tool(self, fn, fn_args, step, emoji, label, interval, cancel_event):
        """后台线程执行长时间工具（图片/视频生成），主线程发心跳。"""
        result_holder = [None]
        done_event = threading.Event()

        def _worker():
            try:
                result_holder[0] = fn(**fn_args)
            except Exception as e:
                result_holder[0] = json.dumps({"error": str(e)}, ensure_ascii=False)
            done_event.set()

        threading.Thread(target=_worker, daemon=True).start()
        elapsed = 0
        events = []
        while not done_event.is_set():
            done_event.wait(timeout=interval)
            elapsed += interval
            if not done_event.is_set():
                events.append(self._sse_event("thinking", {
                    "step": step, "message": f"{emoji} {label}... ({elapsed}s)"
                }))
            if cancel_event and cancel_event.is_set():
                break
        return result_holder[0] or json.dumps({"error": f"{label}被取消"}), events

    def run_stream(self, user_messages: list[dict], cancel_event: threading.Event = None, rag_mode: bool = False):
        """驱动完整 Agent 循环，yield SSE 格式字符串。"""
        import time as _time

        today = datetime.now().strftime("%Y年%m月%d日")

        paths_hint = ""
        if self._permission_mgr.allowed_paths:
            paths_hint = (
                f"用户已授权你访问以下路径: {', '.join(sorted(self._permission_mgr.allowed_paths))}。"
                f"当用户提到\"这个项目\"、\"这个工程\"、\"分析项目\"等涉及项目的请求时，"
                f"你必须使用 list_directory 和 read_file 工具来浏览和读取这些路径下的文件，不要凭空猜测。"
            )

        skills_index = load_skills_index()
        skills_hint = "\n".join(
            f"- **{s['key']}**: {s['name']} — {s['description']}"
            for s in skills_index
        ) if skills_index else "暂无可用技能"

        system_content = cfg.SYSTEM_PROMPT.format(
            today=today, paths_hint=paths_hint, skills_hint=skills_hint
        )
        # RAG 模式：限制只能用 RAG 工具
        _RAG_TOOL_NAMES = {"rag_ask", "rag_search", "rag_list", "rag_delete", "rag_ingest"}
        if rag_mode:
            system_content += (
                "\n\n⚠️【RAG知识库问答模式已开启 — 严格限制】\n"
                "回答规则：\n"
                "1. 你只能使用 rag_ask 和 rag_search 工具检索知识库，严禁调用任何其他工具（包括联网搜索、浏览器等）。\n"
                "2. 收到问题后，必须先调用 rag_ask 工具进行 Agentic 多角度检索。\n"
                "3. 查看返回的 relevance 分数和 queries_used：\n"
                "   - 若分数普遍 < 0.4，或明显缺少某些方面，继续用 rag_search 补充精确查询。\n"
                "   - 复杂问题应多次调用 rag_search 覆盖各阶段。\n"
                "4. 收集足够内容后，严格只根据检索结果回答，绝对禁止使用预训练知识补充。\n"
                "5. 若多次检索后仍无相关内容，直接回复：'知识库中没有相关内容，无法回答。'\n"
                "不得猜测、推断或扩展任何知识库以外的信息。"
            )
            # 过滤工具列表，只保留 RAG 相关工具
            active_tools = [t for t in self._tools if t["function"]["name"] in _RAG_TOOL_NAMES]
        else:
            active_tools = self._tools

        messages = [{"role": "system", "content": system_content}, *user_messages]

        def _cancelled():
            return cancel_event and cancel_event.is_set()

        # 获取当前模型和提供商
        model, provider = self._model_resolver()

        total_start = _time.time()
        total_prompt_tokens = 0
        total_completion_tokens = 0
        _RAG_TOOLS = {"rag_ask", "rag_search"}
        rag_tools_called = False
        rag_last_step_empty = False

        for step in range(cfg.MAX_TOOL_LOOPS):
            if _cancelled():
                yield self._sse_event("reply", {"content": "⏹ 已停止回答。"})
                return

            step_start = _time.time()
            yield self._sse_event("thinking", {"step": step + 1, "message": f"第 {step + 1} 步：正在思考...", "timing": True})

            try:
                llm_gen = self._llm_client.stream(model, provider, messages, active_tools, cancel_event=cancel_event)
                first = next(llm_gen, None)
            except Exception as e:
                yield self._sse_event("error", {"message": f"API 调用失败: {e}"})
                return

            if _cancelled():
                yield self._sse_event("reply", {"content": "⏹ 已停止回答。"})
                return

            if first is None:
                yield self._sse_event("reply", {"content": ""})
                return

            msg = None
            streamed_text = False

            if first[0] == "content_chunk":
                elapsed = round(_time.time() - step_start, 1)
                yield self._sse_event("thinking", {"step": step + 1, "message": f"✅ 开始生成回复 ({elapsed}s)"})
                full_content = first[1]
                yield self._sse_event("reply_chunk", {"content": first[1]})
                streamed_text = True
                for item in llm_gen:
                    if item[0] == "content_chunk":
                        full_content += item[1]
                        yield self._sse_event("reply_chunk", {"content": item[1]})
                        if _cancelled():
                            break
                    elif item[0] == "tool_calls":
                        msg = item[1]
                    elif item[0] == "usage":
                        total_prompt_tokens += item[1].get("prompt_tokens", 0)
                        total_completion_tokens += item[1].get("completion_tokens", 0)
            elif first[0] == "tool_calls":
                msg = first[1]
            elif first[0] == "usage":
                total_prompt_tokens += first[1].get("prompt_tokens", 0)
                total_completion_tokens += first[1].get("completion_tokens", 0)

            if streamed_text and msg is None:
                msg = self._try_parse_text_tool_call(full_content)
                if msg is None:
                    if rag_mode and step == 0 and not rag_tools_called:
                        yield self._sse_event("reply_done", {"full_content": full_content, "elapsed": 0, "is_prefix": True})
                        messages.append({"role": "user", "content": "⚠️ 你必须先调用 rag_ask 工具检索知识库，再根据检索结果回答，不能直接回答。"})
                        continue
                    if rag_mode and rag_last_step_empty:
                        yield self._sse_event("reply_done", {"full_content": full_content, "elapsed": 0, "is_prefix": True})
                        yield self._sse_event("reply", {"content": "知识库中没有找到相关内容，无法回答。"})
                        return
                    yield self._sse_event("reply_done", {"full_content": full_content, "elapsed": round(_time.time() - total_start, 1)})
                    return
                yield self._sse_event("reply_done", {"full_content": "", "elapsed": 0, "is_prefix": True, "clear": True})

            if streamed_text and msg is not None:
                yield self._sse_event("reply_done", {"full_content": full_content, "elapsed": round(_time.time() - total_start, 1), "is_prefix": True})

            if msg is None:
                yield self._sse_event("reply", {"content": ""})
                return

            elapsed = round(_time.time() - step_start, 1)
            yield self._sse_event("thinking", {"step": step + 1, "message": f"🤔 决定调用 {len(msg['tool_calls'])} 个工具 ({elapsed}s)"})
            messages.append(msg)

            for tc in msg["tool_calls"]:
                fn_name = tc["function"]["name"]
                fn_args = json.loads(tc["function"]["arguments"])
                fn = self._tool_map.get(fn_name)
                label = self._tool_labels.get(fn_name, fn_name)

                if fn_name in self._file_tools:
                    tool_path = self._permission_mgr.get_tool_path(fn_name, fn_args)
                    abs_path = os.path.abspath(os.path.expanduser(tool_path))
                    if not self._permission_mgr.is_allowed(abs_path):
                        req_id = str(uuid.uuid4())[:8]
                        evt = threading.Event()
                        self._permission_mgr.pending_approvals[req_id] = {"event": evt, "approved": False, "path": abs_path}
                        yield self._sse_event("permission_request", {"request_id": req_id, "tool": fn_name, "label": label, "path": abs_path, "args": fn_args})
                        evt.wait(timeout=cfg.PERMISSION_TIMEOUT)
                        approval = self._permission_mgr.pending_approvals.pop(req_id, {})
                        if not approval.get("approved"):
                            result = json.dumps({"error": f"用户拒绝了访问: {abs_path}"}, ensure_ascii=False)
                            yield self._sse_event("tool_call", {"name": fn_name, "label": label, "args": fn_args})
                            yield self._sse_event("tool_result", {"name": fn_name, "label": label, "result": json.loads(result)})
                            messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result})
                            continue

                if _cancelled():
                    yield self._sse_event("reply", {"content": "⏹ 已停止回答。"})
                    return

                yield self._sse_event("tool_call", {"name": fn_name, "label": label, "args": fn_args})

                if fn_name in ("generate_image", "generate_video"):
                    emoji = "🎨" if fn_name == "generate_image" else "🎬"
                    lbl = "图片生成中" if fn_name == "generate_image" else "视频生成中"
                    interval = 3 if fn_name == "generate_image" else 5
                    result, heartbeat_events = self._run_long_tool(fn, fn_args, step + 1, emoji, lbl, interval, cancel_event)
                    for evt_str in heartbeat_events:
                        yield evt_str
                else:
                    result = fn(**fn_args) if fn else json.dumps({"error": f"未知工具: {fn_name}"})

                result_data = json.loads(result)

                llm_result = result
                if "image_base64" in result_data:
                    llm_data = {k: v for k, v in result_data.items() if k != "image_base64"}
                    llm_data["message"] = f"截图完成（{result_data.get('title', '')}），图片已展示给用户。"
                    llm_result = json.dumps(llm_data, ensure_ascii=False)

                yield self._sse_event("tool_result", {"name": fn_name, "label": label, "result": result_data})
                messages.append({"role": "tool", "tool_call_id": tc["id"], "content": llm_result})

                if fn_name in _RAG_TOOLS:
                    rag_tools_called = True
                    is_empty = (result_data.get("count", -1) == 0)
                    if not is_empty:
                        rag_last_step_empty = False

                if _cancelled():
                    yield self._sse_event("reply", {"content": "⏹ 已停止回答。"})
                    return

            if rag_mode:
                step_rag_calls = [tc for tc in msg["tool_calls"] if tc["function"]["name"] in _RAG_TOOLS]
                if step_rag_calls:
                    step_all_empty = all(
                        json.loads(m["content"]).get("count", -1) == 0
                        for m in messages[-len(step_rag_calls):]
                        if m.get("role") == "tool"
                    )
                    if step_all_empty:
                        rag_last_step_empty = True
                        yield self._sse_event("reply", {"content": "知识库中没有找到相关内容，无法回答。"})
                        return

        yield self._sse_event("reply", {"content": f"⚠️ 达到最大循环次数（{cfg.MAX_TOOL_LOOPS}次），请尝试简化问题。"})
