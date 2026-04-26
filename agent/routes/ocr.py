"""OCR 识别路由"""
import json
from flask import Blueprint, request, jsonify

bp = Blueprint('ocr', __name__)


@bp.route("/api/ocr", methods=["POST"])
def ocr_image():
    data = request.get_json()
    image_data = data.get("image_data", "")
    lang = data.get("lang", "ch")
    if not image_data:
        return jsonify({"error": "缺少 image_data"}), 400
    from mcp_servers.ocr import ocr_recognize
    return jsonify(json.loads(ocr_recognize(image_data=image_data, lang=lang)))
