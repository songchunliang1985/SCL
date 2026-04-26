"""
MCP Server: Playwright — 浏览器自动化（导航、截图、点击、输入）
所有 Playwright 操作在专用线程中执行，每次操作自动截图
"""

import json
import os
import base64
import threading
import time
from queue import Queue
from playwright.sync_api import sync_playwright

# 读取本模块配置
_dir = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(_dir, "config.json"), "r") as f:
    _cfg = json.load(f)

HEADLESS = _cfg.get("headless", False)
CHANNEL = _cfg.get("channel", "msedge")
VIEWPORT_WIDTH = _cfg.get("viewport_width", 1280)
VIEWPORT_HEIGHT = _cfg.get("viewport_height", 720)
TIMEOUT = _cfg.get("timeout", 30)
ACTION_TIMEOUT = _cfg.get("action_timeout", 10)
CONTENT_MAX_LENGTH = _cfg.get("content_max_length", 5000)

# ── 专用线程通信 ──────────────────────────────────────
_cmd_queue = Queue()
_worker_thread = None


def _take_screenshot(page):
    try:
        time.sleep(0.5)
        buf = page.screenshot(type="png")
        return base64.b64encode(buf).decode("utf-8")
    except Exception:
        return None


def _worker_loop():
    _pw = sync_playwright().start()
    launch_opts = {"headless": HEADLESS}
    if CHANNEL:
        launch_opts["channel"] = CHANNEL
    _browser = _pw.chromium.launch(**launch_opts)
    _page = _browser.new_page(viewport={"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT})

    while True:
        cmd, args, result_q = _cmd_queue.get()
        if cmd == "__STOP__":
            try:
                _page.close()
                _browser.close()
                _pw.stop()
            except Exception:
                pass
            result_q.put(json.dumps({"message": "浏览器已关闭"}, ensure_ascii=False))
            break
        try:
            result = cmd(_page, *args)
            result_q.put(result)
        except Exception as e:
            result_q.put(json.dumps({"error": str(e)}, ensure_ascii=False))


def _ensure_worker():
    global _worker_thread
    if _worker_thread is None or not _worker_thread.is_alive():
        _worker_thread = threading.Thread(target=_worker_loop, daemon=True)
        _worker_thread.start()


def _run_on_worker(cmd, *args):
    _ensure_worker()
    result_q = Queue()
    _cmd_queue.put((cmd, args, result_q))
    return result_q.get(timeout=TIMEOUT + 10)


# ── 专用线程内执行的函数 ─────────────────────────────

def _do_navigate(page, url):
    page.goto(url, timeout=TIMEOUT * 1000)
    page.wait_for_load_state("networkidle", timeout=10000)
    screenshot = _take_screenshot(page)
    result = {"url": page.url, "title": page.title(), "message": f"已打开: {page.title()}"}
    if screenshot:
        result["image_base64"] = screenshot
    return json.dumps(result, ensure_ascii=False)


def _do_screenshot(page):
    buf = page.screenshot(type="png")
    b64 = base64.b64encode(buf).decode("utf-8")
    return json.dumps({
        "url": page.url, "title": page.title(),
        "image_base64": b64, "message": "截图完成",
    }, ensure_ascii=False)


def _do_click(page, selector):
    page.click(selector, timeout=ACTION_TIMEOUT * 1000)
    page.wait_for_load_state("domcontentloaded", timeout=5000)
    screenshot = _take_screenshot(page)
    result = {"url": page.url, "title": page.title(), "message": f"已点击: {selector}"}
    if screenshot:
        result["image_base64"] = screenshot
    return json.dumps(result, ensure_ascii=False)


def _do_type(page, selector, text):
    page.fill(selector, text, timeout=ACTION_TIMEOUT * 1000)
    screenshot = _take_screenshot(page)
    result = {"url": page.url, "title": page.title(), "message": f"已输入 '{text}' 到: {selector}"}
    if screenshot:
        result["image_base64"] = screenshot
    return json.dumps(result, ensure_ascii=False)


def _do_get_content(page):
    text = page.inner_text("body")[:CONTENT_MAX_LENGTH]
    return json.dumps({"url": page.url, "title": page.title(), "content": text}, ensure_ascii=False)


# ── 对外暴露的工具函数 ──────────────────────────────

def browser_navigate(url: str) -> str:
    try:
        return _run_on_worker(_do_navigate, url)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def browser_screenshot() -> str:
    try:
        return _run_on_worker(_do_screenshot)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def browser_click(selector: str) -> str:
    try:
        return _run_on_worker(_do_click, selector)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def browser_type(selector: str, text: str) -> str:
    try:
        return _run_on_worker(_do_type, selector, text)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def browser_get_content() -> str:
    try:
        return _run_on_worker(_do_get_content)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def browser_close() -> str:
    global _worker_thread
    try:
        _ensure_worker()
        result_q = Queue()
        _cmd_queue.put(("__STOP__", (), result_q))
        result = result_q.get(timeout=10)
        _worker_thread = None
        return result
    except Exception as e:
        _worker_thread = None
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ── MCP 导出 ─────────────────────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "browser_navigate",
            "description": "在浏览器中打开指定 URL，自动截图返回。用于可视化浏览网页。",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string", "description": "要访问的完整 URL"}},
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_screenshot",
            "description": "截取当前浏览器页面的截图。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_click",
            "description": "点击页面元素（CSS 选择器），自动截图返回操作后状态。",
            "parameters": {
                "type": "object",
                "properties": {"selector": {"type": "string", "description": "CSS 选择器"}},
                "required": ["selector"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_type",
            "description": "在页面输入框中输入文字，自动截图返回。",
            "parameters": {
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS 选择器"},
                    "text": {"type": "string", "description": "要输入的文字"},
                },
                "required": ["selector", "text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_get_content",
            "description": "获取当前页面的文本内容。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_close",
            "description": "关闭浏览器，释放资源。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]

TOOL_MAP = {
    "browser_navigate": browser_navigate,
    "browser_screenshot": browser_screenshot,
    "browser_click": browser_click,
    "browser_type": browser_type,
    "browser_get_content": browser_get_content,
    "browser_close": browser_close,
}

TOOL_LABELS = {
    "browser_navigate": "🌐 浏览器导航",
    "browser_screenshot": "📸 浏览器截图",
    "browser_click": "👆 浏览器点击",
    "browser_type": "⌨️ 浏览器输入",
    "browser_get_content": "📝 获取页面内容",
    "browser_close": "🚪 关闭浏览器",
}
