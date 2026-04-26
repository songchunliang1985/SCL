"""隧道状态路由"""
from flask import Blueprint, jsonify, current_app

bp = Blueprint('tunnel', __name__)


@bp.route("/api/tunnel", methods=["GET"])
def tunnel_status():
    tunnel = current_app.extensions['registry'].tunnel
    return jsonify({"active": tunnel.is_alive, "url": tunnel.url})
