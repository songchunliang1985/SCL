---
title: YouTube字幕提取器
emoji: 🎬
colorFrom: blue
colorTo: purple
sdk: gradio
sdk_version: 4.0.0
app_file: app.py
pinned: false
---

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

### macOS（Apple Silicon 推荐）

```bash
brew install ffmpeg yt-dlp
pip install -r requirements.txt
python app.py
```

### Windows

```powershell
# 安装系统依赖（需要 winget，Windows 10/11 自带）
winget install Gyan.FFmpeg
winget install yt-dlp.yt-dlp

# 安装 Python 依赖
pip install -r requirements.txt
python app.py
```

> Windows 上不支持 mlx-whisper，会自动使用 faster-whisper。  
> 若有 NVIDIA 显卡，还需安装对应版本的 [CUDA Toolkit](https://developer.nvidia.com/cuda-downloads)，可自动启用 GPU 加速。

### Linux

```bash
# Ubuntu/Debian
sudo apt install ffmpeg
pip install yt-dlp
pip install -r requirements.txt
python app.py
```

启动后浏览器打开 → [http://127.0.0.1:7860](http://127.0.0.1:7860)

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

| 模型 | 大小 | Apple Silicon | Windows/Linux CPU | 推荐场景 |
|------|------|:---:|:---:|---------|
| `turbo` | ~800 MB | ⚡⚡⚡⚡ **（默认）** | ⚡⚡ | 速度和精度最佳平衡 |
| `small` | ~500 MB | ⚡⚡⚡ | ⚡⚡⚡ | 轻量快速 |
| `base` | ~150 MB | ⚡⚡⚡⚡⚡ | ⚡⚡⚡⚡ | 极速预览 |
| `tiny` | ~80 MB | ⚡⚡⚡⚡⚡ | ⚡⚡⚡⚡⚡ | 最快，精度较低 |
| `medium` | ~1.5 GB | ⚡⚡ | ⚡ | 高精度需求 |
| `large` | ~3 GB | ⚡ | 🐢 | 最高精度 |

> **Apple Silicon**：使用 mlx-whisper，调用 Apple GPU/Neural Engine  
> **Windows / Linux**：使用 faster-whisper；有 NVIDIA 显卡自动启用 CUDA 加速

---

## ☁️ 云端部署 / Cloud Deployment（Hugging Face Spaces）

将工具部署到 Hugging Face Spaces 后，任何设备（包括手机）都可通过公网 HTTPS 地址访问，无需开电脑。

**免费套餐规格**：2 vCPU、16GB RAM、无需信用卡、永久免费（闲置 30 分钟后休眠，访问时自动唤醒）

### 第一步：注册 Hugging Face

打开 [https://huggingface.co](https://huggingface.co) → Sign Up（免费注册）

### 第二步：创建 Space

1. 登录后点右上角头像 → **New Space**
2. 填写 Space name（如 `youtube-subtitle`）
3. **SDK 选择 Gradio**
4. License 选 MIT
5. 点击 **Create Space**

### 第三步：上传代码

**方式 A：通过 Git 推送（推荐）**

HF Space 本身是一个 Git 仓库，直接把本目录推送过去：

```bash
# 在 youtube-subtitle/ 目录下执行
git init
git remote add space https://huggingface.co/spaces/你的用户名/youtube-subtitle
git add .
git commit -m "init"
git push space main
```

**方式 B：网页手动上传**

在 Space 页面点 **Files** → **Add file** → 逐一上传以下文件：
- `app.py`
- `subtitle_extractor.py`
- `requirements.txt`
- `packages.txt`
- `README.md`

### 第四步：等待构建

上传后 HF 自动安装依赖并启动服务，构建过程约 3-5 分钟。  
在 Space 页面的 **Logs** 标签中可查看进度，出现以下内容即表示成功：

```
Running on public URL: https://你的用户名-youtube-subtitle.hf.space
```

### 第五步：访问使用

用手机浏览器打开上述地址即可，无需任何 App。

### 注意事项

| 事项 | 说明 |
|------|------|
| 冷启动 | 休眠后首次访问需等 30-60 秒唤醒 |
| 模型下载 | Whisper turbo（~800MB）在冷启动后首次转录时自动下载，约需 2-5 分钟 |
| 有字幕的视频 | 直接调用 YouTube API，无需 Whisper，几秒内返回结果 |
| 并发 | 免费版单实例，同时仅支持一人使用 |
| 数据安全 | 音频文件仅在服务器临时存储，处理完成后删除 |

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

| 包 | 平台 | 用途 |
|----|------|------|
| `youtube-transcript-api` | 全平台 | 直接获取 YouTube 字幕 |
| `yt-dlp` | 全平台（系统级安装） | 下载音频 |
| `mlx-whisper` | Apple Silicon 专用 | Apple GPU 加速语音转文字 |
| `faster-whisper` | 全平台 | Windows/Linux 转录（CUDA 或 CPU） |
| `gradio` | 全平台 | Web UI 框架 |
| `deep-translator` | 全平台 | Google 翻译，免费无需 Key |

---

## 📄 License

MIT License — 详见 [LICENSE](LICENSE)
