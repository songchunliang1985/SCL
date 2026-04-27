# 🎬 YouTube 字幕提取器 / YouTube Subtitle Extractor

从 YouTube 视频中提取字幕文本。有字幕直接提取，没有字幕自动下载音频并用 Whisper 转录，还支持将内容翻译成中文。

Extract subtitles from YouTube videos. Fetches existing captions directly; falls back to audio download + Whisper transcription when none are available. Optionally translates to Chinese via Google Translate.

---

## ✨ 功能特性 / Features

| 功能 | 说明 |
|------|------|
| 🚀 直接提取字幕 | 优先通过 YouTube API 获取已有字幕，秒级响应 |
| ⚡ Apple GPU 加速转录 | 无字幕时用 mlx-whisper 调用 Apple Silicon GPU，速度极快 |
| 🌐 多语言支持 | 中文、英文、日文、韩文及自动检测 |
| 🇨🇳 中文翻译 | 通过 Google 翻译将英文等字幕翻译为中文，免费无需 API Key |
| ⏱️ 时间戳 | 可选保留 `[HH:MM:SS]` 时间戳 |
| 💾 下载导出 | 一键下载 `.txt` 字幕文件 |
| 🖥️ Web UI | Gradio 构建，浏览器访问，开箱即用 |

---

## 🚀 快速开始 / Quick Start

### 前置要求 / Prerequisites

- Python 3.10+
- Apple Silicon Mac（M1/M2/M3/M4）推荐，可获得 GPU 加速
- [ffmpeg](https://ffmpeg.org/)（必须）：`brew install ffmpeg`
- [yt-dlp](https://github.com/yt-dlp/yt-dlp)（必须）：`brew install yt-dlp`

### 安装 / Installation

```bash
# 克隆仓库
git clone https://github.com/songchunliang1985/SCL.git
cd SCL/youtube-subtitle

# 安装依赖
pip install -r requirements.txt
```

### 运行 / Run

```bash
python app.py
```

浏览器打开 → [http://127.0.0.1:7860](http://127.0.0.1:7860)

---

## 📖 使用说明 / Usage

1. 粘贴 YouTube 视频 URL（支持 `youtube.com/watch?v=` 和 `youtu.be/` 格式）
2. 选择语言偏好（默认自动检测）
3. 选择 Whisper 模型（默认 `turbo`，速度快、精度高）
4. 按需勾选「包含时间戳」和「翻译为中文」
5. 点击 **🚀 提取字幕**

### 工作流程

```
输入 URL
  │
  ├─► 尝试 YouTube 字幕 API ──► 成功：直接返回字幕（秒级）
  │
  └─► 无字幕：yt-dlp 下载音频
            │
            └─► mlx-whisper 转录（Apple GPU）──► 格式化输出
                                                    │
                                         （可选）Google 翻译为中文
```

### Whisper 模型选择参考

> 所有模型在 Apple Silicon 上均通过 **mlx-whisper** 使用 GPU 加速

| 模型 | 大小 | Apple M 系列速度 | 推荐场景 |
|------|------|----------------|---------|
| `turbo` | ~800 MB | ⚡⚡⚡⚡ **（默认）** | 速度和精度最佳平衡 |
| `small` | ~500 MB | ⚡⚡⚡ | 轻量快速 |
| `base` | ~150 MB | ⚡⚡⚡⚡⚡ | 极速预览 |
| `tiny` | ~80 MB | ⚡⚡⚡⚡⚡ | 最快，精度较低 |
| `medium` | ~1.5 GB | ⚡⚡ | 高精度需求 |
| `large` | ~3 GB | ⚡ | 最高精度 |

---

## 🛠️ 项目结构 / Project Structure

```
youtube-subtitle/
├── app.py                  # Gradio Web 应用入口
├── subtitle_extractor.py   # 核心逻辑（字幕获取 / 转录 / 翻译）
├── requirements.txt        # Python 依赖
└── README.md
```

---

## 📦 依赖 / Dependencies

| 包 | 用途 |
|----|------|
| `youtube-transcript-api` | 直接获取 YouTube 字幕 |
| `yt-dlp` | 下载音频（系统级，via Homebrew） |
| `mlx-whisper` | Apple GPU 加速语音转文字 |
| `faster-whisper` | CPU 转录（非 Apple 硬件兜底） |
| `gradio` | Web UI 框架 |
| `deep-translator` | Google 翻译，免费无需 Key |

---

## 📄 License

MIT License — 详见 [LICENSE](LICENSE)
