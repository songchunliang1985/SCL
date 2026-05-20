"""
WerewolfAI 一键启动器（Python 套壳）

流程：
  1. 杀掉占用 config.port 的旧 node 进程（Windows）
  2. 启动 node server/llm-proxy.js（stdout/stderr 写到 launcher.log）
  3. 轮询 /config 等代理就绪
  4. pywebview 弹独立窗口加载 web/index.html
  5. 窗口关闭时清理子进程

依赖：pip install pywebview
运行：python launcher.py   或   双击 launcher.pyw
"""

import atexit
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

import webview  # pip install pywebview

LAUNCHER_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(LAUNCHER_DIR)
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config.json")
PROXY_SCRIPT = os.path.join("server", "llm-proxy.js")
INDEX_PATH = os.path.join(PROJECT_ROOT, "web", "index.html")
LAUNCHER_LOG = os.path.join(PROJECT_ROOT, "launcher.log")


def read_port() -> int:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return int(json.load(f).get("port") or 3001)
    except Exception:
        return 3001


def kill_port_listener(port: int) -> int:
    """Windows: 杀掉占用指定端口的 LISTENING 进程，返回杀掉的数量"""
    if os.name != "nt":
        return 0
    killed = 0
    try:
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True, text=True, check=False,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        for line in result.stdout.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                pid = line.split()[-1]
                if pid.isdigit():
                    subprocess.run(
                        ["taskkill", "/F", "/PID", pid],
                        capture_output=True, check=False,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    )
                    killed += 1
    except Exception as e:
        print(f"[launcher] kill_port_listener failed: {e}", file=sys.stderr)
    return killed


def start_proxy() -> subprocess.Popen:
    """启动 node server/llm-proxy.js；stdout/stderr 重定向到 launcher.log 便于排错"""
    creation = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    log_fh = open(LAUNCHER_LOG, "a", encoding="utf-8")
    log_fh.write(f"\n=== [{time.strftime('%Y-%m-%d %H:%M:%S')}] launcher start ===\n")
    log_fh.flush()
    return subprocess.Popen(
        ["node", PROXY_SCRIPT],
        cwd=PROJECT_ROOT,
        creationflags=creation,
        stdout=log_fh,
        stderr=log_fh,
    )


def wait_ready(port: int, timeout_sec: int = 10) -> bool:
    url = f"http://127.0.0.1:{port}/config"
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=0.5) as r:
                if r.status == 200:
                    return True
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            pass
        time.sleep(0.3)
    return False


def main() -> int:
    if not os.path.exists(CONFIG_PATH):
        print(f"[launcher] config.json not found at {CONFIG_PATH}", file=sys.stderr)
        return 1
    if not os.path.exists(INDEX_PATH):
        print(f"[launcher] web/index.html not found at {INDEX_PATH}", file=sys.stderr)
        return 1
    if not os.path.exists(os.path.join(PROJECT_ROOT, PROXY_SCRIPT)):
        print(f"[launcher] {PROXY_SCRIPT} not found in {PROJECT_ROOT}", file=sys.stderr)
        return 1

    port = read_port()

    killed = kill_port_listener(port)
    if killed > 0:
        print(f"[launcher] killed {killed} stale process(es) on port {port}")
        time.sleep(0.5)

    proxy = start_proxy()
    atexit.register(lambda: proxy.terminate())

    if not wait_ready(port):
        proxy.terminate()
        print(f"[launcher] llm-proxy did not become ready within 10s. See {LAUNCHER_LOG}", file=sys.stderr)
        return 1

    print(f"[launcher] llm-proxy ready at http://127.0.0.1:{port}")
    webview.create_window(
        "WerewolfAI · 12 人神局",
        f"file:///{INDEX_PATH.replace(os.sep, '/')}?port={port}",
        width=1400,
        height=900,
    )
    webview.start()

    proxy.terminate()
    return 0


if __name__ == "__main__":
    sys.exit(main())
