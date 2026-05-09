# Changelog

## [0.1.0] - 2026-05-09

### Added
- 初版リリース
- Claude Code (VS Code) ネイティブの multi-agent fault-correction kit
- 配布構成:
  - `README.md` 主設計文書（Mermaid 全体図 1 枚）
  - `docs/architecture.md` 詳細アーキ（Mermaid 図 4 枚）
  - `docs/workflow.md` ワークフロー + 入出力サンプル
  - `docs/agents.md` 8 subagent 仕様
  - `docs/setup.md` 導入手順
- 8 subagents (`examples/.claude/agents/`):
  - `design-reader` 設計書 RAG
  - `frontend-analyzer` Spring Boot 解析
  - `backend-analyzer` COBOL→Java 解析
  - `mq-inspector` IBM MQ 通信解析
  - `impact-analyzer` 影響範囲解析
  - `history-searcher` 過去障害検索
  - `patch-proposer` 修正案生成（aider edit-block）
  - `report-writer` 障害票生成（Markdown + Excel）
- Slash command: `/障害修正 <incident-id>` (`examples/.claude/commands/障害修正.md`)
- 3 skills (`examples/.claude/skills/`):
  - `cobol-idioms` COBOL→Java 変換コード読解ガイド
  - `keitai-japanese` 敬体日本語スタイル
  - `shogai-template` 障害票 8 セクション構造
- 3 offline scripts (`examples/scripts/`):
  - `ingest_docs.py` Word/Excel/PDF → Markdown (Docling)
  - `ingest_history.py` 過去障害票 → Markdown + PII マスキング
  - `fill_template.py` 障害票.xlsx テンプレ fill-in (openpyxl)
- Sample 入出力:
  - `examples/incidents/INC-SAMPLE-001.yaml`
  - `examples/output/INC-SAMPLE-001/障害票.md`
  - `examples/output/INC-SAMPLE-001/patches/案A-*.diff`, `案B-*.diff`
- `examples/.claude/settings.json` permissions テンプレ（mvn / git push 等は deny）

### 設計指針
- LangGraph 等の独自フレームワーク **不採用**、Claude Code 標準機能のみで構成
- VS Code 上の Sonnet 4.6 のみで動作（Opus 切替不要）
- subagent 間通信は Claude Code の Agent ツール経由（並列ディスパッチ）
- patch 出力のみ、テストは人手検証ポリシー
- リーダーレビューは Markdown + Excel をメール添付で実施

### 参考にした GitHub プロジェクト
- paul-gauthier/aider — edit-block patch format
- FoundationAgents/MetaGPT — 構造化文書通信思想
- Azure-Samples/Legacy-Modernization-Agents — COBOL→Java agent role
- DS4SD/docling — 設計書 ingestion
- anthropics/claude-code — subagent / slash command / skill 仕様
