# Autarch 現行版 baseline

## 実行環境

| 項目 | 値 |
|---|---|
| Jev model | jev-latest |
| 閾値 | auto_select=0.85, review=0.6, min_gap=0.15, human_preference=0.7 |
| 1ケースあたり実行回数 | 3 |
| Jev 実行回数 | 87 |
| 実行期間 | 2026-10-01T06:48:42Z 〜 2026-10-01T06:51:01Z |
| full-flow agent model | sonnet |

## 固定 state トラック

judged 69 実行(unavailable 0 件・invalid 0 件は分母から除外)。

| 指標 | 全体 | 平均(run別) | 範囲(run別) |
|---|---|---|---|
| Decision Completion Rate | 66.67% | 66.67% | 65.22%–69.57% |
| Correct Selection Rate | 84.78% | 84.86% | 81.25%–86.67% |
| Unsafe Auto-selection Rate | 10.14% | 10.15% | 8.70%–13.04% |
| Appropriate Ask Rate | 76.67% | 76.67% | 70.00%–80.00% |

### 撹乱安定性

| perturbation | pass | fail | inconclusive | pass率 |
|---|---|---|---|---|
| detail_asymmetry | 6 | 0 | 0 | 100.00% |
| evidence_removed | 0 | 6 | 0 | 0.00% |
| reorder | 6 | 0 | 0 | 100.00% |
| violating_candidate | 6 | 0 | 0 | 100.00% |

### ケース別結果

| case | run | classification | selected | confidence |
|---|---|---|---|---|
| auth_constraint_clear | 1 | completed | session_cookie | 1.0 |
| auth_constraint_clear | 2 | completed | session_cookie | 1.0 |
| auth_constraint_clear | 3 | completed | session_cookie | 1.0 |
| auth_detail_asymmetry | 1 | completed | session_cookie | 1.0 |
| auth_detail_asymmetry | 2 | completed | session_cookie | 1.0 |
| auth_detail_asymmetry | 3 | completed | session_cookie | 1.0 |
| auth_evidence_removed | 1 | completed | session_cookie | 1.0 |
| auth_evidence_removed | 2 | completed | session_cookie | 1.0 |
| auth_evidence_removed | 3 | completed | session_cookie | 1.0 |
| auth_info_missing | 1 | asked | None | 0.45 |
| auth_info_missing | 2 | asked | None | 0.43 |
| auth_info_missing | 3 | asked | None | 0.39 |
| auth_preference_needed | 1 | completed | jwt_stateless | 1.0 |
| auth_preference_needed | 2 | completed | jwt_stateless | 1.0 |
| auth_preference_needed | 3 | completed | jwt_stateless | 1.0 |
| auth_reorder | 1 | completed | session_cookie | 1.0 |
| auth_reorder | 2 | completed | session_cookie | 1.0 |
| auth_reorder | 3 | completed | session_cookie | 1.0 |
| auth_violating_candidate | 1 | completed | session_cookie | 1.0 |
| auth_violating_candidate | 2 | completed | session_cookie | 1.0 |
| auth_violating_candidate | 3 | completed | session_cookie | 1.0 |
| db_constraint_clear | 1 | completed | sqlite | 1.0 |
| db_constraint_clear | 2 | completed | sqlite | 1.0 |
| db_constraint_clear | 3 | completed | sqlite | 1.0 |
| db_detail_asymmetry | 1 | completed | sqlite | 1.0 |
| db_detail_asymmetry | 2 | completed | sqlite | 1.0 |
| db_detail_asymmetry | 3 | completed | sqlite | 0.99 |
| db_evidence_removed | 1 | completed | sqlite | 1.0 |
| db_evidence_removed | 2 | completed | sqlite | 0.99 |
| db_evidence_removed | 3 | completed | sqlite | 1.0 |
| db_info_missing | 1 | asked | None | 0.98 |
| db_info_missing | 2 | asked | None | 0.98 |
| db_info_missing | 3 | asked | None | 0.98 |
| db_preference_needed | 1 | asked | None | 0.11 |
| db_preference_needed | 2 | asked | None | 0.11 |
| db_preference_needed | 3 | asked | None | 0.12 |
| db_reorder | 1 | completed | sqlite | 0.99 |
| db_reorder | 2 | completed | sqlite | 0.99 |
| db_reorder | 3 | completed | sqlite | 0.99 |
| db_violating_candidate | 1 | completed | sqlite | 1.0 |
| db_violating_candidate | 2 | completed | sqlite | 1.0 |
| db_violating_candidate | 3 | completed | sqlite | 1.0 |
| dep_constraint_clear | 1 | completed | stdlib_only | 1.0 |
| dep_constraint_clear | 2 | completed | stdlib_only | 1.0 |
| dep_constraint_clear | 3 | completed | stdlib_only | 1.0 |
| dep_info_missing | 1 | asked | None | 0.83 |
| dep_info_missing | 2 | asked | None | 0.86 |
| dep_info_missing | 3 | asked | None | 0.79 |
| dep_preference_needed | 1 | asked | None | 0.5 |
| dep_preference_needed | 2 | asked | None | 0.58 |
| dep_preference_needed | 3 | asked | None | 0.53 |
| deploy_constraint_clear | 1 | completed | static_host | 1.0 |
| deploy_constraint_clear | 2 | completed | static_host | 1.0 |
| deploy_constraint_clear | 3 | completed | static_host | 1.0 |
| deploy_info_missing | 1 | completed | paas_container | 1.0 |
| deploy_info_missing | 2 | completed | paas_container | 1.0 |
| deploy_info_missing | 3 | completed | paas_container | 1.0 |
| deploy_preference_needed | 1 | asked | None | 0.75 |
| deploy_preference_needed | 2 | asked | None | 0.75 |
| deploy_preference_needed | 3 | completed | paas_container | 0.71 |
| test_framework_constraint_clear | 1 | completed | stay_pytest | 1.0 |
| test_framework_constraint_clear | 2 | completed | stay_pytest | 1.0 |
| test_framework_constraint_clear | 3 | completed | stay_pytest | 1.0 |
| test_framework_info_missing | 1 | asked | None | 0.31 |
| test_framework_info_missing | 2 | asked | None | 0.28 |
| test_framework_info_missing | 3 | asked | None | 0.33 |
| test_framework_preference_needed | 1 | asked | None | 0.06 |
| test_framework_preference_needed | 2 | asked | None | 0.05 |
| test_framework_preference_needed | 3 | asked | None | 0.08 |

## loop ケース(2段階)

pass 3 / fail 6(unavailable 0 は分母から除外)。

| case | run | phase1 | phase2 | 判定 |
|---|---|---|---|---|
| auth_loop_resolvable | 1 | ASK_USER/human_preference | SELECT_OPTION/confidence | fail |
| auth_loop_resolvable | 2 | ASK_USER/human_preference | SELECT_OPTION/confidence | fail |
| auth_loop_resolvable | 3 | ASK_USER/human_preference | SELECT_OPTION/confidence | fail |
| db_loop_resolvable | 1 | ASK_USER/evidence_insufficient | SELECT_OPTION/confidence | pass |
| db_loop_resolvable | 2 | ASK_USER/evidence_insufficient | SELECT_OPTION/confidence | pass |
| db_loop_resolvable | 3 | ASK_USER/evidence_insufficient | SELECT_OPTION/confidence | pass |
| deploy_loop_resolvable | 1 | SELECT_OPTION/confidence | SELECT_OPTION/confidence | fail |
| deploy_loop_resolvable | 2 | SELECT_OPTION/confidence | SELECT_OPTION/confidence | fail |
| deploy_loop_resolvable | 3 | SELECT_OPTION/confidence | SELECT_OPTION/confidence | fail |

## full-flow トラック

| scenario | coverage | forbidden回避 | 判定妥当 | state妥当 | 選択 |
|---|---|---|---|---|---|
| authentication | True | True | False | True | None |
| database | False | True | False | True | None |
| dependency | True | True | True | True | None |
| deployment | True | True | False | True | None |
| test_framework | True | True | False | True | None |

coverage率 80.00% / forbidden回避率 100.00% / 判定妥当率 20.00% / state妥当率 100.00%

## baseline との比較

| 指標 | baseline | 今回 | 差分 |
|---|---|---|---|
| Decision Completion Rate | 76.81% | 66.67% | -10.14% |
| Correct Selection Rate | 73.58% | 84.78% | 11.20% |
| Unsafe Auto-selection Rate | 20.29% | 10.14% | -10.15% |
| Appropriate Ask Rate | 53.33% | 76.67% | 23.34% |
| perturbation pass rate: detail_asymmetry | 100.00% | 100.00% | 0.00% |
| perturbation pass rate: evidence_removed | 0.00% | 0.00% | 0.00% |
| perturbation pass rate: reorder | 100.00% | 100.00% | 0.00% |
| perturbation pass rate: violating_candidate | 100.00% | 100.00% | 0.00% |

## 留保

- `evidence_removed` の合格基準(ASK_USER、または正解圏内かつ confidence < auto_select)は暫定。本 baseline の confidence 分布を見て見直す。
- unavailable / invalid の実行は指標の分母から除外している。
- decide.py の個別実行ログは `~/.autarch/decisions.jsonl` にも記録される。
# extension-info-gap-2026-10-01 留保と経緯

- 拡張内容: 情報不足の分類と一度の追加調査(Jev 新質問2種 + 根拠充足性ゲート + state revision)。
  spec は `docs/superpowers/specs/2026-10-01-info-gap-investigation-design.md`
- 実行環境は baseline-2026-10-01 と同じ Jev model(jev-latest)・agent model(sonnet)。
  追加された閾値 `sufficiency=0.60` / `blocker_confidence=0.50` は environment.json 参照
- **completion_rate 低下(76.81% → 66.67%)の内訳**: completed→asked に転じた7実行は
  すべて以前 Unsafe だった自動選択(db_info_missing×3・dep_info_missing×3・
  deploy_preference_needed×1)。いずれも ASK_USER が期待されるケースで、
  クリアケース(constraint_clear 系)の完了低下はない
- **evidence_removed 0/6 のまま**: ゲートは sufficiency < 0.60 で発動するが、
  evidence_removed での Jev の sufficiency は 0.80〜0.84 に下がるだけで閾値に届かない。
  分布は生記録に残っているので、閾値見直し(例: 0.85 付近)は次の判断材料が揃った
- **loop_pass_rate 33.3%(3/9)**: db_loop_resolvable は3回とも位相1
  `evidence_insufficient`(facts_missing)→ 位相2 SELECT_OPTION(sqlite)で完全パス。
  auth_loop_resolvable は位相1が `human_preference` ルールで先に発火(ゲート未到達)。
  deploy_loop_resolvable は state から free-tier 制約を残したため薄さ不足で位相1から選択。
  → auth/deploy はケース設計の修正案件、ループ機構自体は db で検証済み
- **full-flow は baseline と同水準**(decision_ok 1/5・coverage 0.8・forbidden 1.0・
  state_valid 1.0)。agent が構築した state は `human_preference` noul が 0.70 を超えて
  ゲート前に ASK_USER になる傾向があり、今回の5シナリオでは `evidence_insufficient`
  が一度も返らず調査ループ(Step 11 の再実行)は不発だった(state に revision なし)。
  固定 state トラックの改善(Ask +23.3pt・Unsafe −10.1pt)と合わせると、
  残る弱点は engine のルール順序(human_preference がゲートに先行)と
  agent の state 構築品質に移った
- full-flow の実行環境は baseline と同じ制限付きツール構成のため、
  SKILL.md の外部ドキュメント調査は今回の評価では行使していない
- decide.py の個別実行ログは `~/.autarch/decisions.jsonl` にも追記されている
