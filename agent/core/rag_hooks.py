"""RAG 专用 Hook —— 管理 RAG 工具的状态追踪与结果校验。

从 agent_runner 主循环中迁出 RAG 特定的横切逻辑。
"""

import json


class RagState:
    """RAG 工具调用状态追踪（在 agent 单次对话生命周期内）。"""

    def __init__(self):
        self.tools_called = False     # 本轮是否调用过任何 RAG 工具
        self.last_step_empty = False  # 上一步的所有 RAG 调用是否都返回空

    def reset(self):
        self.tools_called = False
        self.last_step_empty = False


def create_rag_result_hook(state: RagState):
    """创建 post-hook：追踪 RAG 工具调用状态并处理空结果。

    用法:
        state = RagState()
        pipeline.add_post("rag_*", create_rag_result_hook(state))
    """
    _FOUND_INSTRUCTION = (
        "📎 以上为检索结果。请基于这些内容回答，每个事实声明标注来源文件名 `[来源: xxx]`，"
        "不要编造任何检索结果中没有的信息。"
    )

    def _hook(tool_name, tool_args, result_str):
        try:
            data = json.loads(result_str)
        except (json.JSONDecodeError, TypeError):
            return None

        count = data.get("count", -1)
        is_empty = (count == 0)
        if not is_empty:
            state.last_step_empty = False
            # 注入来源标注指令
            if "instruction" not in data:
                data["instruction"] = _FOUND_INSTRUCTION
        state.tools_called = True

        # 给结果打标，方便 agent_runner 在循环中用
        data["_rag_empty"] = is_empty
        return json.dumps(data, ensure_ascii=False)

    return _hook
