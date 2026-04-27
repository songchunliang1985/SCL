"""Agent 主循环 —— 多轮 LLM + 工具执行"""
import json
import os
import uuid
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import config as cfg
from mcp_servers import load_skills_index, get_skill_content
from core.hooks import HookPipeline
from core.rag_hooks import RagState, create_rag_result_hook
from core.context_trim import trim_messages


class AgentRunner:
    """封装 Agent 的完整执行流程。"""

    def __init__(self, tools: list, tool_map: dict, tool_labels: dict,
                 file_tools: set, permission_mgr, llm_client, model_resolver):
        self._tools = tools
        self._tool_map = tool_map
        self._tool_labels = tool_labels
        self._file_tools = file_tools
        self._permission_mgr = permission_mgr
        self._llm_client = llm_client
        self._model_resolver = model_resolver

        self._tools.append({
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
        })
        self._tool_map["use_skill"] = lambda skill_name: self._handle_use_skill(skill_name)
        self._tool_labels["use_skill"] = "📋 加载技能"

        # 全局 hook 管道（不含 RAG hook，RAG hook 在每次请求时独立创建，见 run_stream）
        self._hook_pipeline = HookPipeline()

    @staticmethod
    def _sse_event(event: str, data: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    def _handle_use_skill(self, skill_name: str) -> str:
        content = get_skill_content(skill_name)
        if content is None:
            available = [s["key"] for s in load_skills_index()]
            return json.dumps({"error": f"技能 '{skill_name}' 不存在", "available_skills": available}, ensure_ascii=False)
        return json.dumps({"skill": skill_name, "instructions": content}, ensure_ascii=False)

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

        _RAG_TOOL_NAMES = {"rag_ask", "rag_search", "rag_list", "rag_delete", "rag_ingest"}
        if rag_mode:
            system_content += (
                "\n\n⚠️【RAG知识库问答模式已开启 — 严格限制】\n"
                "回答规则：\n"
                "1. 你只能使用 rag_ask 和 rag_search 工具检索知识库，严禁调用任何其他工具。\n"
                "2. 收到问题后，必须先调用 rag_ask 工具进行 Agentic 多角度检索。\n"
                "3. 查看返回的 relevance 分数和 trace/queries_used：\n"
                "   - 若分数普遍 < 0.4，或明显缺少某些方面，继续用 rag_search 补充精确查询。\n"
                "   - 复杂问题应多次调用 rag_search 覆盖各阶段。\n"
                "4. 收集足够内容后，严格只根据检索结果回答，绝对禁止使用预训练知识补充。\n"
                "5. 若多次检索后仍无相关内容，直接回复：'知识库中没有相关内容，无法回答。'\n"
                "6. 【忠实度要求】回答中的每个事实声明必须能在检索结果中找到对应 chunk，并在引用时标注来源文件名，格式：`[来源: xxx.pdf]`。\n"
                "不得猜测、推断或扩展任何知识库以外的信息。"
            )
            active_tools = [t for t in self._tools if t["function"]["name"] in _RAG_TOOL_NAMES]
        else:
            active_tools = self._tools

        messages = [{"role": "system", "content": system_content}, *user_messages]

        def _cancelled():
            return cancel_event and cancel_event.is_set()

        model, provider = self._model_resolver()
        total_start = _time.time()
        total_prompt_tokens = 0
        total_completion_tokens = 0

        # 每次请求独立的 RAG 状态（并发安全：不共享 self 上的状态）
        rag_state = RagState()
        request_hooks = self._hook_pipeline.copy()
        request_hooks.add_post("rag_*", create_rag_result_hook(rag_state))

        _RETRY_CODES = ("502", "503", "429")

        for step in range(cfg.MAX_TOOL_LOOPS):
            if _cancelled():
                yield self._sse_event("reply", {"content": "⏹ 已停止回答。"})
                return

            # 每步前裁剪消息，防止长对话/大工具结果撞上 context window
            messages = trim_messages(messages)

            step_start = _time.time()
            yield self._sse_event("thinking", {"step": step + 1, "message": f"第 {step + 1} 步：正在思考...", "timing": True})

            # LLM 调用 + 指数退避重试（502/503/429）
            first = None
            for attempt in range(3):
                try:
                    llm_gen = self._llm_client.stream(model, provider, messages, active_tools, cancel_event=cancel_event)
                    first = next(llm_gen, None)
                    break
                except Exception as e:
                    if any(c in str(e) for c in _RETRY_CODES) and attempt < 2:
                        wait = 2 ** attempt
                        yield self._sse_event("thinking", {"step": step + 1, "message": f"⚠️ API 暂时不可用，{wait}s 后重试..."})
                        _time.sleep(wait)
                    else:
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
            full_content = ""

            if first[0] == "content_chunk":
                elapsed = round(_time.time() - step_start, 1)
                yield self._sse_event("thinking", {"step": step + 1, "message": f"✅ 开始生成回复 ({elapsed}s)"})
                full_content = first[1]
                # RAG 模式先 buffer 不推，避免"答完又答"的视觉残影
                if not rag_mode:
                    yield self._sse_event("reply_chunk", {"content": first[1]})
                streamed_text = True
                for item in llm_gen:
                    if item[0] == "content_chunk":
                        full_content += item[1]
                        if not rag_mode:
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

            # 文本已流出但没有工具调用 → 最终答案
            if streamed_text and msg is None:
                if rag_mode and not rag_state.tools_called:
                    messages.append({"role": "user", "content": "⚠️ 你必须先调用 rag_ask 工具检索知识库，再根据检索结果回答，不能直接回答。"})
                    continue
                if rag_mode and rag_state.last_step_empty:
                    yield self._sse_event("reply", {"content": "知识库中没有找到相关内容，无法回答。"})
                    return
                if rag_mode:
                    yield self._sse_event("reply", {"content": full_content})
                else:
                    yield self._sse_event("reply_done", {"full_content": full_content, "elapsed": round(_time.time() - total_start, 1)})
                return

            # 文本已流出 + 同时发出了工具调用 → 文本是前缀，通知前端删除
            if streamed_text and msg is not None and not rag_mode:
                yield self._sse_event("reply_done", {"full_content": full_content, "elapsed": round(_time.time() - total_start, 1), "is_prefix": True})

            if msg is None:
                yield self._sse_event("reply", {"content": ""})
                return

            elapsed = round(_time.time() - step_start, 1)
            yield self._sse_event("thinking", {"step": step + 1, "message": f"🤔 决定调用 {len(msg['tool_calls'])} 个工具 ({elapsed}s)"})
            messages.append(msg)

            # ── 工具执行 ──────────────────────────────────────────
            # 先统一通报所有工具调用，再执行
            for tc in msg["tool_calls"]:
                yield self._sse_event("tool_call", {
                    "name":  tc["function"]["name"],
                    "label": self._tool_labels.get(tc["function"]["name"], tc["function"]["name"]),
                    "args":  json.loads(tc["function"]["arguments"]),
                })

            # 文件工具：串行执行（需要权限弹窗交互，无法并行）
            # 其他工具：并行执行，加速多工具调用场景
            file_tcs  = [tc for tc in msg["tool_calls"] if tc["function"]["name"] in self._file_tools]
            other_tcs = [tc for tc in msg["tool_calls"] if tc["function"]["name"] not in self._file_tools]

            collected: dict[str, str] = {}  # tc_id -> result_json_str

            for tc in file_tcs:
                fn_name = tc["function"]["name"]
                fn_args = json.loads(tc["function"]["arguments"])
                fn      = self._tool_map.get(fn_name)
                label   = self._tool_labels.get(fn_name, fn_name)

                tool_path = self._permission_mgr.get_tool_path(fn_name, fn_args)
                abs_path  = os.path.abspath(os.path.expanduser(tool_path))
                if not self._permission_mgr.is_allowed(abs_path):
                    req_id = str(uuid.uuid4())[:8]
                    evt    = threading.Event()
                    self._permission_mgr.pending_approvals[req_id] = {"event": evt, "approved": False, "path": abs_path}
                    yield self._sse_event("permission_request", {
                        "request_id": req_id, "tool": fn_name, "label": label,
                        "path": abs_path, "args": fn_args,
                    })
                    evt.wait(timeout=cfg.PERMISSION_TIMEOUT)
                    approval = self._permission_mgr.pending_approvals.pop(req_id, {})
                    if not approval.get("approved"):
                        collected[tc["id"]] = json.dumps({"error": f"用户拒绝了访问: {abs_path}"}, ensure_ascii=False)
                        continue

                if _cancelled():
                    yield self._sse_event("reply", {"content": "⏹ 已停止回答。"})
                    return

                wrapped = request_hooks.wrap(fn_name, fn)
                collected[tc["id"]] = wrapped(**fn_args) if fn else json.dumps({"error": f"未知工具: {fn_name}"}, ensure_ascii=False)

            if other_tcs:
                def _exec(tc, _hooks=request_hooks, _tool_map=self._tool_map):
                    _fn_name = tc["function"]["name"]
                    _fn_args = json.loads(tc["function"]["arguments"])
                    _fn      = _tool_map.get(_fn_name)
                    if _fn is None:
                        return tc["id"], json.dumps({"error": f"未知工具: {_fn_name}"}, ensure_ascii=False)
                    try:
                        _wrapped = _hooks.wrap(_fn_name, _fn)
                        return tc["id"], _wrapped(**_fn_args)
                    except Exception as exc:
                        return tc["id"], json.dumps({"error": str(exc)}, ensure_ascii=False)

                with ThreadPoolExecutor(max_workers=min(len(other_tcs), 4)) as pool:
                    for tc_id, result_str in pool.map(_exec, other_tcs):
                        collected[tc_id] = result_str

            if _cancelled():
                yield self._sse_event("reply", {"content": "⏹ 已停止回答。"})
                return

            # 按原始顺序处理并上报结果
            step_rag_empty_flags = []
            for tc in msg["tool_calls"]:
                result_str = collected.get(tc["id"])
                if result_str is None:
                    continue

                fn_name     = tc["function"]["name"]
                label       = self._tool_labels.get(fn_name, fn_name)
                result_data = json.loads(result_str)

                is_rag_empty = result_data.pop("_rag_empty", None)
                if is_rag_empty is not None:
                    step_rag_empty_flags.append(is_rag_empty)

                llm_result = json.dumps(result_data, ensure_ascii=False)
                if "image_base64" in result_data:
                    llm_data = {k: v for k, v in result_data.items() if k != "image_base64"}
                    llm_data["message"] = f"截图完成（{result_data.get('title', '')}），图片已展示给用户。"
                    llm_result = json.dumps(llm_data, ensure_ascii=False)

                yield self._sse_event("tool_result", {"name": fn_name, "label": label, "result": result_data})
                messages.append({"role": "tool", "tool_call_id": tc["id"], "content": llm_result})

            if rag_mode and step_rag_empty_flags and all(step_rag_empty_flags):
                rag_state.last_step_empty = True
                yield self._sse_event("reply", {"content": "知识库中没有找到相关内容，无法回答。"})
                return

        yield self._sse_event("reply", {"content": f"⚠️ 达到最大循环次数（{cfg.MAX_TOOL_LOOPS}次），请尝试简化问题。"})
