# 🎬 YouTube 字幕提取器 / YouTube Subtitle Extractor

从 YouTube 视频中提取字幕文本。有字幕直接提取，没有字幕自动下载音频并用 Whisper 转录，还支持将内容翻译成中文。

Extract subtitles from YouTube videos. Fetches existing captions directly; falls back to audio download + Whisper transcription when none are available. Optionally translates to Chinese via Claude API.

---

## ✨ 功能特性 / Features

| 功能 | 说明 |
|------|------|
| 🚀 直接提取字幕 | 优先通过 YouTube API 获取已有字幕，秒级响应 |
| 🎙️ Whisper 兜底转录 | 无字幕时自动下载音频并本地 AI 转录 |
| 🌐 多语言支持 | 中文、英文、日文、韩文及自动检测 |
| 🇨🇳 中文翻译 | 通过 Claude API 将英文等字幕翻译为中文 |
| ⏱️ 时间戳 | 可选保留 `[HH:MM:SS]` 时间戳 |
| 💾 下载导出 | 一键下载 `.txt` 字幕文件 |
| 🖥️ Web UI | Gradio 构建，浏览器访问，开箱即用 |

---

## 🚀 快速开始 / Quick Start

### 前置要求 / Prerequisites

- Python 3.10+
- [ffmpeg](https://ffmpeg.org/)（必须）：`brew install ffmpeg`
- [yt-dlp](https://github.com/yt-dlp/yt-dlp)（必须）：`brew install yt-dlp`

### 安装 / Installation

```bash
# 克隆仓库
git clone https://github.com/songcl/youtube-subtitle.git
cd youtube-subtitle

# 安装依赖
pip install -r requirements.txt
```

### 运行 / Run

```bash
python app.py
```

浏览器打开 → [http://127.0.0.1:7860](http://127.0.0.1:7860)

### 翻译功能配置 / Translation Setup（可选）

翻译功能需要 Claude API Key：

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

---

## 📖 使用说明 / Usage

1. 粘贴 YouTube 视频 URL（支持 `youtube.com/watch?v=` 和 `youtu.be/` 格式）
2. 选择语言偏好和 Whisper 模型（默认 `small`，准确度和速度均衡）
3. 按需勾选"包含时间戳"和"翻译为中文"
4. 点击 **🚀 提取字幕**

### Whisper 模型选择参考

| 模型 | 大小 | M 系列参考速度 | 推荐场景 |
|------|------|--------------|---------|
| `tiny` | 75 MB | 最快 | 快速预览 |
| `base` | 140 MB | 快 | 简短视频 |
| `small` | 466 MB | 中等（**默认**） | 大多数场景 |
| `medium` | 1.5 GB | 较慢 | 高准确度需求 |
| `large` | 2.9 GB | 慢 | 最高准确度 |

---

## 🛠️ 项目结构 / Project Structure

```
youtube-subtitle/
├── app.py                  # Gradio Web 应用入口
├── subtitle_extractor.py   # 核心逻辑（字幕获取 / 转录 / 翻译）
├── requirements.txt
└── README.md
```

---

## 📦 依赖 / Dependencies

| 包 | 用途 |
|----|------|
| `youtube-transcript-api` | 直接获取 YouTube 字幕 |
| `yt-dlp` | 下载音频（系统级，via Homebrew） |
| `openai-whisper` | 本地语音转文字 |
| `gradio` | Web UI 框架 |
| `anthropic` | Claude API，用于翻译 |

---

## 📄 License

MIT License — 详见 [LICENSE](LICENSE)
