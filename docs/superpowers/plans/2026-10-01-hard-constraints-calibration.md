# 必須条件の採点前検査と閾値検証 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 根拠付き必須条件を採点前に検査し、未確認・違反候補の自動採用を防ぐ。独立した検証で合格した場合だけ閾値を更新する。

**Architecture:** decide.py に純粋な事前検査を追加し、適格候補のみ Jev へ渡す。agent は既存 revision を共有して一度調査する。評価は既存 baseline、新しい必須条件トラック、閾値検証を分ける。

**Tech Stack:** Python 3.10+ stdlib / pytest / Jev SystemOne / claude CLI（full-flow）

**Spec:** `docs/superpowers/specs/2026-10-01-hard-constraints-calibration-design.md`

## Global Constraints

- runtime の依存追加は不要とする。
- 既存 decision 値は増やさない。既存 `judging.py` の指標定義と23ケースは変更しない。
- 既存の `known_constraints` と文字列配列 `evidence` は維持する。
- 条件確認と根拠不足調査を合わせて一度までとする。既存 revision の制約を維持する。
- 元の state は変更しない。新しい情報にも秘密情報除外と再帰的伏せ字を適用する。
- review=0.60、min_gap=0.15、human_preference=0.70 は固定する。検証前の既定値変更は禁止。
- 採用条件を満たす閾値がなければ既定値を変更しない。
- SKILL.md と engine のユーザー向け文字列は既存に合わせて英語。日本語で作業報告する。
- 各コードタスクは失敗テスト → 最小実装 → テスト成功 → commit。全体検証は `python3 -m pytest`。

## Review Focus

1. source/fact が伏せ字だけになった根拠を確認済みとして使わない（Task 2）。
2. RFC 3339 風だが実在しない日付、タイムゾーンなし、null を拒否する（Task 1）。
3. 部分実行、同じ位相の重複、provider 障害で成功率が水増しされない（Task 5）。
4. 丸めで Score の首位が変わる境界でも再判定が一致する（Task 4）。
5. 閾値検証用ケースの結果を見て再調整しない。欠測と不完全な実行を合格にしない（Task 7）。

## ファイルの役割

| ファイル | 変更と役割 |
|---|---|
| skills/autarch/scripts/decide.py | schema、事前検査、出力、丸め前の信号、ゲート順序の選択 |
| skills/autarch/SKILL.md | 条件登録、根拠確認、調査・候補不足の分岐 |
| tests/test_decide.py | engine の契約と CLI の検証 |
| tests/test_skill_md.py | フローの必須記載 |
| evals/constraint_cases.py（新） | 独立トラックの schema・位相生成・判定 |
| evals/run_constraint_cases.py（新） | 既存 runner の呼び出しを再利用して実行・記録 |
| evals/calibrate_thresholds.py（新） | 丸め前信号の再判定、グリッド比較、採用判定 |
| evals/run_fixed_state.py | 信号取得の CLI 伝達と設定記録 |
| evals/cases_constraints/（新） | 必須条件の評価ケース |
| evals/cases_calibration/（新） | 凍結する検証用10ケース |
| tests/test_constraint_cases.py、tests/test_calibrate_thresholds.py（新） | 独立評価と閾値探索の検証 |
| evals/results/、STATE.md、README.md、README.ja.md | 実測結果、留保、利用方法 |

既存の大きい decide.py を全面分割しない。評価の新責務は専用ファイルへ分離する。

### Task 1: 構造化根拠と必須条件の入力契約

**Files:** Modify `skills/autarch/scripts/decide.py`（validate_state 周辺）、`tests/test_decide.py`。

**Interfaces:** `validate_constraint_fields(state: dict) -> list[str]` を追加し、既存 `validate_state(state) -> list[str]` から呼ぶ。

- [ ] **Step 1:** `TestValidateConstraints` を追加する。valid な2候補・1条件・verified 根拠を fixture にし、`validate_state(state) == []`、旧 state と空配列が有効であることを assert。null、非配列、非 object、重複 ID、列挙外、未参照根拠 ID、候補の過不足、evidence_ids の非配列・重複、空文字、根拠なし met/violated、inference のみの met が errors を返すことをパラメータ化する。日付 `2026-02-30T00:00:00Z`、timezone なし、数値日時を拒否し、`Z` と `+09:00` は受理する。
- [ ] **Step 2:** `python3 -m pytest tests/test_decide.py -k ValidateConstraints -v`。新契約が未実装で FAIL を確認。
- [ ] **Step 3:** 上記関数を実装。日時は RFC 3339 の形式検査と stdlib datetime の暦検証を組み合わせる。met/violated は verified を1件以上必要とし、unknown は空または既存参照を許す。型エラーを例外にせず errors に集める。
- [ ] **Step 4:** 同じ対象と `python3 -m pytest tests/test_decide.py -q` が PASS。
- [ ] **Step 5:** 対象2ファイルを commit: `feat: validate evidence-backed hard constraints`。

### Task 2: 候補の事前検査と main の接続

**Files:** Modify `skills/autarch/scripts/decide.py`（redact 後・main・ログ）、`tests/test_decide.py`。

**Interfaces:** `check_constraints(state: dict) -> tuple[dict | None, dict, dict | None]`。返り値は評価用 state、constraint_check、早期 resolution。legacy は元と等価なコピー、structured は適格候補に絞ったコピー。早期停止では評価用 state は None。constraint_check は `mode`、`eligible_option_ids`、`excluded_options`（option_id / constraint_ids / evidence_ids）、`unknown_assessments`（option_id / constraint_id）。不正入力時は constraint_check=None。

- [ ] **Step 1:** `TestConstraintPreflight` で入力不変を assert。3候補の1候補を除外した payload は2候補のみで、Choice と全 Score に除外 ID がないことを assert。全違反と1候補残存は `INSUFFICIENT_OPTIONS / constraint_candidates_insufficient`、unknown は `ASK_USER / constraint_unverified`、revision ありは `investigation_exhausted`。違反＋unknown の同じ候補では違反優先、他候補の unknown は候補不足より先に停止。main の send_request を spy にし全早期停止で call_count==0。除外 ID を返す偽 Jev 応答は PROVIDER_UNAVAILABLE。
- [ ] **Step 2:** `python3 -m pytest tests/test_decide.py -k 'ConstraintPreflight' -v` が FAIL。
- [ ] **Step 3:** check_constraints を実装して main に接続。伏せ字後は schema を再検査し、ID・参照の一致を元 state と照合する。met/violated が依拠する verified 根拠の fact/source が伏せ字のみなら invalid_state とする。Task 1 の契約は原入力に適用し、フィルタ後は候補に合わせ assessments を絞る。
- [ ] **Step 4:** `TestConstraintRedaction` を追加し、ID が秘密キー扱いされる候補、参照が変わる秘密風 ID、source/fact が完全伏せ字になるケースは非呼び出し停止、文中の秘密は送信・ログで伏せ字となることを確認する。出力・build_log_record に constraint_check を加え、legacy・provider 障害・invalid_state も形を揃える。`python3 -m pytest tests/test_decide.py -q` が PASS。
- [ ] **Step 5:** 対象2ファイルを commit: `feat: filter candidates before Jev evaluation`。

### Task 3: agent の条件確認と一度の調査

**Files:** Modify `skills/autarch/SKILL.md`、`tests/test_skill_md.py`、README.md、README.ja.md。

**Interfaces:** engine の constraint_unverified / investigation_exhausted / constraint_candidates_insufficient と constraint_check を消費する。13ステップ構成を維持する。

- [ ] **Step 1:** `test_hard_constraint_flow` に、hard_constraints・evidence_records・verified/inference・constraint_unverified・候補不足のルール名と、revision 共有の説明が記載される assertions を追加。
- [ ] **Step 2:** `python3 -m pytest tests/test_skill_md.py -v` が新記載不足で FAIL。
- [ ] **Step 3:** state 作成時に厳守条件と好みを分け、明示された必須条件を全候補について登録する指示を追加。変動する事実は判断時に再確認。Step 11 は engine の新ルールで一度調査・再実行、既に revision があれば問い直す。候補不足分岐は候補追加または条件確認、条件を勝手に緩めず自動反復しない。README に最小入力例と legacy の保証範囲を記載。
- [ ] **Step 4:** 同じテストが PASS。新しい英語指示を仕様と突き合わせ、unknown を met として扱う抜け道がないことを通読。
- [ ] **Step 5:** 対象4ファイルを commit: `docs: teach evidence-backed constraint checks and investigation`。

### Task 4: 丸め前の評価信号と同一経路での再判定

**Files:** Modify decide.py、evals/run_fixed_state.py、tests/test_decide.py、tests/test_run_fixed_state.py。Create evals/calibrate_thresholds.py、tests/test_calibrate_thresholds.py。

**Interfaces:** `resolve(state, parsed, thresholds, *, gate_order="human_first") -> dict` を後方互換で拡張。CLI `--gate-order human_first|evidence_first` と `--capture-evaluation`（既定 false）。`evaluation_signals` は成功時の blocker_class/confidence、`evaluation_snapshot` は capture 時のみ `{schema_version:1, parsed:dict, thresholds:dict, gate_order:str, evaluated_option_ids:list[str]}`。capture なし、事前停止、provider 障害の snapshot は null。`replay_resolution(state: dict, snapshot: dict, thresholds: dict, gate_order: str) -> dict` は engine の check_constraints で評価用 state を再生成し、evaluated_option_ids と一致を検査してから resolve を利用する。

- [ ] **Step 1:** ゲート不発でも evaluation_signals が保存され、snapshot の scores が丸められないテストを書く。human と evidence の両ゲートが成立する入力で、順序ごとの rule が異なり、既定は現行動作と一致することを assert。`test_replay_preserves_close_score_winner` は composite が表示上同点になる2候補で直接 resolve と replay の decision/rule/selected_option が一致することを assert。
- [ ] **Step 2:** `python3 -m pytest tests/test_decide.py tests/test_calibrate_thresholds.py tests/test_run_fixed_state.py -q` が新機能で FAIL。
- [ ] **Step 3:** インターフェースを実装。snapshot は parse_answers の検証済み値だけを保存し、未加工応答を保存しない。通常ログは evaluation_signals のみ追加し snapshot 本体は複製しない。runner は capture と順序を CLI で渡して environment.json に記録する。
- [ ] **Step 4:** 非有限数、信号欠落、未知 schema_version、候補 ID 不一致を replay が ValueError で拒否するテストを追加。対象テストと既存 test_judging.py が PASS。
- [ ] **Step 5:** 対象ファイルを commit: `feat: capture validated evaluation signals for policy replay`。

### Task 5: 必須条件の独立評価トラック

**Files:** Create evals/constraint_cases.py、evals/run_constraint_cases.py、tests/test_constraint_cases.py、evals/cases_constraints/*.json。

**Interfaces:** `load_constraint_cases(path: Path) -> list[dict]`、`constraint_phase2_state(case: dict) -> dict`、`constraint_verdict(case: dict, records: list[dict]) -> str`（pass / fail / unavailable / incomplete）、`constraint_metrics(cases: list[dict], runs: list[dict]) -> dict`。runner は既存 run_fixed_state.run_with_retry を再利用。記録は case_kind="constraints"、phase=1|2、case_id、run_index。既存 JSONL と別の constraint_runs.jsonl を使う。

- [ ] **Step 1:** schema fixture に id/topic/state/phases を持たせる。各 phase の期待値は decision、rule、eligible_option_ids、excluded_option_ids、unknown pairs、selected_option（null 可）。phase2 は置換する evidence_records/hard_constraints と既存制約どおりの revision を指定。状態が intentionally invalid のケースには expected_validation_errors=true を必須とし、通常ケースは validate_state()==[]。単一・2位相の pass/fail、欠落=incomplete、provider 障害=unavailable、重複位相=ValueError、未知ケース=ValueError を assert。
- [ ] **Step 2:** `python3 -m pytest tests/test_constraint_cases.py -v` が FAIL。
- [ ] **Step 3:** schema、非破壊位相生成、判定、CLI `--cases-dir --out-dir --runs --decide-script --dry-run` と既存 runner と同じ閾値6種・`--gate-order`・`--model` を実装。相反する期待値を拒否。summary は全実行の pass/fail/unavailable/incomplete 件数と、評価可能な実行の pass_rate を併記する。欠測を pass と扱わない。空ディレクトリは exit 2。
- [ ] **Step 4:** db_eligible（1違反・2適格）、env_single、env_none、env_unknown_resolved、env_unknown_exhausted、inference_invalid、cost_verified の7ケースを作る。偽 decide と spy で事前停止時の非呼び出しと位相生成を検証。dry-run と対象テストが PASS。
- [ ] **Step 5:** 新ファイルを commit: `test: add an independent hard constraint evaluation track`。

### Task 6: 閾値グリッドの比較と採用条件

**Files:** Modify evals/calibrate_thresholds.py、tests/test_calibrate_thresholds.py。

**Interfaces:** `candidate_policies() -> list[dict]`（90設定）、`rank_policies(cases: list[dict], runs: list[dict]) -> list[dict]`、`adoption_verdict(reference: dict, candidate: dict, validation: dict) -> dict`（accepted:bool / reasons:list[str]）。CLI に `describe`（--runs-file / --out-file）、`search`（--cases-dir / --loop-cases-dir / --runs-file / --out-dir）、`validate`（--policy-file / --manifest / --runs-file / --out-dir）サブコマンドを設ける。search は ranking.json、selected-policy.json（設定・学習用採用判定・ケース hash・manifest hash）を出力する。manifest hash は search の追加引数 --manifest で登録する。validate は adoption.json を出力し、不成立は exit 1、入力不正は exit 2。

- [ ] **Step 1:** グリッド=5×3×3×2、固定値と順序、順位の辞書式規則を assert。unsafe、根拠不足の見逃し、loop 位相2の失敗、明確ケースの不要質問、変更数、現行順序、現行値からの絶対差の合計、グリッド記載順の順に比較する。既存記録の欠けた blocker は unknown と表示し、完全 replay の結果を作らない。
- [ ] **Step 2:** `python3 -m pytest tests/test_calibrate_thresholds.py -v` が FAIL。
- [ ] **Step 3:** describe は状況・位相別分布と欠測を出力。search は Task 4 の snapshot と replay を使う。凍結ポリシーには学習用の現行・候補の件数集計と採用判定を保存し、validate がこの比較結果と検証用結果を合わせて採用条件を検査する。ASK_USER 期待の状況は info_missing/preference_needed/evidence_removed、loop は既存 phase 期待値を使う。閾値より低い confidence による WITH_CAUTION を完了とする既存指標定義を守る。採用条件は仕様 §5 をそのまま実装し、3有効実行/ケースを要求する。
- [ ] **Step 4:** 同点規則、境界 `<` と `>=`、unsafe 増加、clear 回帰、db loop 退行、検証用14/15、provider 障害、重複 run_index、候補設定不一致、検証用不足で rejected を assert。対象テストが PASS。
- [ ] **Step 5:** 対象ファイルを commit: `feat: compare threshold policies with explicit adoption gates`。

### Task 7: 検証用ケースを凍結して実測する

**Files:** Create evals/cases_calibration/*.json、evals/cases_calibration/metadata/manifest.json、evals/results/hard-constraints-calibration-2026-10-01*/。Modify tests/test_calibrate_thresholds.py、STATE.md。

**Interfaces:** manifest は10ケースの ID と SHA-256、題材、対になる ID、凍結日時を保存。case ファイルは既存 validate_case の形式を使い、manifest.json は loader から除外する（metadata/ 配下なので case loader の対象にならない）。validate は selected-policy.json と manifest hash を要求する。

- [ ] **Step 1:** manifest 改変・ケース改変・異なる selected policy・3件未満の有効実行を validate が拒否するテストを追加。`python3 -m pytest tests/test_calibrate_thresholds.py -v` の FAIL を確認して実装、PASS を確認。
- [ ] **Step 2:** 5題材の別の決め手を作る。database=複数ホストの同時書込み、authentication=即時失効要件、test_framework=既存ブラウザテストとの連携、dependency=実行環境のバイナリ導入可否、deployment=永続ディスクの必要性。それぞれ決め手欠落の ASK_USER と確認済みの許容選択の対にし、同じ既存条件と矛盾しないことを通読する。モデル実行前に10ケースと manifest を commit: `test: freeze held-out threshold validation pairs`。
- [ ] **Step 3:** `python3 evals/calibrate_thresholds.py describe --runs-file evals/results/extension-info-gap-2026-10-01/fixed_state_runs.jsonl --out-file <root/distribution.json>` で第1拡張記録の分布を保存。旧記録の欠測を記録する。
- [ ] **Step 4:** `python3 -m pytest` が PASS してから、B の通常・loop 生信号を取得する。

```bash
python3 evals/run_fixed_state.py --out-dir evals/results/hard-constraints-calibration-2026-10-01/training --loop-cases-dir evals/cases_loop --capture-evaluation --runs 3
python3 evals/run_constraint_cases.py --cases-dir evals/cases_constraints --out-dir evals/results/hard-constraints-calibration-2026-10-01/constraints --runs 3
```

同名ディレクトリが存在したら既存を上書きせず末尾 -2 以降を選び、以後すべてのコマンドで同じルートを使う。provider 障害は既存 runner の再試行上限を維持し、不足した有効実行だけ記録を分けて追加する。

- [ ] **Step 5:** `python3 evals/calibrate_thresholds.py search --manifest evals/cases_calibration/metadata/manifest.json --cases-dir evals/cases --loop-cases-dir evals/cases_loop --runs-file <training/fixed_state_runs.jsonl> --out-dir <root/search>` で候補を選ぶ。候補設定と manifest hash を selected-policy.json に凍結し commit。学習用の採用条件不成立なら rejected を記録し、検証用へ進まず現行値を維持する。
- [ ] **Step 6:** 候補が成立した場合、選択値を CLI の明示フラグとして渡し、検証用10ケースを `run_fixed_state.py --cases-dir evals/cases_calibration --allow-partial-set --capture-evaluation --runs 3 --out-dir <root/validation>` で実行。`python3 evals/calibrate_thresholds.py validate --policy-file <selected-policy.json> --manifest <metadata/manifest.json> --runs-file <validation/fixed_state_runs.jsonl> --out-dir <root/validation-report>` が accepted=true の場合だけ Task 8 の既定値更新を許す。結果を見た調整・再探索は禁止。
- [ ] **Step 7:** 分布、ケース・設定の凍結、判定結果、費用・モデル名・日時・欠測を notes.md に記録して commit: `test: record constraint and calibration evaluation results`。

### Task 8: 採用判定に従う更新と最終評価

**Files:** Modify decide.py、run_fixed_state.py、tests/test_decide.py、README.md、README.ja.md（採用時のみ）。Create 最終評価記録。Modify STATE.md。

**Interfaces:** Task 7 の accepted 判定。reject なら既定値変更なし。採用する順序と値は frozen policy の値をそのまま使う。

- [ ] **Step 1:** accepted の場合だけ既定値テストを frozen policy に合わせて先に変更し、対象テストの FAIL を確認。engine・runner の既定値と記載を更新して PASS を確認。reject の場合はこの更新を省略して理由を notes に残す。
- [ ] **Step 2:** `python3 -m pytest` が全て PASS（live skip は件数を記録）。`git diff --check` が空。独立レビューの指摘は再現する失敗テストを経て修正し、変更に応じた再検証を行う。
- [ ] **Step 3:** 最終設定で既存23ケース＋3 loop を別ディレクトリ `<root/final>` へ各3回再実行。新トラックも Task 5 runner のフラグで同じ設定を渡して再実行する。
- [ ] **Step 4:** `python3 evals/run_full_flow.py --out-dir <root/final> --agent-model sonnet` を実行。5シナリオについて構造化条件の取りこぼし、根拠、revision、rule と判断結果を手動確認し notes に記録する。
- [ ] **Step 5:** `python3 evals/report_baseline.py --baseline-dir <root/final> --loop-cases-dir evals/cases_loop --compare-to evals/results/extension-info-gap-2026-10-01/baseline.json` で比較する。新トラックの結果は独立 summary としてリンクし、既存分母には混ぜない。閾値選択時の合格と最終再実行での回帰を区別し、後者で採用条件を破れば既定値を戻して不採用とする。戻した場合は最終設定の評価を再実行し、新候補の探索はしない。
- [ ] **Step 6:** STATE.md に実装・評価・採用設定または不採用理由、残るルール順序/full-flow 課題を記録。対象だけ stage して commit: `feat: finalize evidence-backed constraint checks and calibration outcome`。完了後に finishing-a-development-branch の手順で統合方法を扱う。

## 自己レビューと引き継ぎ

仕様 §1–4 は Task 1–3、§5 は Task 4・6–8、§6 は Task 5・7–8、§7 は全体と Task 8 に対応する。生信号の保存は表示値の再利用を避け、検証用はモデル実行前に凍結する。旧ケース・指標の変更を禁止し、評価トラックを独立させた。Review Focus の5件は担当タスクのテストに割り当てた。

推奨実行方法は Subagent-driven。候補除外、出力契約、再判定、評価の境界に誤りがあると品質判定自体を誤るため、各タスクで独立レビューを挟む。実装開始にはこの計画のレビューと実行方法の選択が必要。
