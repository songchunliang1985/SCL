"""
MCP Server: OCR — 基于PaddleOCR 3.x的图像文字识别
"""

import json
import base64
import os
import tempfile
from typing import Optional

# 尝试导入PaddleOCR
try:
    from paddleocr import PaddleOCR
    PADDLEOCR_AVAILABLE = True
except ImportError:
    PADDLEOCR_AVAILABLE = False

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "ocr_recognize",
            "description": "识别图像中的文字（OCR），支持base64编码图像或本地文件路径",
            "parameters": {
                "type": "object",
                "properties": {
                    "image_data": {
                        "type": "string",
                        "description": "base64编码的图像数据或本地文件路径"
                    },
                    "lang": {
                        "type": "string",
                        "description": "识别语言，支持：ch（中文）、en（英文），默认ch",
                        "default": "ch"
                    }
                },
                "required": ["image_data"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ocr_health_check",
            "description": "检查OCR服务状态和可用语言",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
]

# 全局OCR实例缓存
_ocr_instances = {}  # lang -> PaddleOCR instance


def _get_ocr_instance(lang: str = 'ch'):
    """获取或创建OCR实例（使用轻量 mobile 模型，避免卡顿）"""
    global _ocr_instances

    if not PADDLEOCR_AVAILABLE:
        raise ImportError("PaddleOCR未安装，请运行: pip install paddlepaddle paddleocr")

    if lang not in _ocr_instances:
        _ocr_instances[lang] = PaddleOCR(
            lang=lang,
            ocr_version='PP-OCRv5',
            text_detection_model_name='PP-OCRv5_mobile_det',
            text_recognition_model_name='PP-OCRv5_mobile_rec',
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
        )

    return _ocr_instances[lang]


def _resolve_image_path(image_data: str) -> str:
    """将 base64 数据转为临时文件路径，或直接返回已有文件路径。
    PaddleOCR 3.x predict() 接受文件路径。"""

    # 如果是文件路径
    if not image_data.startswith('data:image/') and len(image_data) < 1000 and os.path.exists(image_data):
        return image_data

    # base64 数据
    raw = image_data
    if raw.startswith('data:image/'):
        raw = raw.split(',', 1)[1]

    image_bytes = base64.b64decode(raw)
    tmp = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
    tmp.write(image_bytes)
    tmp.close()
    return tmp.name


def ocr_recognize(image_data: str, lang: str = 'ch', **kwargs) -> str:
    """识别图像中的文字"""
    tmp_path = None
    try:
        if not PADDLEOCR_AVAILABLE:
            return json.dumps({
                "error": "PaddleOCR未安装",
                "install_command": "pip install paddlepaddle paddleocr",
            }, ensure_ascii=False)

        img_path = _resolve_image_path(image_data)
        # 记录是否是临时文件，后面清理
        if img_path != image_data:
            tmp_path = img_path

        ocr = _get_ocr_instance(lang=lang)
        results = ocr.predict(img_path)

        texts = []
        confidences = []

        for r in results:
            rec_texts = r.get('rec_texts', [])
            rec_scores = r.get('rec_scores', [])
            for t, s in zip(rec_texts, rec_scores):
                texts.append(t)
                confidences.append(float(s))

        full_text = "\n".join(texts)
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

        return json.dumps({
            "text": full_text,
            "confidence": avg_confidence,
            "detected_count": len(texts),
            "language": lang,
            "message": "未检测到文字" if not texts else f"识别到 {len(texts)} 段文字",
        }, ensure_ascii=False)

    except Exception as e:
        return json.dumps({
            "error": str(e),
            "error_type": type(e).__name__
        }, ensure_ascii=False)
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def ocr_health_check() -> str:
    """检查OCR服务状态"""
    try:
        if not PADDLEOCR_AVAILABLE:
            return json.dumps({
                "status": "not_installed",
                "message": "PaddleOCR未安装",
                "install_command": "pip install paddlepaddle paddleocr",
            }, ensure_ascii=False)

        global _ocr_instances
        return json.dumps({
            "status": "ready",
            "paddleocr_available": True,
            "version": "3.x",
            "ocr_initialized_langs": list(_ocr_instances.keys()),
            "supported_languages": ["ch", "en"],
            "note": "首次调用 ocr_recognize 时会自动初始化 OCR 引擎（首次较慢）"
        }, ensure_ascii=False)

    except Exception as e:
        return json.dumps({
            "status": "error",
            "error": str(e)
        }, ensure_ascii=False)


TOOL_MAP = {
    "ocr_recognize": ocr_recognize,
    "ocr_health_check": ocr_health_check,
}

TOOL_LABELS = {
    "ocr_recognize": "🔤 OCR文字识别",
    "ocr_health_check": "🩺 OCR健康检查",
}

PERMISSION_TOOLS = set()
