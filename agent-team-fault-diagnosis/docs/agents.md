# Subagent 仕様

8 つの subagent + 1 つの supervisor (slash command)。各 `.md` ファイルは Claude Code 仕様の YAML frontmatter + プロンプト本体。

---

## 共通定義フォーマット

```yaml
---
name: <agent-name>            # ファイル名と一致
description: <呼び出し条件>    # supervisor が auto-routing に使う
tools: Read, Grep, Glob, ...   # 使えるツール（最小権限）
model: sonnet                  # Sonnet 4.6 統一
---
<システムプロンプト本体>
```

呼び出しは parent agent (supervisor) が `Agent` ツールで `subagent_type: <name>` を指定。

---

## 1. design-reader（設計書RAG）

| 項目 | 値 |
|---|---|
| name | design-reader |
| 責務 | `docs-md/` 配下の設計書 Markdown から関連箇所を抽出、引用付きで返却 |
| tools | Read, Grep, Glob |
| 入力 | 障害キーワード、対象画面/業務 ID |
| 出力 | 引用リスト `file:section + 抜粋（200字以内）` |

ポイント:
- 引用は必ず `<file>:<section-num>` 形式（hallucination 防止）
- 該当箇所が無ければ「設計書未記載」と明記
- 関連性の低いものは除外（top 5-10 まで）

## 2. frontend-analyzer

| 項目 | 値 |
|---|---|
| name | frontend-analyzer |
| 責務 | Spring Boot 側の Controller / Service / Thymeleaf / JSP を解析、画面フロー記述 |
| tools | Read, Grep, Glob |
| 入力 | 画面 ID / URL パス |
| 出力 | `file:line` リスト + フロー説明 |

ポイント:
- @Controller / @RequestMapping / @GetMapping を起点に追跡
- DTO / Form / Validator の依存も含める
- Thymeleaf テンプレ参照も明示

## 3. backend-analyzer（COBOL→Java）

| 項目 | 値 |
|---|---|
| name | backend-analyzer |
| 責務 | COBOL→Java 変換コードを解析（業務処理ロジック） |
| tools | Read, Grep, Glob |
| 入力 | 業務処理 ID（例: 受注照会処理）/ メソッド名 |
| 出力 | `file:line` リスト + 処理フロー説明 |
| 連携 skill | `cobol-idioms` |

ポイント:
- COMP-3、copybook、固定長文字列、レベル番号などの非 idiomatic Java を理解
- `cobol-idioms` skill が自動 inject される
- 「綺麗にすべき」とは思わない（リファクタ提案は禁止）

## 4. mq-inspector

| 項目 | 値 |
|---|---|
| name | mq-inspector |
| 責務 | IBM MQ queue 定義 / 電文 layout / 送受信コードの突合 |
| tools | Read, Grep, Glob |
| 入力 | queue 名 / 電文 ID |
| 出力 | 電文フロー記述（送信元 → queue → 受信先 + 電文構造） |

ポイント:
- queue 定義は `*.mqsc` `*.xml` `application.yml` 等から探す
- copybook 電文 layout（フィールド順、長さ、COMP-3 など）を保持
- sender / receiver の片側のみ変更すると不整合 → 必ず両側確認

## 5. impact-analyzer（影響範囲）

| 項目 | 値 |
|---|---|
| name | impact-analyzer |
| 責務 | 変更対象の caller / callee を grep で列挙、デグレ確認用 |
| tools | Read, Grep, Glob, Bash(rg) |
| 入力 | 対象 `file:method` / クラス |
| 出力 | caller / callee リスト + 影響レベル評価 |

ポイント:
- ripgrep でメソッド名検索、Java の package import も考慮
- public / private / 継承関係を踏まえる
- 影響レベル: 低（同 package のみ）/ 中（別 module）/ 高（多 module）

## 6. history-searcher（過去障害検索）

| 項目 | 値 |
|---|---|
| name | history-searcher |
| 責務 | `past-incidents/` から類似事象を検索 |
| tools | Read, Grep, Glob |
| 入力 | 事象キーワード（タイムアウト、桁あふれ、null 等） |
| 出力 | 類似 INC-ID + 当時の対策抜粋 |

ポイント:
- 完全一致でなく類似度高い順に top 5
- 当時の対策・原因をそのまま返さず「参考情報」として返却
- PII（個人名・顧客名）は事前マスキング済前提

## 7. patch-proposer（修正案）

| 項目 | 値 |
|---|---|
| name | patch-proposer |
| 責務 | 原因分析を受けて修正案を aider edit-block 形式で生成 |
| tools | Read, Grep, Edit, Bash(git diff) |
| 入力 | 原因分析、関連 code refs |
| 出力 | `patches/案A-*.diff` `patches/案B-*.diff` |
| 連携 skill | (なし、bug_scope_only 制約はプロンプト本体に明記) |

ポイント:
- **複数案** 生成（保守的・抜本的の最低 2 案）
- aider edit-block format（`<<<<<<< SEARCH` / `=======` / `>>>>>>> REPLACE`）
- bug 直接対応のみ。リファクタ・スタイル変更禁止
- DB / MQ を触る patch には `[要レビュー注意]` バッジ
- patch 適用後の `git diff` を Bash で取得して整合確認

## 8. report-writer（障害票生成）

| 項目 | 値 |
|---|---|
| name | report-writer |
| 責務 | 全 subagent 結果を集約、障害票.md + 障害票.xlsx を生成 |
| tools | Read, Write, Bash(python scripts/fill_template.py) |
| 入力 | 全 State（事象、引用、コード refs、原因、対策） |
| 出力 | `output/INC-xxx/障害票.md`, `output/INC-xxx/障害票.xlsx` |
| 連携 skill | `keitai-japanese`, `shogai-template` |

ポイント:
- 8 セクション構造（[workflow.md](workflow.md) 参照）
- **敬体（です・ます）統一**、英語専門用語より日本語優先
- xlsx は `templates/障害票_template.xlsx` を fill-in
- subagent からのコード抜粋は `file:line` 参照に簡略化（コードブロック貼り付けは最小限）

---

## Slash Command (Supervisor)

`.claude/commands/障害修正.md`:

```yaml
---
description: 障害票生成と修正案提案。引数に incident ID（例: INC-202604-001）
argument-hint: <incident-id>
allowed-tools: Read, Write, Glob, Bash, Agent
---
あなたは障害対応リーダーです。$1 を incident ID として処理してください。

実行手順:
1. incidents/$1.yaml を Read
2. 障害種別判定 → 必要 subagent を **並列で** Agent ツール呼び出し
   ...
```

詳細は `examples/.claude/commands/障害修正.md`。

---

## Skills

3 つの skill が `.claude/skills/<name>/SKILL.md` 形式で常備:

| skill | 主な利用先 | 内容 |
|---|---|---|
| **cobol-idioms** | backend-analyzer | COMP-3, copybook, 固定長, PERFORM 風フローのパターン例 |
| **keitai-japanese** | report-writer | です・ます統一、英→日 用語対訳表 |
| **shogai-template** | report-writer, supervisor | 障害票 8 セクションの記述ガイドライン |

---

## tools 制限の方針

| ツール | 開放範囲 |
|---|---|
| Read | プロジェクト内の読みたいパスのみ（`.claude/settings.json` で allow） |
| Grep / Glob | 全 subagent 開放（読み取り専用） |
| Edit | patch-proposer のみ |
| Write | report-writer のみ |
| Bash | rg / git diff / git log / python scripts/fill_template.py のみ |
| **Bash(mvn)** | **deny**（テストは人手） |
| **Bash(git push/commit)** | **deny**（patch 提出のみ） |

詳細は `examples/.claude/settings.json`。

---

## 関連文書

- [architecture.md](architecture.md)
- [workflow.md](workflow.md)
- [setup.md](setup.md)
