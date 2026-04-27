import platform
import re
import shutil
import ssl
import subprocess
import tempfile
from pathlib import Path

# Fix macOS Python SSL certificate issue (common with python.org installers)
try:
    import certifi
    ssl._create_default_https_context = lambda: ssl.create_default_context(cafile=certifi.where())
except ImportError:
    pass

_IS_APPLE_SILICON = platform.system() == 'Darwin' and platform.machine() == 'arm64'


def extract_video_id(url: str) -> str | None:
    patterns = [
        r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})',
        r'^([a-zA-Z0-9_-]{11})$',
    ]
    url = url.strip()
    for pattern in patterns:
        m = re.search(pattern, url)
        if m:
            return m.group(1)
    return None


def fetch_transcript(video_id: str, languages: list[str]) -> tuple:
    """Return (snippets, language_code, is_generated) or (None, None, None)."""
    from youtube_transcript_api import YouTubeTranscriptApi
    from youtube_transcript_api._errors import NoTranscriptFound, TranscriptsDisabled

    try:
        api = YouTubeTranscriptApi()
        transcript_list = api.list(video_id)

        try:
            t = transcript_list.find_manually_created_transcript(languages)
            return list(t.fetch()), t.language_code, False
        except NoTranscriptFound:
            pass

        try:
            t = transcript_list.find_generated_transcript(languages)
            return list(t.fetch()), t.language_code, True
        except NoTranscriptFound:
            pass

        for t in transcript_list:
            return list(t.fetch()), t.language_code, t.is_generated

    except (TranscriptsDisabled, Exception):
        pass

    return None, None, None


def download_audio(url: str, output_dir: str) -> str:
    """Download audio via yt-dlp CLI and return path to mp3 file."""
    yt_dlp = shutil.which('yt-dlp')
    if not yt_dlp:
        # Common non-PATH install locations
        for candidate in ['/opt/homebrew/bin/yt-dlp', '/usr/local/bin/yt-dlp']:
            if Path(candidate).exists():
                yt_dlp = candidate
                break
    if not yt_dlp:
        raise RuntimeError(
            "未找到 yt-dlp，请先安装：\n"
            "  macOS:   brew install yt-dlp\n"
            "  Windows: winget install yt-dlp.yt-dlp\n"
            "  Linux:   pip install yt-dlp"
        )

    output_template = str(Path(output_dir) / '%(id)s.%(ext)s')
    cmd = [
        yt_dlp,
        '-x',
        '--audio-format', 'mp3',
        '--audio-quality', '0',
        '--no-playlist',
        '-o', output_template,
        url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp 下载失败: {result.stderr[-500:]}")

    mp3_files = list(Path(output_dir).glob('*.mp3'))
    if not mp3_files:
        raise RuntimeError("未找到下载的音频文件")
    return str(mp3_files[0])


_MLX_MODELS = {
    'tiny':   'mlx-community/whisper-tiny-mlx',
    'base':   'mlx-community/whisper-base-mlx',
    'small':  'mlx-community/whisper-small-mlx',
    'medium': 'mlx-community/whisper-medium-mlx',
    'large':  'mlx-community/whisper-large-v3-mlx',
    'turbo':  'mlx-community/whisper-large-v3-turbo',
}


def _get_faster_whisper_device() -> tuple[str, str]:
    """Return (device, compute_type) for faster-whisper based on available hardware."""
    try:
        import torch
        if torch.cuda.is_available():
            return 'cuda', 'float16'
    except ImportError:
        pass
    return 'cpu', 'int8'


def transcribe_audio(
    audio_path: str,
    model_name: str = 'turbo',
    language: str | None = None,
    progress_callback=None,
) -> tuple:
    """Transcribe audio. Uses mlx-whisper on Apple Silicon, faster-whisper elsewhere."""

    # ── Apple Silicon: mlx-whisper (GPU) ─────────────────────────────────────
    if _IS_APPLE_SILICON:
        try:
            import mlx_whisper
            repo = _MLX_MODELS.get(model_name, f'mlx-community/whisper-{model_name}-mlx')
            if progress_callback:
                progress_callback(0.1, f'⚡ 加载 {model_name} 模型（Apple GPU）…')

            kwargs = {'path_or_hf_repo': repo, 'verbose': False}
            if language:
                kwargs['language'] = language

            result = mlx_whisper.transcribe(audio_path, **kwargs)
            segments = [
                {'start': s['start'], 'end': s['end'], 'text': s['text']}
                for s in result.get('segments', [])
            ]
            return result['text'].strip(), segments
        except Exception:
            pass  # fall through to faster-whisper

    # ── Windows / Linux / Intel Mac: faster-whisper ───────────────────────────
    from faster_whisper import WhisperModel

    device, compute_type = _get_faster_whisper_device()
    accel_label = 'NVIDIA GPU' if device == 'cuda' else 'CPU'
    if progress_callback:
        progress_callback(0.1, f'加载 {model_name} 模型（{accel_label}）…')

    # turbo maps to large-v3 in faster-whisper
    fw_model = 'large-v3' if model_name == 'turbo' else model_name
    model = WhisperModel(fw_model, device=device, compute_type=compute_type)
    segments_gen, info = model.transcribe(
        audio_path,
        language=language,
        beam_size=5,
        vad_filter=True,
        vad_parameters={'min_silence_duration_ms': 500},
    )
    total_duration = info.duration or 1.0
    segments, texts = [], []
    for seg in segments_gen:
        segments.append({'start': seg.start, 'end': seg.end, 'text': seg.text})
        texts.append(seg.text)
        if progress_callback:
            ratio = min(seg.end / total_duration, 1.0)
            m, s = int(seg.end // 60), int(seg.end % 60)
            tm, ts = int(total_duration // 60), int(total_duration % 60)
            progress_callback(ratio, f'转录中 {m:02d}:{s:02d} / {tm:02d}:{ts:02d}')
    return ' '.join(texts).strip(), segments


def _seconds_to_hms(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def format_transcript(data, with_timestamps: bool = True) -> str:
    """Format youtube-transcript-api snippets or whisper segments into text."""
    lines = []
    for item in data:
        if hasattr(item, 'text'):
            text = item.text
            start = item.start
        else:
            text = item['text']
            start = item['start']

        text = text.strip()
        if not text:
            continue

        if with_timestamps:
            lines.append(f"[{_seconds_to_hms(start)}] {text}")
        else:
            lines.append(text)

    return '\n'.join(lines)


def translate_to_chinese(text: str) -> str:
    """Translate text to Chinese using Google Translate, preserving [HH:MM:SS] timestamps."""
    from deep_translator import GoogleTranslator

    translator = GoogleTranslator(source='auto', target='zh-CN')
    lines = text.split('\n')

    CHUNK_CHARS = 4000
    chunks, current, current_len = [], [], 0
    for line in lines:
        if current_len + len(line) + 1 > CHUNK_CHARS and current:
            chunks.append(current)
            current, current_len = [], 0
        current.append(line)
        current_len += len(line) + 1
    if current:
        chunks.append(current)

    translated_lines = []
    for chunk in chunks:
        result = translator.translate('\n'.join(chunk))
        translated_lines.append(result)

    return '\n'.join(translated_lines)
