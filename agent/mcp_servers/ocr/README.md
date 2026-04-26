# OCR MCP Server

基于PaddleOCR的图像文字识别MCP服务器。

## 功能特性

- 支持中文、英文、法文、德文、韩文、日文等多种语言
- 支持base64编码图像或本地文件路径
- 自动角度校正
- 返回文字内容、置信度、文字位置框等信息

## 安装依赖

OCR服务器需要以下Python包：

```bash
# 安装PaddleOCR及其依赖
pip install paddlepaddle paddleocr opencv-python numpy
```

## 可用工具

### 1. ocr_recognize
识别图像中的文字。

**参数：**
- `image_data`: base64编码的图像数据或本地文件路径
- `use_angle_cls`: 是否使用角度分类模型（默认True）
- `lang`: 识别语言（默认"ch"中文）

**支持的语言：**
- `ch`: 中文
- `en`: 英文
- `fr`: 法文
- `german`: 德文
- `korean`: 韩文
- `japan`: 日文

### 2. ocr_health_check
检查OCR服务状态和可用语言。

## 使用示例

### 识别本地图像文件
```python
# 识别图片中的文字
ocr_recognize("/path/to/image.jpg", lang="ch")
```

### 识别base64编码图像
```python
# 识别base64编码的图像
ocr_recognize("data:image/jpeg;base64,/9j/4AAQSkZJRgABAQ...", lang="en")
```

### 检查服务状态
```python
ocr_health_check()
```

## 返回格式

### ocr_recognize 返回示例：
```json
{
  "text": "识别的文字内容\n多行文字",
  "confidence": 0.95,
  "boxes": [[[x1,y1],[x2,y2],[x3,y3],[x4,y4]], ...],
  "confidences": [0.98, 0.92, ...],
  "detected_count": 3,
  "language": "ch"
}
```

### ocr_health_check 返回示例：
```json
{
  "status": "ready",
  "paddleocr_available": true,
  "opencv_available": true,
  "ocr_initialized": false,
  "supported_languages": ["ch", "en", "fr", "german", "korean", "japan"],
  "current_language": null,
  "note": "首次调用ocr_recognize时会自动初始化OCR引擎"
}
```

## 注意事项

1. 首次使用时会自动下载OCR模型文件（约几百MB）
2. 建议使用GPU加速以获得更好的性能
3. 对于大图像，识别时间可能较长
4. 支持常见的图像格式：JPG、PNG、BMP等