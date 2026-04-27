import os
import tempfile

import gradio as gr

from subtitle_extractor import (
    download_audio,
    extract_video_id,
    fetch_transcript,
    format_transcript,
    transcribe_audio,
    translate_to_chinese,
)

LANG_MAP = {
    '自动 / Auto': ['zh-Hans', 'zh-TW', 'zh', 'zh-CN', 'en'],
    '中文 / Chinese': ['zh-Hans', 'zh-TW', 'zh', 'zh-CN'],
    '英文 / English': ['en'],
    '日文 / Japanese': ['ja'],
    '韩文 / Korean': ['ko'],
}

WHISPER_LANG_MAP = {
    '自动 / Auto': None,
    '中文 / Chinese': 'zh',
    '英文 / English': 'en',
    '日文 / Japanese': 'ja',
    '韩文 / Korean': 'ko',
}


def process_video(url, lang_pref, whisper_model, with_timestamps, do_translate, progress=gr.Progress()):
    if not url or not url.strip():
        return '⚠️ 请输入 YouTube 视频 URL', '', None

    video_id = extract_video_id(url.strip())
    if not video_id:
        return '❌ 无法解析视频 ID，请检查 URL 格式', '', None

    languages = LANG_MAP.get(lang_pref, LANG_MAP['自动 / Auto'])

    # ── Step 1: try transcript API ────────────────────────────────────────────
    progress(0.05, desc='正在尝试获取字幕…')
    snippets, lang_code, is_generated = fetch_transcript(video_id, languages)

    if snippets:
        progress(0.7, desc='字幕获取成功，正在格式化…')
        text = format_transcript(snippets, with_timestamps)
        source_label = f"{'自动生成' if is_generated else '手动'} 字幕 ({lang_code})"
    else:
        # ── Step 2: download audio + whisper ─────────────────────────────────
        progress(0.1, desc='未找到字幕，正在下载音频（可能需要几分钟）…')
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                audio_path = download_audio(url.strip(), tmpdir)
            except RuntimeError as e:
                return f'❌ 音频下载失败: {e}', '', None

            progress(0.4, desc=f'音频下载完成，正在加载 Whisper {whisper_model} 模型…')
            whisper_lang = WHISPER_LANG_MAP.get(lang_pref)

            def on_segment(ratio, desc):
                # Map transcription ratio (0-1) into the 0.4–0.85 progress window
                progress(0.4 + ratio * 0.45, desc=f'🎙️ {desc}')

            try:
                _, segments = transcribe_audio(
                    audio_path,
                    model_name=whisper_model,
                    language=whisper_lang,
                    progress_callback=on_segment,
                )
            except Exception as e:
                return f'❌ Whisper 转录失败: {e}', '', None

        progress(0.88, desc='转录完成，正在格式化…')
        text = format_transcript(segments, with_timestamps)
        source_label = f'Whisper {whisper_model} 转录'

    # ── Step 3: optional translation ─────────────────────────────────────────
    if do_translate and text:
        progress(0.8, desc='正在翻译为中文（通过 Claude API）…')
        try:
            text = translate_to_chinese(text)
            source_label += ' → 中文翻译'
        except Exception as e:
            source_label += f' (翻译失败: {e})'

    progress(0.95, desc='正在生成下载文件…')
    tmp = tempfile.NamedTemporaryFile(
        mode='w', suffix='.txt', delete=False, encoding='utf-8', prefix=f'{video_id}_'
    )
    tmp.write(text)
    tmp.close()

    progress(1.0, desc='完成')
    return f'✅ {source_label}', text, tmp.name


# ── Gradio UI ─────────────────────────────────────────────────────────────────

custom_css = """
.title { text-align: center; font-size: 2rem; font-weight: 700; margin-bottom: 0.25rem; }
.subtitle { text-align: center; color: #6b7280; margin-bottom: 1.5rem; }
footer { display: none !important; }
"""

with gr.Blocks(title='YouTube 字幕提取器') as demo:
    gr.HTML('<div class="title">🎬 YouTube 字幕提取器</div>')
    gr.HTML(
        '<div class="subtitle">'
        '优先获取已有字幕 · 无字幕时自动下载并 Whisper 转录 · 支持翻译为中文'
        '</div>'
    )

    with gr.Row():
        url_input = gr.Textbox(
            label='YouTube 视频 URL',
            placeholder='https://www.youtube.com/watch?v=...  或  https://youtu.be/...',
            scale=4,
        )

    with gr.Row():
        lang_select = gr.Dropdown(
            choices=list(LANG_MAP.keys()),
            value='自动 / Auto',
            label='语言偏好',
            scale=2,
        )
        model_select = gr.Dropdown(
            choices=['tiny', 'base', 'small', 'medium', 'large'],
            value='small',
            label='Whisper 模型（无字幕时使用）',
            scale=2,
        )
        with gr.Column(scale=1):
            timestamps_cb = gr.Checkbox(value=True, label='包含时间戳')
            translate_cb = gr.Checkbox(value=False, label='翻译为中文')

    submit_btn = gr.Button('🚀 提取字幕', variant='primary', size='lg')

    status_box = gr.Textbox(label='状态', interactive=False, max_lines=2)

    text_output = gr.Textbox(
        label='字幕文本',
        lines=22,
        max_lines=40,
        interactive=True,
    )

    download_file = gr.File(label='💾 下载字幕文件 (.txt)', file_count='single')

    submit_btn.click(
        fn=process_video,
        inputs=[url_input, lang_select, model_select, timestamps_cb, translate_cb],
        outputs=[status_box, text_output, download_file],
    )

    gr.Examples(
        examples=[
            ['https://www.youtube.com/watch?v=JkSSFreIb04', '中文 / Chinese', 'small', True, False],
            ['https://www.youtube.com/watch?v=dQw4w9WgXcQ', '英文 / English', 'small', True, True],
        ],
        inputs=[url_input, lang_select, model_select, timestamps_cb, translate_cb],
        label='示例',
    )


if __name__ == '__main__':
    demo.launch(
        server_name='127.0.0.1',
        server_port=7860,
        share=False,
        css=custom_css,
        theme=gr.themes.Soft(),
    )
