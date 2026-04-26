"""
MCP Server: Image & Video Gen — 通义万象 API（阿里云 DashScope 新加坡）
文生图：wan2.6-t2i（multimodal-generation，同步接口）
文生视频/图生视频：wan2.6-t2v（video-generation，异步接口 + 轮询）
"""

import json
import time
import requests
import config as cfg

# DashScope 国际版 API 基础地址
_DASHSCOPE_BASE  = "https://dashscope-intl.aliyuncs.com/api/v1"
# 文生图端点（multimodal-generation，同步返回）
_IMAGE_ENDPOINT  = f"{_DASHSCOPE_BASE}/services/aigc/multimodal-generation/generation"
# 文生视频端点（video-generation，需异步轮询）
_VIDEO_ENDPOINT  = f"{_DASHSCOPE_BASE}/services/aigc/video-generation/video-synthesis"
# 使用的模型 ID
_IMAGE_MODEL     = "wan2.6-t2i"
_VIDEO_MODEL     = "wan2.6-t2v"

# 异步任务轮询参数
_POLL_INTERVAL = 5     # 每次轮询间隔（秒）
_POLL_MAX      = 72    # 最多轮询次数，72 * 5s = 6 分钟超时


def _headers() -> dict:
    """构建请求头，从配置中读取 DashScope API Key"""
    key = cfg.PROVIDERS.get("qwen", {}).get("dashscope_key", "")
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def _poll_task(task_id: str) -> dict:
    """轮询 DashScope 异步任务直到完成或超时。
    成功时返回 output 字典，失败或超时时返回含 'error' 键的字典。
    """
    url = f"{_DASHSCOPE_BASE}/tasks/{task_id}"
    for _ in range(_POLL_MAX):
        time.sleep(_POLL_INTERVAL)
        try:
            resp = requests.get(url, headers=_headers(), timeout=30)
            resp.encoding = "utf-8"
            data = resp.json()
        except Exception:
            # 网络抖动时跳过本次，继续轮询
            continue
        status = data.get("output", {}).get("task_status", "")
        if status == "SUCCEEDED":
            return data.get("output", {})
        if status == "FAILED":
            return {"error": data.get("output", {}).get("message", "任务失败")}
    return {"error": f"任务超时（task_id: {task_id}）"}


# ── 工具定义（LLM function calling 格式） ─────────────
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "generate_image",
            "description": "根据文字描述生成图像（通义万象 AI 绘画）。当用户要求生成图片、画图、创作图像时使用此工具。",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "图像描述，尽量详细（风格、主体、背景、色调等）"
                    },
                    "negative_prompt": {
                        "type": "string",
                        "description": "不希望出现的元素，如 '低画质, 模糊, 畸形'"
                    },
                    "size": {
                        "type": "string",
                        "description": "图像尺寸，默认 1024*1024。可选：1024*1024、1280*720、720*1280、1024*576、576*1024",
                        "enum": ["1024*1024", "1280*720", "720*1280", "1024*576", "576*1024"]
                    },
                },
                "required": ["prompt"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_video",
            "description": "根据文字描述生成视频（通义万象 AI 视频）。当用户要求生成视频、做动画时使用此工具。生成需要 1-5 分钟。",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "视频描述，尽量详细（场景、动作、镜头、光线、风格等）"
                    },
                    "image_url": {
                        "type": "string",
                        "description": "可选，提供图片 URL 则以该图为首帧生成视频（图生视频）"
                    },
                },
                "required": ["prompt"],
            },
        },
    },
]


# ── 文生图（同步接口，multimodal-generation） ──────────
def generate_image(prompt: str, negative_prompt: str = "", size: str = "1280*1280") -> str:
    """调用通义万象文生图 API，返回 JSON 字符串。
    优先使用同步接口直接获取图片 URL；
    若接口返回 task_id，则回退到异步轮询模式。
    返回字段包含 image_urls、cost_usd、cost_cny 等。
    """
    key = cfg.PROVIDERS.get("qwen", {}).get("dashscope_key", "")
    if not key:
        return json.dumps({"error": "DashScope API Key 未配置"}, ensure_ascii=False)

    # 构建请求体：单条用户消息，参数含尺寸、数量、水印等
    body = {
        "model": _IMAGE_MODEL,
        "input": {
            "messages": [{"role": "user", "content": [{"text": prompt}]}]
        },
        "parameters": {
            "size": size,
            "n": 1,
            "prompt_extend": True,   # 允许模型自动扩展提示词
            "watermark": False,
            "negative_prompt": negative_prompt,
        },
    }
    try:
        resp = requests.post(_IMAGE_ENDPOINT, headers=_headers(), json=body, timeout=60)
        resp.encoding = "utf-8"
        data = resp.json()
    except Exception as e:
        return json.dumps({"error": f"图片生成请求异常: {e}"}, ensure_ascii=False)

    # 同步接口直接返回结果，检查错误码
    output = data.get("output", {})
    if data.get("code") or output.get("task_status") == "FAILED":
        return json.dumps({"error": data.get("message", str(data))}, ensure_ascii=False)

    # 从 choices -> message -> content 中提取图片 URL
    choices = output.get("choices", [])
    image_urls = []
    for choice in choices:
        for item in choice.get("message", {}).get("content", []):
            if item.get("image"):
                image_urls.append(item["image"])

    if not image_urls:
        # 部分版本返回 task_id，需要走异步轮询
        task_id = output.get("task_id", "")
        if task_id:
            output = _poll_task(task_id)
            if "error" in output:
                return json.dumps({"error": output["error"]}, ensure_ascii=False)
            results = output.get("results", [])
            image_urls = [r.get("url") for r in results if r.get("url")]

    if not image_urls:
        return json.dumps({"error": "未返回图片 URL", "raw": str(data)[:300]}, ensure_ascii=False)

    # 计算费用并返回结果
    cost_usd = cfg.calc_media_cost_usd("wan2.6-t2i", len(image_urls))
    return json.dumps({
        "success": True,
        "prompt": prompt,
        "image_urls": image_urls,
        "message": f"已生成 {len(image_urls)} 张图片",
        "cost_usd": cost_usd,
        "cost_cny": round(cost_usd * cfg.USD_TO_CNY, 3),
    }, ensure_ascii=False)


# ── 文生视频 / 图生视频（异步接口） ───────────────────
def generate_video(prompt: str, image_url: str = "") -> str:
    """调用通义万象视频生成 API（异步），返回 JSON 字符串。
    提交任务后通过 _poll_task 轮询结果，最长等待约 6 分钟。
    支持文生视频（仅 prompt）和图生视频（prompt + image_url 首帧）。
    返回字段包含 video_urls、cost_usd、cost_cny 等。
    """
    key = cfg.PROVIDERS.get("qwen", {}).get("dashscope_key", "")
    if not key:
        return json.dumps({"error": "DashScope API Key 未配置"}, ensure_ascii=False)

    url = _VIDEO_ENDPOINT
    # 构建输入：若提供图片 URL 则启用图生视频模式
    inp = {"prompt": prompt}
    if image_url:
        inp["image_url"] = image_url

    body = {
        "model": _VIDEO_MODEL,
        "input": inp,
        # 固定参数：720P 分辨率，5 秒时长，允许提示词扩展
        "parameters": {"size": "1280*720", "duration": 5, "prompt_extend": True},
    }
    # 异步模式需加 X-DashScope-Async 请求头
    headers = {**_headers(), "X-DashScope-Async": "enable"}
    try:
        resp = requests.post(url, headers=headers, json=body, timeout=30)
        resp.encoding = "utf-8"
        data = resp.json()
    except Exception as e:
        return json.dumps({"error": f"视频生成请求异常: {e}"}, ensure_ascii=False)

    # 获取异步任务 ID
    task_id = data.get("output", {}).get("task_id", "")
    if not task_id:
        return json.dumps({"error": f"提交失败: {data.get('message', str(data))}"}, ensure_ascii=False)

    # 轮询等待任务完成
    output = _poll_task(task_id)
    if "error" in output:
        return json.dumps({"error": output["error"]}, ensure_ascii=False)

    video_url = output.get("video_url", "")
    if not video_url:
        return json.dumps({"error": "任务完成但未返回视频 URL", "raw": str(output)[:300]}, ensure_ascii=False)

    # 计算费用并返回结果
    duration = body.get("parameters", {}).get("duration", 5)
    cost_usd = cfg.calc_media_cost_usd("wan2.6-t2v", duration)
    return json.dumps({
        "success": True,
        "prompt": prompt,
        "video_urls": [video_url],
        "message": f"已生成 1 个视频（{duration}秒）",
        "cost_usd": cost_usd,
        "cost_cny": round(cost_usd * cfg.USD_TO_CNY, 3),
    }, ensure_ascii=False)


# ── 工具注册表（由 mcp_servers/__init__.py 加载） ──────
TOOL_MAP = {
    "generate_image": generate_image,
    "generate_video": generate_video,
}

# 工具显示标签（用于 SSE 事件中的 UI 展示）
TOOL_LABELS = {
    "generate_image": "🎨 AI 绘画",
    "generate_video": "🎬 AI 视频",
}

# 无需文件系统权限确认的工具集（空集合）
PERMISSION_TOOLS = set()
