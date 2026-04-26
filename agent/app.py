"""
Dragon Agent —— Flask 应用工厂 + 入口
模块化架构：核心逻辑在 core/，路由蓝图在 routes/
"""

import os
import sys
import threading

from flask import Flask, render_template

import config as cfg
from core import (
    ServiceRegistry, SessionStore, PermissionManager,
    TunnelManager, LlmClient, AgentRunner,
)
from routes import register_blueprints
from mcp_servers import load_all

# ── 路径兼容（支持 PyInstaller 打包模式） ─────────────
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
    BUNDLE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    BUNDLE_DIR = BASE_DIR

# 数据目录
DATA_DIR = os.path.join(BASE_DIR, "data")
SESSIONS_FILE = os.path.join(DATA_DIR, "sessions.json")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(os.path.join(DATA_DIR, "rag_docs"), exist_ok=True)


def create_app() -> Flask:
    """Flask 应用工厂：初始化服务、注册蓝图"""
    app = Flask(__name__, template_folder=os.path.join(BUNDLE_DIR, "templates"))

    # ── 构建 ServiceRegistry ──────────────────────────
    reg = ServiceRegistry()
    reg.session_store = SessionStore(SESSIONS_FILE)
    reg.permission_mgr = PermissionManager()
    reg.llm_client = LlmClient()
    reg.tunnel = TunnelManager()

    # 加载 MCP 工具
    tools, tool_map, tool_labels, file_tools = load_all()

    # model_resolver：AgentRunner 每次调用时获取当前模型和提供商
    def model_resolver():
        model = reg.current_model
        provider = cfg.get_provider_for_model(model)
        if not provider:
            raise ValueError(f"未知模型: {model}")
        return model, provider

    reg.agent = AgentRunner(
        tools, tool_map, tool_labels, file_tools,
        reg.permission_mgr, reg.llm_client, model_resolver,
    )

    # 注册到 Flask extensions
    app.extensions["registry"] = reg

    # ── 注册路由蓝图 ─────────────────────────────────
    register_blueprints(app)

    @app.route("/")
    def index():
        return render_template("index.html")

    return app


# ── 入口 ─────────────────────────────────────────────
if __name__ == "__main__":
    app = create_app()
    reg = app.extensions["registry"]

    # 延迟启动隧道
    def _delayed_tunnel():
        import time
        time.sleep(2)
        reg.tunnel.start()

    threading.Thread(target=_delayed_tunnel, daemon=True).start()
    app.run(debug=False, host="0.0.0.0", port=cfg.WEB_PORT, threaded=True)
