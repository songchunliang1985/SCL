"""
prompts 包 —— 系统提示词与定价常量的统一入口

导入示例：
  from prompts import SYSTEM_PROMPT
  from prompts import calc_cost, calc_media_cost_usd, USD_TO_CNY
"""

from .system_prompt import SYSTEM_PROMPT
from .pricing import (
    MODEL_PRICING,
    MEDIA_PRICING,
    USD_TO_CNY,
    calc_cost,
    calc_media_cost_usd,
)

__all__ = [
    "SYSTEM_PROMPT",
    "MODEL_PRICING",
    "MEDIA_PRICING",
    "USD_TO_CNY",
    "calc_cost",
    "calc_media_cost_usd",
]
