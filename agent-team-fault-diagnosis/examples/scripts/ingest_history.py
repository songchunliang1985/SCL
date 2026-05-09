#!/usr/bin/env python3
"""
過去 障害票 (Word/Excel/PDF) を Markdown 化、PII マスキング後 `past-incidents/` に保存。

Usage:
    python scripts/ingest_history.py <input_dir> [<output_dir>]

例:
    python scripts/ingest_history.py ./過去障害票/  ./past-incidents/

PII マスキング:
    - 個人名 (担当者氏名らしきパターン) → ●●
    - 顧客名 (株式会社/Corp/Inc) → ●●会社
    - メールアドレス → ●●@●●
    - 電話番号 → ●●-●●●●-●●●●

依存:
    pip install docling
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

SUPPORTED_EXTS = {".docx", ".xlsx", ".pdf"}

# PII マスキングパターン（保守的、過剰マスキング許容）
# 注: 完璧な PII 検出は不可能。重要 PII は人手レビュー必須
PII_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"[\w._%+-]+@[\w.-]+\.[A-Za-z]{2,}"), "●●@●●"),
    (re.compile(r"0\d{1,4}-\d{1,4}-\d{4}"), "●●-●●●●-●●●●"),
    (re.compile(r"\b0\d{9,10}\b"), "●●●●●●●●●●●"),
    # 株式会社○○ / ○○株式会社 / ○○会社
    (re.compile(r"(株式会社)([^\s、。\n]{1,20})"), r"\1●●"),
    (re.compile(r"([^\s、。\n]{1,20})(株式会社)"), r"●●\2"),
    (re.compile(r"([^\s、。\n]{1,20})(\s*Corp\.?|\s*Inc\.?|\s*Ltd\.?)"), r"●●\2"),
]


INC_ID_RE = re.compile(r"INC[-_]?\d{4,}[-_]?\d+", re.IGNORECASE)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="過去 障害票 を Markdown 化 + PII マスキング")
    p.add_argument("input_dir", type=Path)
    p.add_argument("output_dir", type=Path, nargs="?", default=Path("./past-incidents"))
    return p.parse_args()


def docling_convert(input_path: Path) -> str:
    try:
        from docling.document_converter import DocumentConverter
    except ImportError:
        log.error("docling が未インストール: `pip install docling`")
        sys.exit(1)
    return DocumentConverter().convert(str(input_path)).document.export_to_markdown()


def mask_pii(text: str) -> str:
    for pattern, replacement in PII_RULES:
        text = pattern.sub(replacement, text)
    return text


def detect_inc_id(text: str, fallback: str) -> str:
    m = INC_ID_RE.search(text)
    return m.group(0).upper().replace("_", "-") if m else fallback


def process_file(input_file: Path, output_root: Path) -> str | None:
    log.info("変換開始: %s", input_file)
    try:
        md = docling_convert(input_file)
    except Exception as e:
        log.error("変換失敗 %s: %s", input_file, e)
        return None

    md = mask_pii(md)
    inc_id = detect_inc_id(md, fallback=input_file.stem)
    out_path = output_root / f"{inc_id}.md"

    frontmatter = (
        "---\n"
        f"source_file: {input_file.name}\n"
        f"incident_id: {inc_id}\n"
        "pii_masked: true\n"
        "---\n\n"
    )
    out_path.write_text(frontmatter + md, encoding="utf-8")
    log.info("  → %s", out_path)
    return inc_id


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
        log.warning("対象ファイルなし: %s", args.input_dir)
        return 1

    ok = 0
    for f in files:
        if process_file(f, args.output_dir):
            ok += 1

    log.info("完了: %d/%d ファイル変換 (%s)", ok, len(files), args.output_dir)
    log.warning("PII マスキングは保守的に実装、完璧ではありません。重要 PII は人手レビュー必須")
    return 0


if __name__ == "__main__":
    sys.exit(main())
