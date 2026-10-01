# Autarch 評価セットと現行版 Baseline 実装設計

**日付:** 2026-10-01
**ステータス:** Draft(ユーザーレビュー待ち)
**関連文書:** `docs/Autarch_requirements_v0.2.md`(要件定義書 v0.2 §20)、`local-proposals/autarch-extension-proposal.ja.md`(拡張提案)

---

## 1. 目的と範囲

拡張提案の最初の実装段階として、**評価セットを作り、現行版の結果を基準値(baseline)として記録する**。今後の拡張(情報不足の分類と一度の追加調査、必須条件の判定)を導入した際に、同じケースで Before/After を比較できる土台を作る。

対象外(今回やらないこと):

- 現行の `decide.py`・`SKILL.md` の機能変更。追加調査、必須条件フィルタ、好みの推定、採用後フィードバックの収集はすべて次段階以降
- 閾値(auto_select 等)の見直し。confidence 分布は記録するが、変更は baseline 後の検証課題
- `local-proposals/` の提案文書自体の編集

## 2. 決定経緯

測定方式は Autarch 自身で評価した。3候補(固定 state のみ / full-flow のみ / ハイブリッド)を Jev に判定させた結果、**ASK_USER(choice_score_disagreement)**: Choice はハイブリッド(確率 0.78)、重み付き Score は固定 state(総合 0.77)が首位で割れた。決め手は「初回の baseline から agent 側(候補作成・評価軸選択)の品質測定を含めるか」であり、オーナーの判断(リリース済みスキルであり品質を優先)で**ハイブリッド**に決定した。

主要な決定:

| 決定 | 内容 |
|---|---|
| 測定方式 | ハイブリッド(固定 state トラック + full-flow トラック、runner は別) |
| 規模 | 固定 state 23ケース × 3回 = 69回の Jev 実行 + full-flow 5回の agent 実行 |
| full-flow 実行 | 自動 headless 実行(`claude -p`、fixture リポジトリ上) |
| 判定 | 機械判定のみ。Jev で Jev を審査しない |
| ケース確認 | baseline 実行前にオーナーがケースセットをレビュー |

## 3. 全体構成

```text
evals/
├── cases/                      # 固定 state トラック: 23ケース(1ファイル1ケース)
│   ├── db_constraint_clear.json
│   ├── db_info_missing.json
│   ├── ...
│   └── auth_violating_candidate.json
├── scenarios/                  # full-flow トラック: 5シナリオ
│   ├── database/
│   │   ├── fixture/            # 証拠収集対象の最小の疑似リポジトリ
│   │   ├── prompt.md           # シナリオ指示(headless 実行で渡す)
│   │   └── expectations.json
│   ├── authentication/
│   ├── test_framework/
│   ├── dependency/
│   └── deployment/
├── run_fixed_state.py          # 固定 state ランナー
├── run_full_flow.py            # full-flow ランナー
└── results/
    └── baseline-2026-10-XX/    # baseline 記録(§8)
```

- `evals/` は repo 直下に新設。要件書付録の想定(`src/autarch/evals/`)と異なるが、現行 repo は skill + tests 直下構成のためこちらに合わせる
- runner は Python 3.10+・stdlib のみ(SKILL 本体と同じ方針)。full-flow 実行には `claude` CLI が必要

## 4. 固定 state トラック

### 4.1 ケース形式

1 ファイル 1 ケース。`state` は SKILL.md Step 6 と同一 schema の完全な decision state(英語)。

```json
{
  "id": "db_constraint_clear",
  "topic": "database",
  "situation": "constraint_clear",
  "state": {
    "goal": "...",
    "question": "...",
    "known_constraints": ["..."],
    "environment": {},
    "evidence": ["..."],
    "alternatives": ["..."],
    "criteria": ["..."]
  },
  "expectations": {
    "acceptable_decisions": ["SELECT_OPTION", "SELECT_OPTION_WITH_CAUTION"],
    "acceptable_selections": ["sqlite"],
    "forbidden_selections": [],
    "requires_human_preference": false
  },
  "derived_from": null
}
```

`derived_from` は撹乱ケースのみ値を持ち、`{"base": "<base case id>", "perturbation": "<type>"}` を格納する。`requires_human_preference` は要件書 §20 のケース基準情報との対応を保つための参照用メタデータであり、判定には使わない(判定は `acceptable_decisions` で行う)。

制約:

- 全ケースの `state` が `decide.py` の `validate_state` を通ること(通常テストで機械検証)
- `situation` は `constraint_clear` / `info_missing` / `preference_needed` のいずれか
- `info_missing`・`preference_needed` では `acceptable_decisions` を `["ASK_USER"]` とする
- `forbidden_selections` は alternatives の id のみ指定できる

### 4.2 ベース 15ケース(題材 5 × 状況 3)

| 題材 | constraint_clear | info_missing | preference_needed |
|---|---|---|---|
| Database | 単一ローカルユーザー・完全オフライン前提 → SQLite が正解圏 | 保存先・配置形態が不明 | 将来の外部公開予定の有無で SQLite / PostgreSQL が分かれる |
| Authentication | 同一 origin の単一 web app → session cookie 優勢 | 既存 session 基盤の有無が不明 | モバイル app・外部 API 提供の予定の有無 |
| Test framework | 既存 codebase が pytest ベース → pytest | テスト方針・CI 環境が不明 | チームの好み・移行コストの許容 |
| Dependency | 用途に対し stdlib で足りる → 依存を追加しない | 性能要件が不明 | 依存を増やすことへの方針 |
| Deployment | 静的 site・無料枠前提 → 静的 hosting | トラフィック規模が不明 | 運用の手間と費用のどちらを優先 |

- 正解が一つに固定できないケースでは、`acceptable_selections` に許容圏を複数定義する(要件書 §20 の preferred_option / acceptable_alternatives に対応)
- `info_missing` では、判断に必要な情報が evidence に存在しない state を作る(現行版に追加調査はないため、低 confidence による ASK_USER が理想挙動)
- `preference_needed` では、技術面だけで決着しない trade-off を残す state を作る

### 4.3 撹乱 8ケース(4種 × Database・Authentication)

すべて `*_constraint_clear` ベースから機械的・手作業で変形し、`derived_from` を付ける。

| perturbation | 変形内容 | 合格基準(1実行あたり) |
|---|---|---|
| `reorder` | 候補の並び順を逆転 | ベース多数決と同じ候補が選択される(§7.3 の定義) |
| `detail_asymmetry` | 一つの候補だけ説明を詳細化 | 同上(説明量に結論が引っ張られない) |
| `evidence_removed` | 制約を確立している evidence を削除 | ASK_USER、または confidence < auto_select 閾値での選択 |
| `violating_candidate` | 必須条件に違反する候補を混入(例: 完全オフライン要件へのマネージド PostgreSQL 案) | 違反候補が自動選択されない(`forbidden_selections`) |

`evidence_removed` の合格基準は暫定であり、baseline の confidence 分布を見て見直す。

## 5. full-flow トラック

### 5.1 シナリオ構成

題材ごとに1シナリオ、計5回の agent 実行。状況配分: database=`constraint_clear`、authentication=`preference_needed`、test_framework=`constraint_clear`、dependency=`info_missing`、deployment=`preference_needed`。

各シナリオの構成要素:

- **`fixture/`**: agent が証拠収集で読む最小の疑似リポジトリ。例(database)は単一ユーザー CLI ツールの `pyproject.toml` + source 数ファイル + README。秘密情報は含めない
- **`prompt.md`**: シナリオ指示(英語)。仕事の依頼文と `/autarch` 実行指示、成果物の保存指定まで含む:
  - state は `./autarch-state.json` に保存
  - `decide.py` の stdout は `./autarch-resolution.json` に保存
- **`expectations.json`**: 後述の機械判定用期待値

### 5.2 expectations.json の形式

生成される alternatives の id・name は agent が決めるため、期待値は**キーワードグループ**で指定する(大文字小文字を区別しない部分一致)。

```json
{
  "situation": "constraint_clear",
  "required_alternatives": [["sqlite"], ["postgres", "postgresql"]],
  "forbidden_alternatives": [["csv", "plain text file"]],
  "acceptable_decisions": ["SELECT_OPTION", "SELECT_OPTION_WITH_CAUTION"],
  "acceptable_selections": [["sqlite"]],
  "requires_human_preference": false
}
```

- `required_alternatives`: 各グループ(同義語のリスト)のうち少なくとも1語が、いずれかの候補の `name` + `description` に含まれること
- `forbidden_alternatives`: いずれかのグループの語に部分一致する候補を生成したら失格
- `acceptable_selections`: 選択された候補(`selected_option` の id が指す候補の `name` + `description`)がどれかのグループに一致すること。`ASK_USER` が正解のシナリオでは `acceptable_decisions` を `["ASK_USER"]` とする

### 5.3 実行と回収(`run_full_flow.py`)

1. `fixture/` を temp directory へコピー
2. 作業 directory に `.claude/skills/autarch` symlink を作成(現行 repo と同じ相対 symlink 仕組み)
3. `claude -p "$(cat prompt.md)"` を起動し、ワークフロー完了まで待う。agent model は runner の `--agent-model` で**明示指定を必須**とし(既定値を置かない)、実行記録に残す。権限は headless 実行に必要な最小構成(作業 directory 内のファイル編集の許可、`decide.py` 実行に必要な Bash 許可)とし、具体的な flag 構成は実装時の smoke テストで確定する
4. `autarch-state.json`・`autarch-resolution.json`・agent の最終出力を回収
5. §5.2 の期待値で機械判定

agent model・起動フラグ・日時は実行記録に残す。state の評価軸(criteria)の適切さは機械判定せず、state を成果物として保存し人間が確認する(提案のとおり、当面は開発者が確認)。

## 6. ランナー共通仕様

- `decide.py` は実際の呼び出し経路と同じく subprocess で実行する(import しない)
- オプション(両 runner 共通): `--dry-run`(API・agent を実行せず実行計画のみ出力)、結果出力先の指定。固定 state ランナー: `--runs N`(既定 3)、`--model`(既定 `jev-latest`)、`--cases`(絞り込み)。閾値は `decide.py` の既定値を引き継ぎ上書き可
- `PROVIDER_UNAVAILABLE` のうち transport 系の失敗は、指数 backoff で最大2回まで再試行。それ以外の結果はそのまま記録
- 呼び出し間に短い interval(既定 1 秒)を置く
- 実行ごとに case id・run index・resolution 全文・latency・時刻を記録
- `TYPESAFE_API_KEY` がない場合は起動時に明示的に失敗する

## 7. 判定と指標

### 7.1 実行結果の分類(固定 state・full-flow 共通)

各実行(run)を次のいずれかに分類する:

- `completed`: decision が `SELECT_OPTION` または `SELECT_OPTION_WITH_CAUTION`
- `asked`: decision が `ASK_USER`
- `unavailable`: `PROVIDER_UNAVAILABLE`(指標の分母から除外し、件数のみ記録)

### 7.2 固定 state トラックの指標

| 指標 | 定義 |
|---|---|
| Decision Completion Rate | completed ÷ (completed + asked) |
| Correct Selection Rate | completed かつ選択が正解圏内 ÷ completed |
| Unsafe Auto-selection Rate | completed かつ(選択が正解圏外。forbidden 含む)÷ (completed + asked) — **最重要指標** |
| Appropriate Ask Rate | ASK_USER が期待されるケース(`acceptable_decisions` が `["ASK_USER"]`)で asked ÷ 当該実行数 |
| Perturbation Stability | §4.3 の合格基準を満たした実行 ÷ 撹乱ケースの実行数(種類ごとに集計) |

「正解圏内」の判定は、`acceptable_selections`(alternatives の id のリスト)への `selected_option` の包含で行う。分母が 0 になる指標(例: completed が 1 件もない場合の Correct Selection Rate)は `N/A` として記録する。

### 7.3 ベース多数決

`reorder`・`detail_asymmetry` の比較基準。ベースケース 3回のうち 2 回以上で選択された候補を「ベース多数決」とする。過半数候補が存在しない場合、そのベースは `unstable` とし、対応する撹乱ケースの Stability 判定は `inconclusive` として記録する(指標の分母から除外)。

### 7.4 full-flow トラックの指標

| 指標 | 定義 |
|---|---|
| Alternative Coverage | 全 `required_alternatives` グループが生成候補に一致したシナリオ ÷ 5 |
| Forbidden Avoidance | `forbidden_alternatives` に一致する候補を生成しなかったシナリオ ÷ 5 |
| Decision Correctness | §7.2 と同じ基準(選択は §5.2 のキーワード判定) |
| State Validity | 生成された state が `validate_state` を通ったシナリオ ÷ 5 |

### 7.5 ばらつきの扱い

- 3回の実行結果は全件記録する。集計指標は「各回で算出して平均 ± 範囲(min–max)」で報告する
- confidence・確率・human_preference_probability の分布は生データとして保存し、閾値見直し(要件の将来課題)に使えるようにする

## 8. baseline の記録物

`evals/results/baseline-YYYY-MM-DD/`(同日再実行時は `-2` を付加):

- `fixed_state_runs.jsonl` — 固定 state の実行ごとの生レコード
- `full_flow/<topic>/` — 回収した state・resolution・agent 出力
- `baseline.json` — 集計指標(機械可読)。将来の拡張比較はこの値と突き合わせる
- `SUMMARY.md` — 人間向け要約(日本語)。指標の表、実行環境(Jev model、閾値、agent model、日時)、既知の留保

baseline 一式は repo に commit する。以後の拡張は同じケースセットで再実行し、`baseline.json` と比較する。

## 9. 評価インフラ自体のテスト

- `tests/test_eval_runner.py`: 判定・指標計算の単体テスト(偽の resolution を与えて分類・集計が正しいこと)。ネットワーク不要。**TDD で実装する**
- ケースファイル・シナリオ期待値の schema 検証を通常テストに含める(全ケースが `validate_state` を通る、`derived_from` の参照先が存在、期待値のキーワード形式が正当、など)
- `--dry-run` のテスト(API を叩かない)
- full-flow の smoke テストは `AUTARCH_LIVE` と同じ流儀で、明示的な環境変数指定時のみ実行(金銭コストがあるため)

## 10. 進め方

1. runner と schema 検証を TDD で実装(§9)
2. 23ケースと5シナリオを作成
3. **オーナーがケースセットをレビュー**(提案の論点「評価ケースの妥当性は誰が確認するか」→ 当面は開発者)。修正を反映
4. baseline 実行: 固定 state 69回 + full-flow 5回
5. 集計して `baseline.json`・`SUMMARY.md` を作成し、commit

## 11. Dependencies

```text
Runtime: Python 3.10+ (stdlib only), TYPESAFE_API_KEY (Jev 実行時)
full-flow 実行時: claude CLI(headless)、agent 実行コスト
Development / test: pytest
```

SKILL 本体(`skills/autarch/`)には依存を追加しない。`decide.py`・`SKILL.md` は変更しない。
