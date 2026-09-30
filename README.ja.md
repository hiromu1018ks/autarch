# Autarch

[English](README.md) | **日本語**

> **Autarch turns uncertainty into structured decisions.**
>
> Autarch は、ユーザーが判断に迷ったとき、エージェントが候補を作り、Jev が評価し、最も合理的な選択を導く意思決定支援スキルである。

`/autarch` は [Claude Code](https://claude.com/claude-code) 向けの意思決定スキルです。コーディングエージェントが「DBはPostgreSQLとSQLiteのどちらにしますか？」のような質問で作業を止めたとき、比較する知識や気力がなくても `/autarch` を実行すれば、あとは Autarch が処理します。エージェントが中立的な候補と評価軸を組み立て、[Jev](https://typesafe.ai/)（TypeSafe AI の System One モデル）が評価し、決定的なポリシーが最適案を採用して作業を続行するか、あなたにしか答えられない小さな質問を1つだけ返します。

```text
Agent:  "DBはPostgreSQLとSQLiteのどちらにしますか？"
User:   /autarch
Autarch: SQLite を選択 — ローカル単一ユーザー用途で外部サーバーが
         不要なため。Jev confidence: 97%
Agent:  "了解。SQLiteで実装を続ける。"
```

## 仕組み

3つの役割を意図的に分離しています。

| 役割 | 責務 |
|---|---|
| **Agent** | 未解決の質問を特定し、2〜5個の*中立的な*候補を生成し、根拠を収集し、評価軸を定義する |
| **Jev** | 評価する: Noul 質問1個（人間の好みが必要か?）、Choice 質問1個（どの案か?）、そして評価軸 × 候補ごとに Score 質問1個 |
| **decide.py** | 入力を検証し、シークレットを redact し、API を呼び、決定的なポリシーを適用し、判断を記録する |

エンジンは**標準ライブラリのみの単一 Python スクリプト**です。インストールするパッケージも、依存関係の drift もありません。決定的でなければならない部分（閾値・ゲート・redaction・ログ）はエージェントの判断ではなくコードに置いています。

Jev に渡す判断材料（質問・候補・根拠・評価軸）は、会話言語に関係なく評価精度のために常に**英語**で書かれます。結果やユーザーに返ってくる質問は、会話言語（日本語なら日本語）で表示されます。

### 判定ポリシー

毎回の実行は同じゲートをこの順序で通ります:

1. **Provider error** → `PROVIDER_UNAVAILABLE` — API の失敗・応答異常時には絶対に自動選択しない
2. **Human-preference ゲート**（Noul ≥ 0.70）→ `ASK_USER` — 判断があなたの好みや意向に依存する場合、confidence が高くても Autarch は選ばない
3. **Choice/Score 整合性** — Choice の1位と重み付き Score の1位が食違う場合 → `ASK_USER`
4. **Probability gap** — 上位2案の確率差が 0.15 未満の場合 → `ASK_USER`
5. **Confidence 帯域** — ≥ 0.85 で `SELECT_OPTION`、≥ 0.60 で `SELECT_OPTION_WITH_CAUTION`、未満で `ASK_USER`

判断があなたに戻ってくるとき、Autarch は元の技術的な質問を**そのまま繰り返しません**。決め手となる要素1つに絞った、あなたにしか答えられない最小の質問へ変換して返します。

なお Choice の `probabilities` は候補集合上の確率分布（総和 ≒ 1）であって点数ではありません。複数軸の評価は `score_summary` に別途含まれます。

## インストール

要件: Python 3.10+、[Claude Code](https://claude.com/claude-code)、TypeSafe AI の API キー。

```bash
# 1. skills CLI でインストール（エージェントを自動検出）
npx skills add hiromu1018ks/autarch

# 2. API キーを追加（TypeSafe AI コンソールで取得）
echo 'export TYPESAFE_API_KEY="your-key"' >> ~/.bashrc
```

<details>
<summary>手動インストール（clone + symlink）</summary>

```bash
git clone https://github.com/hiromu1018ks/autarch.git
mkdir -p ~/.claude/skills
ln -s /path/to/autarch/skills/autarch ~/.claude/skills/autarch
```

</details>

あとは Claude Code セッションの中で、委譲したい質問が出たら:

```text
/autarch
```

Autarch はユーザーが明示的に実行したときだけ動きます（`disable-model-invocation: true`）。エージェントが自分の判断で発動することはありません。

## エンジン CLI

スキルは `scripts/decide.py` を実行します。直接使うこともできます:

```bash
python3 skills/autarch/scripts/decide.py --state-file state.json \
  [--model jev-latest] [--auto-select 0.85] [--review 0.60] \
  [--min-gap 0.15] [--human-preference 0.70] \
  [--timeout 30] [--endpoint https://api.typesafe.ai]
```

- 入力: decision state JSON（`goal`、`question`、`alternatives[2〜5]`、任意の `criteria[0〜8]`）
- stdout: 常に1個の resolution JSON（`decision`、`rule`、`selected_option`、`confidence`、`probabilities`、`score_summary` など）
- 終了コード: `0` resolution を生成（`PROVIDER_UNAVAILABLE` を含む）· `2` usage/入力エラー · `1` 内部エラー

state スキーマと実行フローの詳細は [SKILL.md](skills/autarch/SKILL.md) を参照してください。

## プライバシーとシークレット

- エージェントには、`.env` ファイル・クレデンシャル・秘密鍵・シークレットストアを根拠として読み取らないよう指示しています。
- 送信前に、エンジンが sensitive キー（`password`、`token`、`api_key` など）とシークレットらしい文字列パターン（`sk-...`、`ghp_...`、AWS キー、`Bearer ...`、秘密鍵ブロック）を再帰的に redact します。報告されるのは置換件数のみです。
- decision log（`~/.autarch/decisions.jsonl`）にはサニタイズ済みの質問要約・option/criterion の id・数値のみを記録します。state 全文もシークレット値も残しません。
- エラーメッセージにシークレット値は含まれません。

## 開発

```bash
python3 -m venv .venv
.venv/bin/pip install pytest

.venv/bin/python3 -m pytest tests/            # 107テスト、ネットワーク不要
AUTARCH_LIVE=1 .venv/bin/python3 -m pytest tests/test_live.py -v   # 任意: 実APIスモークテスト
```

プロジェクト構成:

```text
skills/autarch/SKILL.md        # スキル本体（エージェント向け指示）
skills/autarch/scripts/decide.py  # 標準ライブラリのみのエンジン
tests/                          # pytest スイート（ネットワーク不要）+ live テスト
docs/                           # 要件定義・設計doc
```

## ドキュメント

- [要件定義書](docs/Autarch_requirements_v0.2.md) — プロダクト要件、KPI、ロードマップ
- [実装設計](docs/superpowers/specs/2026-09-30-autarch-skill-implementation-design.md) — state スキーマ、API 契約、ポリシー詳細
- [実装プラン](docs/superpowers/plans/2026-09-30-autarch-skill.md) — このコードを生んだ11タスクの TDD プラン

## ライセンス

[MIT](LICENSE)
