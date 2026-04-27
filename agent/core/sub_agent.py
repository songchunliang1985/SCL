"""轻量子 Agent：同步执行，不发 SSE，供主 Agent 并发调用。"""
import json


class SubAgentRunner:
    """专用子 Agent，每次 run() 调用在独立 LLM 上下文中完成单个子任务。"""

    MAX_STEPS = 8

    SPECIALISTS = {
        "rag": (
            {"rag_ask", "rag_search"},
            "知识库检索",
        ),
        "web": (
            {"web_search", "fetch_webpage"},
            "联网搜索",
        ),
        "file": (
            {"list_directory", "read_file", "search_files"},
            "文件读取",
        ),
        "browser": (
            {"browser_navigate", "browser_get_content", "browser_screenshot"},
            "浏览器操作",
        ),
    }

    def __init__(self, all_tools: list, tool_map: dict, llm_client, model_resolver):
        self._all_tools = all_tools
        self._tool_map = tool_map
        self._llm_client = llm_client
        self._model_resolver = model_resolver

    def run(self, task: str, specialist: str) -> str:
        """运行子 Agent，返回 JSON 字符串 {"result": "..."} 或 {"error": "..."}。"""
        spec = self.SPECIALISTS.get(specialist)
        if not spec:
            return json.dumps({
                "error": f"未知专家类型: {specialist}，可选: {list(self.SPECIALISTS.keys())}"
            }, ensure_ascii=False)

        tool_names, spec_desc = spec
        tools = [t for t in self._all_tools if t["function"]["name"] in tool_names]
        if not tools:
            return json.dumps({
                "error": f"专家 {specialist} 无可用工具，请检查 mcp_config.json 中对应模块是否启用"
            }, ensure_ascii=False)

        messages = [
            {
                "role": "system",
                "content": (
                    f"你是专注于{spec_desc}的子 Agent。只使用提供的工具完成任务，"
                    f"完成后直接输出最终结果，不要多余说明。"
                ),
            },
            {"role": "user", "content": task},
        ]

        model, provider = self._model_resolver()

        for _ in range(self.MAX_STEPS):
            try:
                llm_gen = self._llm_client.stream(model, provider, messages, tools)
                first = next(llm_gen, None)
            except Exception as e:
                return json.dumps({"error": f"子 Agent API 错误: {e}"}, ensure_ascii=False)

            if first is None:
                return json.dumps({"error": "子 Agent 无响应"}, ensure_ascii=False)

            msg = None
            content = ""

            if first[0] == "content_chunk":
                content = first[1]
                for item in llm_gen:
                    if item[0] == "content_chunk":
                        content += item[1]
                    elif item[0] == "tool_calls":
                        msg = item[1]
            elif first[0] == "tool_calls":
                msg = first[1]

            if msg is None:
                return json.dumps({"result": content, "specialist": specialist}, ensure_ascii=False)

            messages.append(msg)
            for tc in msg["tool_calls"]:
                fn_name = tc["function"]["name"]
                fn_args = json.loads(tc["function"]["arguments"])
                fn = self._tool_map.get(fn_name)
                if fn:
                    try:
                        result = fn(**fn_args)
                    except Exception as e:
                        result = json.dumps({"error": str(e)}, ensure_ascii=False)
                else:
                    result = json.dumps({"error": f"未知工具: {fn_name}"}, ensure_ascii=False)
                messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result})

        return json.dumps({"error": f"子 Agent 达到最大步数 ({self.MAX_STEPS})"}, ensure_ascii=False)
