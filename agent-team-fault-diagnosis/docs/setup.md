# 導入手順

---

## 前提

| 項目 | 必要バージョン |
|---|---|
| VS Code | 1.90 以上 |
| Claude Code (VS Code extension) | 最新（Sonnet 4.6 利用可能なもの） |
| Python | 3.11 以上 |
| 顧客提供 | 障害票.xlsx テンプレートファイル |

---

## Step 1: kit を legacy app repo にコピー

```bash
# このリポジトリ（agent-team-fault-diagnosis/）を clone した状態で
cd <agent-team-fault-diagnosis のあるディレクトリ>

# legacy app repo にコピー
TARGET=/path/to/legacy-app-repo

cp -r examples/.claude   "$TARGET/"
cp -r examples/scripts   "$TARGET/"

mkdir -p "$TARGET"/{docs-md,past-incidents,incidents,output,templates}

# 顧客から受領した障害票テンプレを配置
cp /path/to/障害票_template.xlsx "$TARGET/templates/"
```

---

## Step 2: Python 依存をインストール

```bash
cd "$TARGET"
pip install docling openpyxl pyyaml
```

`docling` は Word/Excel/PDF parsing、`openpyxl` は Excel 出力、`pyyaml` は incident yaml 読込。

---

## Step 3: 設計書を Markdown 化

```bash
# 設計書原本を ./設計書/ に置いた前提
python scripts/ingest_docs.py    ./設計書/    ./docs-md/

# 過去障害票を ./過去障害票/ に置いた前提
python scripts/ingest_history.py ./過去障害票/ ./past-incidents/
```

確認:
```bash
ls docs-md/        # サブフォルダごとに section 単位 .md
ls past-incidents/ # INC-YYYYMM-NNN.md
```

合格基準:
- 見出し階層が `docs-md/` のディレクトリ階層に反映されている
- 各 .md の YAML frontmatter に `source_file` `section` `page` が記録されている
- 表が markdown table になっている

NG なら docling のバージョン or 設定を見直す。

---

## Step 4: VS Code で Claude Code 起動 → 動作確認

```bash
cd "$TARGET"
code .
```

VS Code 内で Claude Code (Sonnet 4.6) を起動。

サンプル incident yaml を投入:
```bash
cp <kit>/examples/incidents/INC-SAMPLE-001.yaml incidents/
```

Claude Code チャット欄に:
```
/障害修正 INC-SAMPLE-001
```

期待挙動:
- supervisor が yaml を Read
- 並列で subagent をディスパッチ
- output/INC-SAMPLE-001/ にファイル出力

---

## Step 5: 出力検証

```bash
ls output/INC-SAMPLE-001/
# 障害票.md
# 障害票.xlsx
# patches/
# evidence/
```

`障害票.md` を VS Code で開いて 8 セクション全て埋まっているか確認。`障害票.xlsx` をダブルクリックで開き、テンプレ崩れ・敬体崩れがないか目視。

---

## Step 6: 実運用へ

新規 障害発生時:
1. `incidents/INC-202604-001.yaml` を作成（[workflow.md](workflow.md) のフォーマット参照）
2. VS Code → `/障害修正 INC-202604-001`
3. `output/INC-202604-001/` を確認
4. リーダーへメール添付

---

## トラブルシュート

### `/障害修正` コマンドが認識されない
- `.claude/commands/障害修正.md` がリポジトリ root にあるか確認
- VS Code を一度 reload (Cmd/Ctrl + Shift + P → Developer: Reload Window)

### subagent が呼ばれない
- `.claude/agents/*.md` のファイル名と YAML frontmatter `name` が一致しているか
- `description` が「いつ呼ぶか」を具体的に書いているか（auto-routing に効く）

### permission prompt が連発する
- `.claude/settings.json` の `permissions.allow` を見直す
- VS Code のプロジェクト直下に置く（global ではなく）

### docling が遅い / OOM
- 設計書 1 ファイルずつ処理する
- 大きい PDF は事前に分割

### 障害票.xlsx の cell ズレ
- `examples/scripts/fill_template.py` 冒頭の `CELL_MAP` を顧客テンプレに合わせて修正
- できれば named range を使う設計に

### 敬体が崩れる
- `.claude/skills/keitai-japanese/SKILL.md` を強化
- supervisor プロンプトに「最終出力前に敬体チェック」を明示

---

## アンインストール

```bash
rm -rf .claude scripts docs-md past-incidents output incidents
# templates/, .claude/settings.json は残しても良い
```

---

## 関連文書

- [architecture.md](architecture.md)
- [workflow.md](workflow.md)
- [agents.md](agents.md)
