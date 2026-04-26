"""
Agent 配置文件 —— API、模型等集中管理

系统提示词与定价常量已迁移至 prompts/ 包，此处直接导入供外部使用。
"""

import os
from pathlib import Path

# 加载 .env 文件（若存在）；生产环境可直接设置系统环境变量，无需 .env
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass  # python-dotenv 未安装时，直接使用系统环境变量

# ── 从 prompts 包导入系统提示词和定价常量 ────────────
from prompts import (
    SYSTEM_PROMPT,
    MODEL_PRICING,
    MEDIA_PRICING,
    USD_TO_CNY,
    calc_cost,
    calc_media_cost_usd,
)

# ── 提供商配置 ────────────────────────────────────────
# 支持多个提供商，每个提供商包含 api_url、api_key 及其下属模型列表
# deepseek：Chat 模型（支持 function calling）
# qwen：仅用于视觉（多模态）场景，视觉模型不出现在 UI 下拉列表中
PROVIDERS = {
    "deepseek": {
        "api_url": "https://api.deepseek.com/chat/completions",
        "api_key": os.environ.get("DEEPSEEK_API_KEY", ""),
        "models": {
            "deepseek-chat": "DeepSeek Chat",
        },
    },
    "qwen": {
        "api_url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions",
        "api_key": os.environ.get("DASHSCOPE_API_KEY", ""),
        "models": {},  # 视觉模型仅内部自动切换，不出现在 UI 选择列表
        "vision_model": "qwen-vl-max",
        "dashscope_key": os.environ.get("DASHSCOPE_API_KEY", ""),
    },
}


def get_provider_for_model(model: str) -> dict | None:
    """根据模型名查找其所属 provider 配置。
    遍历所有提供商，匹配模型 ID，找到则返回对应的 provider 配置字典，否则返回 None。
    """
    for provider_cfg in PROVIDERS.values():
        if model in provider_cfg["models"]:
            return provider_cfg
    return None


def get_all_models() -> list[dict]:
    """返回所有可用模型列表（含 provider 分组信息）。
    遍历所有提供商下的所有模型，组装成前端展示所需的统一格式列表。
    """
    result = []
    for provider_name, provider_cfg in PROVIDERS.items():
        for model_id, model_label in provider_cfg["models"].items():
            result.append({
                "id": model_id,
                "label": model_label,
                "provider": provider_name,
                # api_key 非空则视为可用
                "available": bool(provider_cfg["api_key"]),
            })
    return result


# ── Agent 参数 ────────────────────────────────────────
MAX_TOOL_LOOPS = 30          # 最大工具调用循环次数，防止无限递归
API_TIMEOUT = 120            # LLM API 请求超时（秒）
PERMISSION_TIMEOUT = 120     # 等待用户授权文件路径的超时（秒）

# ── 服务配置 ──────────────────────────────────────────
WEB_PORT = 5050              # Flask Web 服务监听端口

# ── 通知邮箱 ─────────────────────────────────────────
# 当 cloudflared 隧道建立成功后，将公网地址发送到此邮箱
NOTIFY_EMAIL = os.environ.get("NOTIFY_EMAIL", "")
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_HOST = "smtp.163.com"
SMTP_PORT = 465
