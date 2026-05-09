# アーキテクチャ詳細

本ドキュメントは agent team の内部構造を 4 つの Mermaid 図で示します。

---

## 図1: 全体アーキテクチャ

[README.md](../README.md) 冒頭と同一。SE / Supervisor / 8 Subagents / データソース / 出力 / リーダーレビュー の関係を一目で把握できる。

```mermaid
flowchart TB
    SE[SE / 担当者<br/>VS Code + Claude Code]
    INPUT[incidents/INC-xxx.yaml]

    subgraph CLAUDE[".claude/"]
        CMD["/障害修正 (Supervisor)"]
        subgraph AGENTS["8 Subagents (Sonnet 4.6)"]
            A1[design-reader]
            A2[frontend-analyzer]
            A3[backend-analyzer]
            A4[mq-inspector]
            A5[impact-analyzer]
            A6[history-searcher]
            A7[patch-proposer]
            A8[report-writer]
        end
        SK[skills/]
    end

    D1[docs-md/]
    D2[past-incidents/]
    D3[src/]
    D4[templates/障害票.xlsx]
    OUT[output/INC-xxx/]
    LEAD[リーダー]

    SE --> CMD
    INPUT --> CMD
    CMD --> A1 & A2 & A3 & A4 & A5 & A6
    A1 -.-> D1
    A2 & A3 & A4 & A5 -.-> D3
    A6 -.-> D2
    AGENTS --> CMD
    CMD --> A7 --> A8 -.-> D4
    A8 --> OUT
    SK -.-> AGENTS
    OUT --> SE --> LEAD
```

---

## 図2: 実行シーケンス

`/障害修正 INC-xxx` を実行した時の時間軸。並列ディスパッチがポイント。

```mermaid
sequenceDiagram
    participant SE
    participant CMD as /障害修正<br/>(Supervisor)
    participant Para as 並列subagents<br/>(design/front/back/mq/impact/history)
    participant Patch as patch-proposer
    participant Report as report-writer
    participant FS as ファイルシステム

    SE->>CMD: /障害修正 INC-202604-001
    CMD->>FS: Read incidents/INC-xxx.yaml
    Note over CMD: 障害種別を判定<br/>呼ぶ subagent を決定

    par 並列ディスパッチ（1メッセージ複数Agent呼出）
        CMD->>Para: design-reader
        CMD->>Para: frontend-analyzer
        CMD->>Para: backend-analyzer
        CMD->>Para: mq-inspector
        CMD->>Para: impact-analyzer
        CMD->>Para: history-searcher
    end
    Para-->>CMD: 各々 要約のみ返却<br/>(file:line / file:section)

    Note over CMD: 集約 → 原因分析 synthesize<br/>設計書 vs 実装乖離をフラグ

    CMD->>Patch: 原因分析を渡す
    Patch->>FS: aider edit-block で patch 生成
    Patch-->>CMD: patches/*.diff

    CMD->>Report: 全 State を渡す
    Report->>FS: Bash python fill_template.py
    Report->>FS: Write 障害票.md
    Report-->>CMD: 完了

    CMD-->>SE: output/INC-xxx/ 一式
    SE->>SE: 内容確認 → メール添付
```

並列ディスパッチは Claude Code の Agent ツールを 1 メッセージ内で複数回呼び出すことで実現。最大 ~10 並列。

---

## 図3: ディレクトリ配置（kit ↔ 適用先）

`agent-team-fault-diagnosis/examples/` の中身を legacy app repo にコピーする。kit 自体は方案・サンプル集として独立。

```mermaid
flowchart LR
    subgraph KIT["agent-team-fault-diagnosis/<br/>（配布 kit）"]
        K1[README.md]
        K2[docs/]
        K3[examples/.claude/]
        K4[examples/scripts/]
        K5[examples/incidents/]
        K6[examples/output/]
    end
    subgraph TARGET["legacy-app-repo/<br/>（適用先）"]
        T1[.claude/<br/>← examples/.claude/ をコピー]
        T2[scripts/<br/>← examples/scripts/ をコピー]
        T3[docs-md/<br/>← ingest_docs.py で生成]
        T4[past-incidents/<br/>← ingest_history.py で生成]
        T5[incidents/<br/>← SE が yaml 作成]
        T6[output/<br/>← agent が出力]
        T7[templates/障害票.xlsx<br/>← 顧客提供]
        T8[src/ 既存]
    end
    K3 -.copy.-> T1
    K4 -.copy.-> T2
    K5 -.参考.-> T5
    K6 -.参考.-> T6
```

---

## 図4: subagent 内部処理（design-reader 例）

各 subagent は **separate context window** を持ち、与えられたタスクを Tools で完遂、要約結果のみ親に返す。

```mermaid
flowchart TD
    IN[親からの指示<br/>キーワード/対象]
    G[Glob docs-md/**/*.md]
    R[Grep キーワード]
    READ[Read 該当 .md]
    SUM[要約抽出<br/>file:section 引用付き]
    OUT[親へ返却<br/>引用リスト + 要点]
    IN --> G --> R --> READ --> SUM --> OUT
```

他 subagent も同パターン:
- **frontend-analyzer / backend-analyzer / mq-inspector / impact-analyzer**: `src/` を Glob/Grep/Read
- **history-searcher**: `past-incidents/` を Glob/Grep/Read
- **patch-proposer**: 上記 subagent 結果から Edit ツールで diff を生成、`git diff` で確認
- **report-writer**: 全結果を Markdown 化、`python fill_template.py` で xlsx 出力

---

## モデル配置

| シーン | モデル | 理由 |
|---|---|---|
| Supervisor | Sonnet 4.6 | VS Code 制約。routing も synthesis も Sonnet |
| 全 subagent | Sonnet 4.6 | 統一。フレームワーク制約だが、本ユースケースには十分 |

将来 API 経由で Opus 4.7 が利用可能になった場合は `patch-proposer` と原因分析 synthesis のみ Opus 化を検討。

---

## State の表現

LangGraph の Pydantic State 相当のものは **存在しない**。代わりに **Claude Code の親 context window** がそのまま State の役割を果たす:

- subagent 結果は親メッセージ履歴に蓄積
- 親（Supervisor）は履歴を見ながら次のステップを決定
- 障害票.md / .xlsx 生成時は report-writer に履歴の要約を渡す

これは **MetaGPT 風の構造化文書通信** とは異なるが、Sonnet 4.6 の長文脈（200K）で十分実用に耐える。

---

## 拡張ポイント

- **新 subagent 追加**: `examples/.claude/agents/<name>.md` を作るだけ
- **新 skill 追加**: `examples/.claude/skills/<name>/SKILL.md`
- **MCP server 連携**: 例えば JIRA や Backlog の障害チケット自動取得を追加するなら MCP server を `.mcp.json` で追加
- **多言語化**: skills/keitai-japanese を別言語版に差し替え可能

---

## 関連文書

- [workflow.md](workflow.md) — ワークフロー詳細と入出力サンプル
- [agents.md](agents.md) — 各 subagent の仕様
- [setup.md](setup.md) — 導入手順
