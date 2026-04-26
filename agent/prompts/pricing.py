"""
模型定价与费用计算

所有价格均为官方公开定价，供费用估算使用。
"""

# ── 文本模型定价 ───────────────────────────────────────
# 单位：元 / 百万 tokens（人民币计价）
# 注：价格请以 DeepSeek 官网为准，下方为占位值
MODEL_PRICING = {
    "deepseek-v4-pro":   {"input": 1.0, "output": 2.0},
    "deepseek-v4-flash": {"input": 0.5, "output": 1.0},
}


def calc_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """计算本次文本 API 调用费用（元）。
    未知模型按 0 计算，不会抛出异常。
    """
    p = MODEL_PRICING.get(model, {"input": 0, "output": 0})
    return round((prompt_tokens * p["input"] + completion_tokens * p["output"]) / 1_000_000, 6)
