"""Flask 路由蓝图注册"""

from .sessions import bp as sessions_bp
from .permissions_routes import bp as permissions_bp
from .models import bp as models_bp
from .rag import bp as rag_bp
from .ocr import bp as ocr_bp
from .tunnel_routes import bp as tunnel_bp
from .chat import bp as chat_bp


def register_blueprints(app):
    """注册所有路由蓝图"""
    app.register_blueprint(sessions_bp)
    app.register_blueprint(permissions_bp)
    app.register_blueprint(models_bp)
    app.register_blueprint(rag_bp)
    app.register_blueprint(ocr_bp)
    app.register_blueprint(tunnel_bp)
    app.register_blueprint(chat_bp)
