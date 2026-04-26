"""
模型定价与费用计算

所有价格均为官方公开定价，供费用估算使用。
"""

# ── 文本模型定价 ───────────────────────────────────────
# 单位：元 / 百万 tokens（人民币计价）
MODEL_PRICING = {
    "deepseek-chat": {"input": 1.0, "output": 2.0},
    "qwen-vl-max":   {"input": 3.0, "output": 9.0},
}


def calc_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """计算本次文本 API 调用费用（元）。
    未知模型按 0 计算，不会抛出异常。
    """
    p = MODEL_PRICING.get(model, {"input": 0, "output": 0})
    return round((prompt_tokens * p["input"] + completion_tokens * p["output"]) / 1_000_000, 6)


# ── 图片 / 视频定价 ───────────────────────────────────
# 阿里云 DashScope 国际版（新加坡）定价，美元计价
# wan2.6-t2i：文生图，按张收费
# wan2.6-t2v：文生视频，按秒收费（720P）
USD_TO_CNY = 7.2  # 汇率参考，用于展示人民币估算价格

MEDIA_PRICING = {
    "wan2.6-t2i": {"per_image_usd": 0.03},    # $0.03/张
    "wan2.6-t2v": {"per_second_usd": 0.10},   # $0.10/秒（720P）
}


def calc_media_cost_usd(model: str, count: float) -> float:
    """计算图片/视频费用（美元）。
    count 对图片是张数，对视频是秒数。
    未知模型返回 0.0。
    """
    p = MEDIA_PRICING.get(model, {})
    if "per_image_usd" in p:
        return round(p["per_image_usd"] * count, 4)
    if "per_second_usd" in p:
        return round(p["per_second_usd"] * count, 4)
    return 0.0
