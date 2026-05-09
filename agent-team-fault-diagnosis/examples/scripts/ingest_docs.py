#!/usr/bin/env python3
"""
設計書 (Word/Excel/PDF) を Markdown に変換するオフラインスクリプト。

Usage:
    python scripts/ingest_docs.py <input_dir> [<output_dir>]

例:
    python scripts/ingest_docs.py ./設計書/  ./docs-md/

各設計書ファイルは見出し階層を保持して section 単位で分割し、
agent が引用しやすい形で `<output_dir>/<原ファイル名>/<NN-見出し>.md` に保存する。
各 .md の YAML frontmatter に source_file / section / page を記録。

依存:
    pip install docling pyyaml
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

SUPPORTED_EXTS = {".docx", ".xlsx", ".pdf", ".pptx"}
SECTION_HEAD_RE = re.compile(r"^(#{1,4})\s+(.+)$", re.MULTILINE)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="設計書を Markdown に変換")
    p.add_argument("input_dir", type=Path, help="設計書原本ディレクトリ")
    p.add_argument("output_dir", type=Path, nargs="?", default=Path("./docs-md"),
                   help="出力先 (default: ./docs-md)")
    p.add_argument("--max-section-chars", type=int, default=8000,
                   help="1 .md のソフト上限文字数 (default 8000)")
    return p.parse_args()


def slugify(text: str, max_len: int = 60) -> str:
    text = re.sub(r"[\s/\\:*?\"<>|]+", "-", text.strip())
    text = re.sub(r"-+", "-", text).strip("-")
    return text[:max_len] if text else "section"


def docling_convert(input_path: Path) -> str:
    """docling で Word/Excel/PDF → Markdown."""
    try:
        from docling.document_converter import DocumentConverter
    except ImportError:
        log.error("docling が未インストールです。`pip install docling` してください")
        sys.exit(1)

    converter = DocumentConverter()
    result = converter.convert(str(input_path))
    return result.document.export_to_markdown()


def split_by_headings(markdown: str) -> list[tuple[int, str, str]]:
    """Markdown を見出しで分割。戻り値: [(level, heading, body), ...]."""
    sections: list[tuple[int, str, str]] = []
    matches = list(SECTION_HEAD_RE.finditer(markdown))

    if not matches:
        return [(1, "全体", markdown)]

    # 先頭から最初の見出しまでをイントロとして含める
    if matches[0].start() > 0:
        intro = markdown[: matches[0].start()].strip()
        if intro:
            sections.append((0, "前文", intro))

    for i, m in enumerate(matches):
        level = len(m.group(1))
        heading = m.group(2).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(markdown)
        body = markdown[start:end].strip()
        sections.append((level, heading, body))

    return sections


def write_section(
    output_dir: Path, source_file: str, section_num: int, level: int,
    heading: str, body: str
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{section_num:02d}-{slugify(heading)}.md"
    fpath = output_dir / fname

    frontmatter = (
        "---\n"
        f"source_file: {source_file}\n"
        f"section: {heading}\n"
        f"section_num: {section_num}\n"
        f"level: {level}\n"
        "---\n\n"
    )
    content = frontmatter + f"# {heading}\n\n{body}\n"
    fpath.write_text(content, encoding="utf-8")


def process_file(input_file: Path, output_root: Path) -> int:
    log.info("変換開始: %s", input_file)
    try:
        md = docling_convert(input_file)
    except Exception as e:
        log.error("変換失敗 %s: %s", input_file, e)
        return 0

    sections = split_by_headings(md)
    out_dir = output_root / input_file.stem
    if out_dir.exists():
        for old in out_dir.glob("*.md"):
            old.unlink()

    for i, (level, heading, body) in enumerate(sections, start=1):
        if not body.strip():
            continue
        write_section(out_dir, input_file.name, i, level, heading, body)

    log.info("  → %d sections written to %s/", len(sections), out_dir)
    return len(sections)


def main() -> int:
    args = parse_args()

    if not args.input_dir.exists():
        log.error("入力ディレクトリ存在せず: %s", args.input_dir)
        return 1

    args.output_dir.mkdir(parents=True, exist_ok=True)

    files = [
        p for p in sorted(args.input_dir.rglob("*"))
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS
    ]
    if not files:
        log.warning("対象ファイルが見つかりません (%s 配下に %s)",
                    args.input_dir, ", ".join(SUPPORTED_EXTS))
        return 1

    total_sections = 0
    for f in files:
        total_sections += process_file(f, args.output_dir)

    log.info("完了: %d ファイル → 合計 %d sections (%s)",
             len(files), total_sections, args.output_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
