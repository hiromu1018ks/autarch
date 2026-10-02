# Autarch

[English](README.md) | **日本語**

> **迷いを、根拠のある判断に変える。**

Autarch は、[Claude Code](https://claude.com/claude-code) 用の意思決定スキルです。エージェントが判断に迷ったときに候補を比べ、作業を先へ進める手助けをします。

`/autarch` を実行すると、エージェントが候補と評価基準を整理します。評価には [TypeSafe AI](https://typesafe.ai/) の System One モデル Jev を使います。エンジンは、必須条件を確認してから候補を評価し、案を選ぶか、追加調査やあなたへの質問に進みます。

```text
エージェント: 「DBはPostgreSQLとSQLiteのどちらにしますか？」
あなた:       /autarch
Autarch:      SQLite を選択。ローカルの単一ユーザー用途なら
              外部サーバーが不要です。Jev の確信度: 97%
エージェント: 「了解しました。SQLiteで作業を続けます。」
```

## 使い方

インストール後は、判断を任せたい場面で `/autarch` と入力します。質問を直接指定することもできます。

```text
/autarch PDF処理の方法を選んで。外部へのデータ送信は禁止。速度は重視したい。
```

JSON を自分で書く必要はありません。エージェントが「外部送信禁止」を必須条件、「速度」を評価基準として整理します。

| 状況 | Autarch の動き |
|---|---|
| 必須条件に違反する候補がある | その候補を採点前に除外する |
| 必須条件を満たすか未確認 | 比較を止め、一度調べてから判断し直す |
| 根拠が不足していると判定された | 不足する事実を調べるか、偏った説明を修正する。再実行は合わせて1回まで |
| あなたの好みや計画が必要 | 判断に必要な質問を1つ返す |
| 条件・評価・確信度が選択基準を満たす | 案を選び、元の作業を続ける |

条件確認・根拠の調査・説明の修正に使える再実行の枠は、合わせて1回です。
必須条件があるときは、その条件を伝えてください。調査しても分からないことは未確認のまま残し、条件を勝手に緩めません。
詳しい導入手順は [インストール](#インストール) を参照してください。

## 仕組み

候補を作る役、候補を評価する役、最終結果を決める役を分けています。

| 役割 | 担当すること |
|---|---|
| エージェント | 未解決の質問を特定し、中立な候補を2〜5案作る。必須条件と希望を分け、出典付きの根拠を集める。必要に応じて一度調べ直す |
| Jev | 人の意向、根拠の充足度、判断を妨げる要因、候補間の確率、評価基準ごとの点数を評価する |
| `decide.py` | 入力と必須条件を検証し、違反候補を除外する。秘密情報を伏せ、適格候補を API に送り、判定ルールを適用して結果を記録する |

Jev には、人の意向と根拠の充足度を確率で答える Noul を2問、候補と阻害要因を選ぶ Choice を2問、各評価基準×候補の Score を送ります。Score は基準の段階評価に沿った点数です。

判断エンジンは、Python の標準ライブラリだけで動く単一スクリプトです。追加パッケージは必要ありません。しきい値の判定、入力確認、秘密情報のマスキング、ログ記録はコードで行います。

Jev に送る質問・候補・根拠・評価基準は、評価の一貫性を保つため常に英語です。元の言葉であることが根拠になる引用だけは、原文と英訳を添えます。結果と、あなたに返す質問は会話の言語で表示します。

### 判定の流れ

入力と必須条件の検査後、Jev の評価結果を次の順で判定します。条件に当てはまった時点で、その結果を返します。

1. **Jev のエラー**: API が失敗した、または有効な応答を返さなかった場合は `PROVIDER_UNAVAILABLE`。自動選択はしません。
2. **人の判断が必要か**: 人の好みや意向が必要だと Jev が判定し、その確率が `0.70` 以上なら `ASK_USER`。
3. **根拠は十分か**: 根拠の充足度が `0.60` 未満で、阻害要因の確信度が `0.50` 以上なら `ASK_USER`。不足する事実の調査や判断材料の修正は1回までで、既に revision があれば質問を返します。好みや同点が阻害要因なら、判断に必要な質問を1つ返します。
4. **評価結果が一致するか**: Choice の1位と、評価基準を重み付けして集計した Score の1位が異なる場合は `ASK_USER`。
5. **上位候補に差があるか**: 1位と2位の確率差が `0.15` 未満なら `ASK_USER`。
6. **確信度は十分か**: 確信度が `0.85` 以上なら `SELECT_OPTION`、`0.60` 以上なら `SELECT_OPTION_WITH_CAUTION`、それ未満なら `ASK_USER`。

`ASK_USER` の理由が事実不足や判断材料の偏りなら、エージェントは一度調査・修正して再実行します。人の意向が必要な場合や、その1回を使っても解決できない場合は、最初の技術的な質問を繰り返さず、判断を分ける点に絞って質問します。

Choice の `probabilities` は候補間の確率分布で、点数ではありません。複数の評価基準に基づく集計結果は `score_summary` に含まれます。

### 根拠を確認してから必須条件を判定する

Jev を呼ぶ前に、エンジンが `hard_constraints` に登録された必須条件を
検査します。希望や優先順位は `criteria` に分けます。各条件には元の全候補の
確認結果を `met`（適合）、`violated`（違反）、`unknown`（未確認）で記録します。
適合・違反の判定には、`evidence_records` 内の確認済み根拠（`verified`）への
参照が1件以上必要です。推論（`inference`）だけなら `unknown` とします。
根拠には事実、出典、タイムゾーン付き RFC 3339 形式の確認日時 `checked_at` を
記録し、料金や提供機能など変動する事実は判断時に確認し直します。

次は必須項目をすべて含む最小入力例です。架空の会話で、ユーザーが両方式の
オフライン動作を明示的に確認した想定です。実際に使う際は、事実、出典、日時を
その判断で確認した内容に置き換えてください。既存プロジェクトについての記述ではありません。

```json
{
  "goal": "Store a local personal task list.",
  "question": "Choose a storage format for the offline task tool.",
  "known_constraints": [
    "Must work fully offline."
  ],
  "environment": {},
  "evidence": [
    "The user confirmed that both proposed implementations operate without network calls."
  ],
  "alternatives": [
    {
      "id": "sqlite",
      "name": "SQLite file",
      "description": "Store tasks in a local SQLite database."
    },
    {
      "id": "json",
      "name": "JSON file",
      "description": "Store tasks in a local JSON file."
    }
  ],
  "criteria": [],
  "evidence_records": [
    {
      "id": "runtime_confirmation",
      "fact": "The user confirmed that both the SQLite and JSON implementations operate locally without network calls.",
      "source": "example conversation, user message 2",
      "checked_at": "2026-10-01T09:00:00Z",
      "kind": "verified"
    }
  ],
  "hard_constraints": [
    {
      "id": "offline",
      "description": "Must work fully offline.",
      "assessments": {
        "sqlite": {
          "status": "met",
          "evidence_ids": [
            "runtime_confirmation"
          ]
        },
        "json": {
          "status": "met",
          "evidence_ids": [
            "runtime_confirmation"
          ]
        }
      }
    }
  ]
}
```

違反した候補は除外します。違反のない候補に未確認条件が残ると、比較を止めて
`ASK_USER / constraint_unverified` を返します。エージェントは一度調査し、
`revision.action=investigation` を付けて再実行します。条件確認、根拠不足の調査、
判断材料の修正が使える枠は、合わせて1回です。既に `revision` があれば
`investigation_exhausted` として、判断に必要な質問を1つ返します。
確認できなかった条件は `unknown` のまま残します。

適格な候補が2件未満なら、1件残っていても自動採用せず、
`INSUFFICIENT_OPTIONS / constraint_candidates_insufficient` を返します。
エージェントは条件を満たす別の候補を追加するか、ユーザーに条件を確認します。
本人の指示なしに条件を緩めたり、候補生成を自動で繰り返したりはしません。
出力の `constraint_check` には、モード、適格候補の ID、除外候補と違反条件・根拠の ID、
未確認の候補・条件の組み合わせが含まれます。

`hard_constraints` を省略した旧入力は従来の評価経路を使います。この互換経路には、
根拠に基づく新しい除外保証はありません。空配列を明示すると structured モードになり、
全候補を適格として扱います。エンジンが保証するのは入力契約と除外処理です。
出典の正しさや、記載した事実が条件を満たすことまでは保証しません。
構造化根拠と revision にも、秘密情報の収集禁止と再帰的な伏せ字処理を適用します。

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

スキルは `scripts/decide.py` を呼び出します。このスクリプトは単独でも実行できます。通常のスキル利用では、エージェントが入力 JSON を作成します。

```bash
python3 skills/autarch/scripts/decide.py --state-file state.json
```

既定値は `--model jev-latest`、`--auto-select 0.85`、`--review 0.60`、
`--min-gap 0.15`、`--human-preference 0.70`、`--sufficiency 0.60`、
`--blocker-confidence 0.50`、`--timeout 30`、`--endpoint https://api.typesafe.ai` です。
`--gate-order` は既定の `human_first` と、根拠の充足度を先に見る `evidence_first` を指定できます。
`--capture-evaluation` を付けると、丸め前の数値を `evaluation_snapshot` に出力し、同じ入力と保存値で閾値を比較できます。
どちらも評価・比較用のオプションで、通常の `/autarch` に指定する必要はありません。

- **入力**: 判断内容を記した JSON ファイル。`goal`、`question`、2〜5件の `alternatives` が必要です。`criteria` は省略でき、指定する場合は0〜8件です。
- **標準出力**: 判定結果を表す JSON オブジェクトを1つ出力します。`decision`、`rule`、`selected_option`、`confidence`、`probabilities`、`score_summary` などが含まれます。
- **終了コード**: `0` は判定結果を出力（`PROVIDER_UNAVAILABLE`、`INSUFFICIENT_OPTIONS`、入力検証で返る `ASK_USER` を含む）、`2` は引数・ファイル読み込み・JSON 構文のエラー、`1` は内部エラーです。

入力 JSON の完全なスキーマと実行手順は [スキルの説明](skills/autarch/SKILL.md) を参照してください。

## プライバシーと秘密情報

- エージェントには、`.env` ファイル、認証情報、秘密鍵、シークレットストアを根拠として読まないよう指示しています。
- API へ送信する前に、エンジンが秘密情報を伏せます。対象は `password`、`token`、`api_key` などのキーと、`sk-...`、`ghp_...`、AWS キー、`Bearer ...`、秘密鍵ブロックなどの文字列パターンです。置き換え件数だけを報告します。
- 判断ログ `~/.autarch/decisions.jsonl` には、記録時刻、質問の要約、候補と評価基準の ID、確率や評価結果などの数値、判定結果、モデル名、処理時間を記録します。質問の要約は秘密情報を伏せ、500文字までにします。入力全体やシークレット値は記録しません。候補と評価基準の ID はそのまま記録されるため、秘密情報を含めないでください。
- `--capture-evaluation` の保存対象は検証済みの数値・既知の ID・分類です。API 応答の自由文や追加 metadata は保存しません。保存した評価記録にも秘密情報を入れないでください。
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
tests/                                # pytest テスト（ネットワーク不要）と実 API テスト
evals/                                # 固定入力、追加調査、必須条件、full-flow、閾値比較の評価
docs/                                 # 要件定義書と設計資料
```

## 実装と検証の状況

2026-10-02 時点で、必須条件の事前検査、根拠不足時の一度だけの追加調査、評価値の保存・再生、学習用と検証用を分けた閾値比較を実装済みです。
通常のテストは638件成功、実 API 用の3件はスキップ。必須条件の独立評価は21/21組で成功しました。
ネットワーク復旧後の認証 full-flow は期待どおり `ASK_USER` となり、候補の網羅性・禁止候補の回避・判断結果・入力の妥当性の4項目に合格しました。

**閾値の既定値は変更していません。** 学習用で選んだ候補を別の30件で検証したところ、根拠不足の3件を誤って自動選択したため、不採用としました。
既存の固定入力評価では誤自動選択が8/69件残り、最初の拡張時の7/69件より1件増えています。
構造化条件の除外処理が動くことと、モデルが十分な根拠を集めて正しく判断することは別に検証しています。
実際のエージェントによる未確認条件の調査経路や、根拠が条件を本当に証明するかの確認は、引き続き課題です。

評価コードは `evals/` にあります。固定入力と追加調査は `run_fixed_state.py`、
必須条件は `run_constraint_cases.py`、スキル全体は `run_full_flow.py` で評価します。
`calibrate_thresholds.py` の `describe` / `search` / `validate` は保存した評価値を使い、API を呼ばずに比較します。
学習用で設定を1つ選び、事前に固定した別ケースで検証し、検証結果を見た再選択はしません。
実測の評価 runner は API を利用し、通常の判断ログにも記録するため、ネットワークと API キーが必要です。
full-flow には Claude Code も必要です。実行するオプションは各スクリプトの `--help` で確認できます。

- [現在の実装状況と残る課題](STATE.md)
- [最終評価と留保](evals/results/hard-constraints-calibration-2026-10-01/final/notes.md)
- [閾値比較と不採用理由](evals/results/hard-constraints-calibration-2026-10-01/notes.md)
- [接続復旧後の認証再評価](evals/results/hard-constraints-calibration-2026-10-01/auth-live-recheck-2026-10-02/notes.md)

## 関連ドキュメント

- [要件定義書](docs/Autarch_requirements_v0.2.md): プロダクト要件、KPI、ロードマップ
- [実装設計書](docs/superpowers/specs/2026-09-30-autarch-skill-implementation-design.md): 入力形式、API 契約、判定ポリシー
- [実装計画](docs/superpowers/plans/2026-09-30-autarch-skill.md): 実装を進めた11タスクの TDD 計画
- [根拠不足と追加調査の設計](docs/superpowers/specs/2026-10-01-info-gap-investigation-design.md): 一度だけの調査と問い直し
- [必須条件と閾値比較の設計](docs/superpowers/specs/2026-10-01-hard-constraints-calibration-design.md): 根拠付き条件、採点前の除外、独立した閾値検証

## ライセンス

[MIT](LICENSE)
