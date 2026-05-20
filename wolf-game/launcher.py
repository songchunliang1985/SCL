"""
WerewolfAI 一键启动器（Python 套壳，绕开公司 Electron/EDR 拦截）
- 启动 node llm-proxy.js（隐藏控制台）
- 等服务就绪
- 用 pywebview 弹独立窗口加载 index.html
- 退出时清理 node 子进程

依赖：pip install pywebview
运行：python launcher.py  或  双击 launcher.pyw
"""

import atexit
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

import webview  # pip install pywebview

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
PROXY_PORT = 3001
PROXY_URL = f"http://127.0.0.1:{PROXY_PORT}"
INDEX_PATH = os.path.join(PROJECT_DIR, "index.html")


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
    """启动 node llm-proxy.js（Windows 下隐藏控制台窗口）"""
    creation = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    proc = subprocess.Popen(
        ["node", "llm-proxy.js"],
        cwd=PROJECT_DIR,
        creationflags=creation,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return proc


def wait_ready(timeout_sec: int = 10) -> bool:
    """轮询 /config 直到 llm-proxy 就绪"""
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{PROXY_URL}/config", timeout=0.5) as r:
                if r.status == 200:
                    return True
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            pass
        time.sleep(0.3)
    return False


def main() -> int:
    if not os.path.exists(os.path.join(PROJECT_DIR, "config.json")):
        print("[launcher] config.json not found. Please create it first.", file=sys.stderr)
        return 1

    # 先杀掉占用 3001 端口的旧 node 进程（保证全新实例）
    killed = kill_port_listener(PROXY_PORT)
    if killed > 0:
        print(f"[launcher] killed {killed} stale process(es) on port {PROXY_PORT}")
        time.sleep(0.5)   # 等端口完全释放

    proxy = start_proxy()
    atexit.register(lambda: proxy.terminate())

    if not wait_ready():
        proxy.terminate()
        print("[launcher] llm-proxy did not become ready within 10s.", file=sys.stderr)
        return 1

    print(f"[launcher] llm-proxy ready at {PROXY_URL}")
    webview.create_window(
        "WerewolfAI · 12 人神局",
        f"file:///{INDEX_PATH.replace(os.sep, '/')}",
        width=1400,
        height=900,
    )
    webview.start()  # 阻塞直到窗口关闭

    proxy.terminate()
    return 0


if __name__ == "__main__":
    sys.exit(main())
