# 情報不足の分類と一度の追加調査 実装設計

**日付:** 2026-10-01
**ステータス:** Draft(ユーザーレビュー待ち)
**関連文書:** `local-proposals/autarch-extension-proposal.ja.md`(拡張提案「判断に迷ったら、本人の意向と調べられる事実を分ける」)、`docs/superpowers/specs/2026-10-01-eval-baseline-design.md`(評価基盤)、`STATE.md`

---

## 1. 目的と範囲

baseline-2026-10-01 が示した弱点 — 情報不足・根拠除去の場面で confidence 0.85 以上のまま自動選択する — への対抗として、**決められない理由の分類**と**一度までの追加調査・再評価**を導入する。

効果を見る指標は3つに固定する(baseline と同じケースセット・シナリオ・`judging.py` の定義で比較):

| 指標 | baseline(2026-10-01) |
|---|---|
| Appropriate Ask Rate | 53.33% |
| evidence_removed 撹乱 pass | 0/6 |
| Unsafe Auto-selection Rate | 20.29% |

対象外(今回やらないこと):

- evidence の構造化(出典・確認日時の schema 化)。evidence は `string[]` のまま。**次段階の必須条件拡張**で導入する
- 必須条件の採点前除外(次段階)
- 閾値(auto_select・sufficiency 等)の本見直し。現行値の妥当性は拡張後のデータが揃ってから検証する(STATE.md の方針)
- `INVESTIGATE` のような新 decision 値。`judging.py` の指標定義を変えない制約から採用しない
- 調査の時間・費用上限のための追加 knob。今回は「調査1回 + 再評価1回」の回数制限のみ

## 2. 決定経緯

| 論点 | 決定 | 理由 |
|---|---|---|
| ループの測定方法 | 2段階ケースを `cases_loop/` に追加(固定 state トラックで機械測定) | 既存23+5だけでは追加調査が起きたことを測定できず、full-flow 1シナリオに依存する。品質最優先で選択(オーナー判断) |
| 追加調査の範囲 | リポジトリ内を確認したうえで、外部ドキュメント・web 検索も1回の調査枠内で許可(オーナー判断) | 解決力を優先。評価の full-flow は制限付きツール構成を維持し、再現性を保つ |
| アプローチ | Jev への分類質問 + ASK_USER の理由拡張 + state の `revision` で一度制限 | 3指標に直接効き、指標定義不変の制約を守る。engine は状態を持たず state が真実の源になる |
| 分類の計算元 | Jev の質問(noul + choice) | 提案書「低い confidence の理由を数値だけから断定しない」。既存信号(confidence・gap・noul)だけでは根拠の不足・材料の偏りを識別できない |

採用しなかった案: 新 decision 値 `INVESTIGATE`(engine 主導ループ)は `classify_run` が invalid に分類し指標定義の変更を迫るため不採用。engine 不変・SKILL.md のみの拡張は固定 state トラックの3指標が動かないため不採用。

## 3. 全体構成

```text
skills/autarch/
├── SKILL.md                      # Step 11 を分類で分岐する形に拡張
└── scripts/decide.py             # 新 Jev 質問2種、根拠充足性ゲート、
                                  # blocker 情報の出力、revision の検証
evals/
├── cases_loop/                   # 【新】2段階ケース(3ケース想定)
├── case_schema.py                # loop ケースの schema 検証を追加
├── run_fixed_state.py            # loop ケースの2段階実行を追加
├── report_baseline.py            # loop 集計と --compare-to を追加
└── results/extension-info-gap-YYYY-MM-DD/   # 再実行の記録先
tests/
├── test_decide.py                # ゲート・revision・parse の単体テスト
└── test_eval_runner.py           # loop ケースの schema・実行・集計テスト
```

役割分担は不変: agent が判断材料を作り、Jev が評価し、`decide.py` が決定ポリシーを決定的に適用する。追加調査の実行主体は agent のみ(`decide.py` はファイルシステム・外部ともに調べない)。

## 4. 判定エンジン(decide.py)

### 4.1 新しい Jev 質問

`build_request` の `questions` に2つ追加する。API 呼び出し回数は現行のまま(1リクエストに同梱)。

| 質問 id | 型 | instructions |
|---|---|---|
| `evidence_sufficiency` | noul | Is there enough evidence in the state to select an option automatically? |
| `blocker_class` | choice | The decision cannot be resolved automatically on the provided material. Select the primary blocker. |

`blocker_class` の選択肢は固定4分類(提案書の表に対応):

| id | 対応する提案の分類 | agent が次に行うこと |
|---|---|---|
| `user_preference_unknown` | 本人の好みや計画が分からない | 答えやすい質問を一つ返す |
| `facts_missing` | 技術的な事実が足りない | 必要な情報を調べて再評価 |
| `material_bias` | 候補の説明や評価軸に偏りがある | 判断材料を修正する |
| `balanced_tie` | 比較しても優劣を決められない | 決め手となる条件を質問する |

`evidence_sufficiency` は要件定義書 §5 の想定質問("Is there enough evidence to select automatically?")を採用した。

### 4.2 `parse_answers` の検証

既存検証に加え、新質問の応答を検証する。不正なら既存と同じく `ProviderError`(`PROVIDER_UNAVAILABLE` 扱い):

- `evidence_sufficiency`: noul 型、値は [0, 1]
- `blocker_class`: choice 型。`choice` は4固定 id のいずれか、`confidence` は [0, 1]、`probabilities` は4固定 id をちょうどカバー

### 4.3 `resolve()` のゲート順序

既存ルールはすべて温存し、human_preference ルールの直後に根拠充足性ゲートを挿入する。

```text
1. human_preference ≥ 0.70                 → ASK_USER(rule=human_preference)【既存】
2. evidence_sufficiency < 0.60
   かつ blocker_confidence ≥ 0.50          → ASK_USER(rule=evidence_insufficient)
   かつ blocker_class を出力に添付           【新】
3. Choice/Score 不一致                      → ASK_USER(rule=choice_score_disagreement)【既存】
4. probability gap < 0.15                  → ASK_USER(rule=probability_gap)【既存】
5. confidence 三段階                       → SELECT_OPTION / WITH_CAUTION / ASK_USER【既存】
```

- 分類が何であれ根拠が足りなければ自動選択しない。confidence が高くても `evidence_removed` のような state では ASK_USER になる
- **誤検知の逃し弁**: `blocker_confidence < 0.50`(分類への確信が足りない)ならゲートを発動させず、以降の既存ルールにフォールバックする。constraint_clear ケースの過剰 ASK_USER 化を防ぐ
- 閾値は新フラグ `--sufficiency`(既定 0.60)と `--blocker-confidence`(既定 0.50)で変更可能。評価の実行記録に残す

### 4.4 出力スキーマ(追加のみ、既存フィールドは不変)

```json
{
  "decision": "ASK_USER",
  "rule": "evidence_insufficient",
  "evidence_sufficiency": 0.32,
  "blocker_class": "facts_missing",
  "blocker_confidence": 0.71,
  "reason": "..."
}
```

- ゲートが発動したときだけ `blocker_class`・`blocker_confidence` に値が入る(それ以外は null)。`evidence_sufficiency` は Jev 評価が成功したとき常に値が入る(`PROVIDER_UNAVAILABLE` では既存どおり null)
- `rule` の新しい値は `evidence_insufficient` と `investigation_exhausted` の2つ
- decision 値は既存の5種のまま。log record には `evidence_sufficiency` と `blocker_class` を追加する

### 4.5 state の `revision` フィールド(任意)と一度制限

```json
"revision": {
  "round": 1,
  "action": "investigation",
  "summary": "checked pyproject.toml and README; the app runs locally with no server component"
}
```

`validate_state` の扱い:

- 不在は許容(旧 state はそのまま通る)
- 存在する場合: `round` は 1 のみ・`action` は `investigation` / `material_fix` のいずれか・`summary` は空でない文字列(上限 500 字。`sanitize_text` と同じ枠)

挙動:

| state | 分類結果 | 出力 |
|---|---|---|
| revision なし | 不十分 + `facts_missing` / `material_bias` | ASK_USER `rule=evidence_insufficient` → agent は調査・修正へ |
| revision の有無を問わず | 不十分 + `user_preference_unknown` / `balanced_tie` | ASK_USER `rule=evidence_insufficient`(調査枠は消費しない。agent は直接問い直しへ) |
| revision あり | 依然 不十分 + `facts_missing` / `material_bias` | ASK_USER `rule=investigation_exhausted` → agent は問い直しへ |
| 任意 | ゲート不発(`evidence_sufficiency` 充分、または `blocker_confidence` 不足の逃し弁) | 通常解決(自動選択可)。既存ルールのみで判定 |

engine は呼び出し間の状態を持たない。`revision` の有無が「調査枠を使い切ったか」の真実の源で、state と出力だけでループの全域を機械検証できる。

### 4.6 revision の秘密情報の扱い

`revision.summary` は通常の文字列値として `redact()` の対象に含める(既存の再帰処理がそのまま適用される)。

## 5. スキルフロー(SKILL.md)

現行 Step 11(ASK_USER)を「rule と `blocker_class` で処理を分岐する」形に拡張する。Step 1〜10・12・13 は変更しない(Step 8 の出力フィールド一覧に新フィールドを追記のみ)。

```text
Step 11 — ASK_USER: rule と blocker_class で分岐
├─ evidence_insufficient + facts_missing + revision なし
│    ① リポジトリ内(設定・コード・文書)を確認
│    ② 足りなければ外部ドキュメント・web 検索(同じ1回の調査枠)
│    発見した事実は evidence に追記(出典を一文で添える。string 形式は維持)
│    revision {round:1, action:"investigation", summary} を設定
│    → decide.py をもう一度だけ実行(事実が見つからなくても再実行する)
├─ evidence_insufficient + material_bias + revision なし
│    候補間で説明の構造・詳しさを再均衡(同じ一度枠)
│    revision {round:1, action:"material_fix", summary} を設定 → 再実行
├─ investigation_exhausted
│    確認済みの事実と未確認事項を並べ、決め手となる質問を1つだけする
├─ blocker_class=user_preference_unknown / balanced_tie
│    現行どおり決め手の最小質問(元の専門質問は繰り返さない)
└─ その他ルール(low_confidence / probability_gap / disagreement)
     現行 Step 11 のまま
```

- 調査で事実を捏造しない。見つからない場合は「見つからなかった」ことを summary に書き、再実行して `investigation_exhausted` を経て問い直す
- 秘密情報(.env・credential 等)の調査対象からの除外、evidence への送信前伏せ字は現行規定のまま適用
- 再評価で `PROVIDER_UNAVAILABLE` になった場合は現行 Step 12 と同じ扱い(自動選択しない)。再評価のためにさらに Jev を呼び直すことはしない

## 6. 評価

### 6.1 2段階ケース(新設 `evals/cases_loop/`、3ケース)

決め手の事実が欠けた薄い state と、調査で得られる事実をセットにしたケース。題材は database・authentication・deployment を想定(内容は実装時に作成し、オーナーがレビュー)。

```json
{
  "id": "db_loop_resolvable",
  "topic": "database",
  "situation": "loop_resolvable",
  "state": { "...決め手の事実が欠けた state..." },
  "investigation": {
    "injected_evidence": [
      "the app runs as a single local CLI tool with no server component"
    ],
    "phase1": {
      "rule": "evidence_insufficient",
      "blocker_class": "facts_missing"
    },
    "phase2": {
      "acceptable_decisions": ["SELECT_OPTION", "SELECT_OPTION_WITH_CAUTION"],
      "acceptable_selections": ["sqlite"]
    }
  },
  "derived_from": null
}
```

runner(`run_fixed_state.py`)の2段階実行:

1. 位相1: `state` をそのまま実行 → `phase1` の期待値(`rule`・`blocker_class`)を機械判定
2. 位相2: `state` の `evidence` に `injected_evidence` を追記し、`revision {round:1, action:"investigation", summary:"injected by eval runner"}` を付けて実行 → `phase2` の期待値(decision・選択)を機械判定

実行記録は既存の jsonl と同じ形式に `phase`(1/2)フィールドを加えて記録する。3ケース × 3回 × 2位相 = Jev 18呼び出し(数分)。

集計は **loop_pass_rate** = 位相1・位相2とも合格だった実行 ÷ 実行数(ケース別・全体)。**baseline 比較の分母には入れない**(既存23ケースの指標とは独立に報告)。

`judging.py` の既存関数・定義は変更しない。位相判定のロジックは runner・集計側の新関数に置く。

### 6.2 既存ケースセットの再実行

- 23ケース + 5シナリオを無変更で再実行し、`evals/results/extension-info-gap-YYYY-MM-DD/` に記録(同日再実行時は `-2`)
- 3目標指標(Appropriate Ask Rate・evidence_removed・Unsafe Auto-selection Rate)を `baseline-2026-10-01/baseline.json` と比較する。`report_baseline.py` に `--compare-to <baseline.json>` を追加し差分表示
- 回帰監視(目標値ではなく確認項目):
  - reorder / detail_asymmetry / violating_candidate の pass が 6/6 を維持していること
  - completion_rate の低下が、本来情報不足のケース(info_missing・evidence_removed)に限定されていること
- full-flow は baseline と同じ制限付きツール構成のまま実行(外部調査は評価で行使しない)。この留保を SUMMARY に明記する
- full-flow の dependency シナリオ(info_missing)は、調査対象の事実が fixture 内に存在しない設計("Nobody has measured how large the weekly files get")なので、期待値 `ASK_USER` は変わらない。agent が調査→再実行→`investigation_exhausted`→問い直しの経路を辿ることを、回収した state(`revision` の有無)と agent 出力で記録し確認する(機械判定の対象外)

## 7. エラー処理・互換性

- 新質問は既存1リクエストに同梱。応答の欠落・不正・transport 障害は現行どおり `PROVIDER_UNAVAILABLE`。engine 内での再試行はしない(runner 側の backoff 再試行は現行仕様のまま)
- 出力は既存フィールド不変・追加のみ。`revision` なしの旧 state もそのまま通る
- Jev が新質問形式を受け付けるかは、実装最初の確認事項とする(`AUTARCH_EVAL_LIVE=1` の live テストで新質問を含むリクエストを検証)。受け付けない場合は質問形式を調整してから baseline 再実行に入る

## 8. テスト(TDD)

- `tests/test_decide.py` に追加(偽の SystemOne 応答で):
  - 新質問の parse 検証(欠落・範囲外・選択肢不一致 → `ProviderError`)
  - ゲート順序: 既存5ルールが変更なく発動すること、ゲートが human_preference の直後であること
  - 逃し弁: `blocker_confidence` 不足なら従来挙動にフォールバック
  - `revision` の検証(不在 OK・`round` は 1 のみ・`action` の列挙・`summary` 空拒否)
  - revision あり → `investigation_exhausted`、revision あり + 充分 → 通常解決
  - 新フラグ `--sufficiency` / `--blocker-confidence` の伝達
  - 出力・log record の新フィールド
- `tests/test_eval_runner.py` に追加:
  - loop ケースの schema 検証(必須キー・`phase2` の期待値形式)
  - 偽 decide.py スクリプトによる2段階実行(evidence 追記・revision 付与を含む state 生成の検証)
  - loop_pass_rate の計算
  - 既存の指標テストは無変更で緑のまま(定義不変の担保)
- live テストは `AUTARCH_EVAL_LIVE=1` / full-flow smoke は現行流儀のまま明示指定時のみ

## 9. 進め方

1. live テストで Jev が新質問形式(noul + 4選択肢 choice)を受け付けることを確認
2. `decide.py` の拡張を TDD で実装(§4)
3. `SKILL.md` の Step 11 拡張(§5)
4. loop ケース・runner・集計の拡張を TDD で実装(§6.1)
5. 既存23+5の再実行と比較レポート(§6.2)
6. 結果を確認し、STATE.md を更新

## 10. Dependencies

```text
Runtime: Python 3.10+ (stdlib only), TYPESAFE_API_KEY (Jev 実行時)
full-flow 実行時: claude CLI(headless)、agent 実行コスト
Development / test: pytest
```

SKILL 本体への依存追加はない。`decide.py`・`SKILL.md`・`evals/`・`tests/` のみ変更する。
