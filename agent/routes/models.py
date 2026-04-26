"""模型切换路由"""
from flask import Blueprint, request, jsonify, current_app
import config as cfg

bp = Blueprint('models', __name__)


def get_registry():
    return current_app.extensions['registry']


@bp.route("/api/model", methods=["GET"])
def get_model():
    reg = get_registry()
    return jsonify({"model": reg.current_model, "models": cfg.get_all_models()})


@bp.route("/api/model", methods=["POST"])
def set_model():
    model = request.get_json().get("model", "")
    provider = cfg.get_provider_for_model(model)
    if not provider:
        return jsonify({"error": f"不支持的模型: {model}"}), 400
    get_registry().current_model = model
    return jsonify({"ok": True, "model": model})
