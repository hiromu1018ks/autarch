# Autarch

[English](README.md) | **日本語**

> **迷いを、根拠のある判断に変える。**

Autarch は、[Claude Code](https://claude.com/claude-code) 用の意思決定スキルです。エージェントが判断に迷ったときに候補を比べ、作業を先へ進める手助けをします。

`/autarch` を実行すると、エージェントが候補と評価基準を整理します。評価には [TypeSafe AI](https://typesafe.ai/) の System One モデル Jev を使います。結果を受け取ったエンジンは、決められたルールに従って案を選ぶか、あなたにしか決められない点を質問します。

```text
エージェント: 「DBはPostgreSQLとSQLiteのどちらにしますか？」
あなた:       /autarch
Autarch:      SQLite を選択。ローカルの単一ユーザー用途なら
              外部サーバーが不要です。Jev の確信度: 97%
エージェント: 「了解しました。SQLiteで作業を続けます。」
```

## 仕組み

候補を作る役、候補を評価する役、最終結果を決める役を分けています。

| 役割 | 担当すること |
|---|---|
| エージェント | 未解決の質問を特定し、中立な候補を2〜5案作る。根拠を集め、評価基準を定める |
| Jev | 人の好みが判断に必要か、どの案が目的に合うか、各評価基準で各案がどの程度合うかを評価する |
| `decide.py` | 入力を検証し、送信前に秘密情報を伏せ、APIを呼び出す。結果に判定ルールを適用し、判断を記録する |

Jev は3種類の質問に答えます。Noul は人の好みや意向が必要か、Choice はどの候補がよいか、Score は各候補が評価基準をどの程度満たすかを判定します。

判断エンジンは、Python の標準ライブラリだけで動く単一スクリプトです。追加パッケージは必要ありません。しきい値の判定、入力確認、秘密情報のマスキング、ログ記録はコードで行います。

Jev に送る質問・候補・根拠・評価基準は、評価の一貫性を保つため常に英語です。元の言葉であることが根拠になる引用だけは、原文と英訳を添えます。結果と、あなたに返す質問は会話の言語で表示します。

### 判定の流れ

エンジンは次の順で判定します。条件に当てはまった時点で、その結果を返します。

1. **Jev のエラー**: API が失敗した、または有効な応答を返さなかった場合は `PROVIDER_UNAVAILABLE`。自動選択はしません。
2. **人の判断が必要か**: 人の好みや意向が必要だと Jev が判定し、その確率が `0.70` 以上なら `ASK_USER`。
3. **評価結果が一致するか**: Choice の1位と、評価基準を重み付けして集計した Score の1位が異なる場合は `ASK_USER`。
4. **上位候補に差があるか**: 1位と2位の確率差が `0.15` 未満なら `ASK_USER`。
5. **確信度は十分か**: 確信度が `0.85` 以上なら `SELECT_OPTION`、`0.60` 以上なら `SELECT_OPTION_WITH_CAUTION`、それ未満なら `ASK_USER`。

`ASK_USER` になると、Autarch は最初の技術的な質問をそのまま繰り返しません。判断を分ける要素に絞り、あなたにしか答えられない質問を返します。

Choice の `probabilities` は候補間の確率分布で、点数ではありません。複数の評価基準に基づく集計結果は `score_summary` に含まれます。

## インストール

必要なものは Python 3.10 以降、[Claude Code](https://claude.com/claude-code)、TypeSafe AI の API キーです。

```bash
# 1. skills CLI でインストール（利用中のエージェントを自動検出）
npx skills add hiromu1018ks/autarch

# 2. API キーをシェルの設定に追加（キーは TypeSafe AI のコンソールで取得）
echo 'export TYPESAFE_API_KEY="your-key"' >> ~/.bashrc
```

この例は Bash 向けです。別のシェルを使う場合は、そのシェルの設定ファイルに `TYPESAFE_API_KEY` を設定してください。

手動でインストールする場合は、リポジトリを取得して Claude Code のスキルディレクトリへリンクします。

```bash
git clone https://github.com/hiromu1018ks/autarch.git
mkdir -p ~/.claude/skills
ln -s /path/to/autarch/skills/autarch ~/.claude/skills/autarch
```

`/path/to/autarch` は、clone したリポジトリの実際のパスに置き換えてください。

Claude Code のセッションで、エージェントから判断を委ねたい質問が出たときに実行します。

```text
/autarch
```

Autarch が動くのは、あなたが `/autarch` を明示的に実行したときだけです。設定の `disable-model-invocation: true` により、エージェントが自分の判断で呼び出すことはありません。

## エンジンを直接実行する

スキルは `scripts/decide.py` を呼び出します。このスクリプトは単独でも実行できます。

```bash
python3 skills/autarch/scripts/decide.py --state-file state.json \
  [--model jev-latest] [--auto-select 0.85] [--review 0.60] \
  [--min-gap 0.15] [--human-preference 0.70] \
  [--timeout 30] [--endpoint https://api.typesafe.ai]
```

- **入力**: 判断内容を記した JSON ファイル。`goal`、`question`、2〜5件の `alternatives` が必要です。`criteria` は省略でき、指定する場合は0〜8件です。
- **標準出力**: 判定結果を表す JSON オブジェクトを1つ出力します。`decision`、`rule`、`selected_option`、`confidence`、`probabilities`、`score_summary` などが含まれます。
- **終了コード**: `0` は判定結果を出力（`PROVIDER_UNAVAILABLE` や `INSUFFICIENT_OPTIONS` を含む）、`2` は引数・ファイル読み込み・JSON 構文のエラー、`1` は内部エラーです。

入力 JSON の完全なスキーマと実行手順は [スキルの説明](skills/autarch/SKILL.md) を参照してください。

## プライバシーと秘密情報

- エージェントには、`.env` ファイル、認証情報、秘密鍵、シークレットストアを根拠として読まないよう指示しています。
- API へ送信する前に、エンジンが秘密情報を伏せます。対象は `password`、`token`、`api_key` などのキーと、`sk-...`、`ghp_...`、AWS キー、`Bearer ...`、秘密鍵ブロックなどの文字列パターンです。置き換え件数だけを報告します。
- 判断ログ `~/.autarch/decisions.jsonl` には、記録時刻、質問の要約、候補と評価基準の ID、確率や評価結果などの数値、判定結果、モデル名、処理時間を記録します。質問の要約は秘密情報を伏せ、500文字までにします。入力全体やシークレット値は記録しません。候補と評価基準の ID はそのまま記録されるため、秘密情報を含めないでください。
- エラーメッセージに秘密の値は含まれません。

## 開発

テストには `pytest` を使います。通常のテストはネットワークに接続しません。

```bash
python3 -m venv .venv
.venv/bin/pip install pytest

.venv/bin/python3 -m pytest tests/
```

TypeSafe AI の API キーを設定すると、実 API を使うスモークテストも実行できます。

```bash
AUTARCH_LIVE=1 .venv/bin/python3 -m pytest tests/test_live.py -v
```

主なファイルは次のとおりです。

```text
skills/autarch/SKILL.md                 # エージェント向けのスキル説明
skills/autarch/scripts/decide.py        # 標準ライブラリだけで動く判断エンジン
tests/                                  # pytest テスト（ネットワーク不要）と実 API テスト
docs/                                   # 要件定義書と設計資料
```

## 関連ドキュメント

- [要件定義書](docs/Autarch_requirements_v0.2.md): プロダクト要件、KPI、ロードマップ
- [実装設計書](docs/superpowers/specs/2026-09-30-autarch-skill-implementation-design.md): 入力形式、API 契約、判定ポリシー
- [実装計画](docs/superpowers/plans/2026-09-30-autarch-skill.md): 実装を進めた11タスクの TDD 計画

## ライセンス

[MIT](LICENSE)
