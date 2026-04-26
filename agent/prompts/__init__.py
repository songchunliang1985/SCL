"""
prompts 包 —— 系统提示词与定价常量的统一入口

导入示例：
  from prompts import SYSTEM_PROMPT
  from prompts import calc_cost
"""

from .system_prompt import SYSTEM_PROMPT
from .pricing import MODEL_PRICING, calc_cost

__all__ = [
    "SYSTEM_PROMPT",
    "MODEL_PRICING",
    "calc_cost",
]
