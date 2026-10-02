# 調査と意向質問の判別強化 実装設計

**日付:** 2026-10-02
**ステータス:** Draft(ユーザーレビュー待ち)
**関連文書:** `STATE.md`、`docs/superpowers/specs/2026-10-01-info-gap-investigation-design.md`(第1拡張)、`docs/superpowers/specs/2026-10-01-hard-constraints-calibration-design.md`(必須条件と閾値検証)、`evals/results/hard-constraints-calibration-2026-10-01/final/notes.md`(最終評価の留保)

---

## 1. 目的と範囲

**「分からないことは agent が自分で調べ、ユーザーの意向が必要なことだけを質問する」** という動きを確実にする。第1拡張と必須条件拡張の後も、この判別が両方向で失敗していることが最終評価で観測されている。

| 失敗 | 観測 | 直接原因 |
|---|---|---|
| 調査が不発 | deployment full-flow: sufficiency .54 でも blocker_confidence .22 < .50 でゲート不発 → 誤自動採用(confidence 1.0)。database full-flow も .44/.44 で不発 | ゲート条件が「sufficiency 低 かつ blocker_confidence 高」の双方を要求 |
| 調査より意向質問が先行 | auth_loop 0/3: `human_preference` が先発し `evidence_insufficient` に届かない | `resolve()` の gate_order=human_first で human ゲートが先に切る |
| 意向確認が必要なのに自動採用 | deploy_preference_needed run2: `ASK_USER/human_preference` から `SELECT_OPTION_WITH_CAUTION` へ回帰 | Jev シグナルの揺れ + 判別構造 |
| agent 構築ミス | assessments を配列で書いて invalid_state(database・test_framework の2件) | SKILL.md の schema 記述が示例に依存 |

共通の構造問題は、**「調査で解決できるか / 意向依存か」の判別を、`human_preference` と `sufficiency × blocker_confidence` という相関の高い2つの確率的シグナルの閾値組み合わせで行っている**点にある。本設計は判別軸を Jev への質問に直接組み込み、ゲート構造を再設計する。

成功基準は**既存評価での改善**(既存ケース・既存指標での失敗観測の減少)。対象の数値目標は次のとおり。

| 指標 | final(2026-10-01)時点 |
|---|---|
| auth_loop / deploy_loop pass | 0/3・0/3(db は 3/3) |
| Unsafe Auto-selection Rate(固定 state 69回) | 8/69 |
| full-flow decision_ok(評価可能3件) | 2/3(deployment が不成立) |

対象外(今回やらないこと):

- 閾値の数値変更。auto_select .85・review .60・min_gap .15・human_preference .70・sufficiency .60・blocker_confidence .50 は**固定**とし、構造(どのシグナルの組み合わせで発火・判別するか)のみ変える
- `blocker_class` の分類名変更。`facts_missing` 等の語彙は case_schema・loop 期待値・テスト群が依存するため**不変**。定義文のみ変更する
- `rule` / `decision` の出力語彙変更、`judging.py` の指標定義変更
- revision の1回制限の変更、調査の時間・費用上限の追加
- agent の調査品質(出典の正確性・根拠の証明範囲)の機械的保証。SKILL.md 指示の改善は行うが、保証範囲は既存どおり
- structured 空配列での unknown 発生経路の実測確認(STATE.md の別課題として留保)

## 2. 決定経緯

| 論点 | 決定 | 理由 |
|---|---|---|
| アプローチ | Jev 質問設計の変更 + ゲート構造再設計(両方) | オーナー選択。判別軸を直接質問できシグナルの質が上がる見込み。構造変更のみでは blocker_class の分類精度に依存したまま、質問変更のみでは deployment 型(低 blocker_confidence)のゲート不発が残るため、両方が必要 |
| 閾値 | 数値固定・構造のみ | オーナー決定。前回の「閾値は既定値維持」決定を踏襲し、captured signals による構造検証も可能にする |
| 成功基準 | 既存評価での改善 | オーナー決定。新しい指標は追加しない |
| 低 blocker_confidence 時の既定 | 調査側(`facts_missing` 扱い) | 「分からないことは調べる」に合致。誤っても調査1回で `investigation_exhausted` → 質問へ流れるため安全 |
| `--gate-order` フラグ | 廃止 | 判別を blocker_class が担い、human_first/evidence_first の区別が意味を失う |
| `requires_human_preference` の文言 | 「調査では取得できない」を明示 | 現行文言は「意向に依存するか」のみで、調査可能性の区別がなく auth_loop 型の広すぎる意向判定を誘発しやすい |

採用しなかった案: エンジン構造のみの変更(A)は既存シグナルで検証できるが、blocker_class の分類精度が現状のまま残る。agent 指示のみの変更(C)は固定 state 評価(auth_loop)が原理的に動かない。いずれも部分的に本設計へ取り込んだ。

## 3. Jev 質問設計の変更(`decide.py`)

判別軸「**調査で取得できるか / ユーザーにしか分からないか**」を質問に直接組み込む。分類名・質問キー・protocol 型(noul/choice/score)はすべて不変。

**`NOUL_INSTRUCTIONS`(`requires_human_preference`)の変更:**

```text
現行: Does resolving this decision require the user's personal preference,
      business intent, subjective taste, or value judgment?
新:   Does resolving this decision depend on the user's own preference,
      plans, or intent — something the agent cannot obtain by investigating
      sources?
```

**`BLOCKER_DESCRIPTIONS` の変更**(`material_bias`・`balanced_tie` は現行維持):

| 分類 | 新しい定義文 |
|---|---|
| `facts_missing` | A fact needed to compare the alternatives is missing, and the agent can obtain it by investigating sources (repository, documentation, web search) |
| `user_preference_unknown` | What is missing is the user's own preference, plan, or intent; no investigation can supply it |

**`BLOCKER_INSTRUCTIONS`・`SUFFICIENCY_INSTRUCTIONS`・`CHOICE_INSTRUCTIONS`** は現行維持。`parse_answers` の検証構造も不変(blocker の choice・probabilities・整合性検査はそのまま)。

## 4. ゲート構造(`resolve()`)の再設計

```text
0.   provider error                     → PROVIDER_UNAVAILABLE       (現行維持)
0.5  structured 条件 preflight          → 除外 / constraint_unverified(現行維持・別経路)
1.   sufficiency < 0.60 → ASK_USER 系へ発火(blocker_confidence の AND を撤廃)
     ├─ blocker_confidence ≥ 0.50 のときは blocker_class で行き先を判別:
     │    facts_missing / material_bias        → evidence_insufficient(調査・修復)
     │                                          (revision ありなら investigation_exhausted)
     │    user_preference_unknown / balanced_tie → human_preference(意向質問)
     └─ blocker_confidence < 0.50 のときは調査側へ倒す:
          evidence_insufficient(revision ありなら investigation_exhausted)
2.   sufficiency ≥ 0.60 かつ human_preference ≥ 0.70 → human_preference(意向質問)
3.   choice/score 一致性 → probability_gap → confidence bands        (現行維持)
```

- `blocker_confidence` はゲートの発火条件から外れ、行き先判別の信頼性判定のみに使う
- ゲート発火時は rule にかかわらず `blocker_class` と `blocker_confidence` を resolution に出力する(観測性向上。語彙互換に影響しない)
- `gate_order` 引数・`--gate-order` CLI フラグ・`GATE_ORDERS` 定数を廃止する
- 期待効果: auth_loop(hp 高 + suff 低 + facts_missing)→ 調査が先。deployment(suff .54)→ 必ず発火し調査へ。deploy_preference_needed(suff 十分 + hp 高)→ 意向質問を維持

## 5. SKILL.md の変更

- **Step 4(証拠収集)に調査前置を明示**: state を書く前に「比較に必要で、リポジトリ・ドキュメント・web 検索で取得できる事実」は先に調査してから state に載せる。エンジンに入ってからの調査し直しを減らし、state 構築時の根拠不足(database・deployment 型)を予防する
- **調査と質問の判別ミラーを明記**: ユーザー自身の好み・計画・意向は調査対象から除外し、質問として返す。エンジン側の判別軸と同じ言葉で指示する
- **Step 11 分岐の整理**: rule ベースの分岐語彙は現行維持。blocker_class と rule の対応を新構造(発火後の行き先)に合わせて整理する
- **Step 6 に `assessments` のオブジェクト形式 schema 例を明示**: `"assessments": {"<option_id>": {"status": ..., "evidence_ids": [...]}}`。配列ミス(full-flow で2件の invalid_state)の予防

## 6. 評価

1. **offline replay(構造の健全性確認)**: training/validation の snapshots(parsed 全体を保持)には新 `resolve()` を完全適用し、unsafe・completion が構造変更だけで悪化しないことを確認する。final 生記録は `evaluation_snapshot` が null のため、保存済み主要シグナル(human_preference_probability・evidence_sufficiency・blocker 信号)による発火ゲートの再判定に限る。文言変更後のシグナルではないため、効果測定ではなく健全性チェックに限る
2. **deploy_loop の state 修正**: phase1 が `SELECT_OPTION` にならないよう evidence を絞り、sufficiency < 0.60 と `facts_missing` を誘導する状態にする(STATE.md 論点3)。auth_loop は state を変えず、構造変更の効果を純粋に観察する
3. **live 再実行**: 旧23ケース×3回 + loop 3ケース×3回(9組18位相)+ full-flow 5シナリオ。新実装で実行し、別ディレクトリに保存して final と比較する。新文言でのシグナル分布(human_preference・sufficiency・blocker_class・blocker_confidence)も記録する
4. **judging.py の指標定義は不変**。ケース期待値も分類名維持でそのまま使う
5. evals 各 runner(`run_fixed_state.py`・`run_constraint_cases.py`・`calibrate_thresholds.py` 等)から `--gate-order` を削除する

## 7. テスト

- `test_decide.py`: resolve 系を新ゲート構造へ更新。新規に (a) sufficiency 単独トリガー、(b) blocker_class による行き先判別、(c) 低 blocker_confidence → 調査側フォールバック、の3系統を追加。`--gate-order` 廃止に伴う削除
- `test_skill_md.py`: SKILL.md 文言検査の期待を更新(調査前置・判別ミラー・assessments 例の存在)
- evals 系テスト(`test_run_fixed_state.py` 等): `--gate-order` 引数削除に伴う更新
- 全体試験の緑維持(現行 638 passed / 3 skipped)

## 8. 留保

- Jev は確率的モデルであり、新質問にも揺れは残る。本変更は判別の根拠を質問に明示することで精度を高めるもので、決定論的保証ではない
- 新文言の効果は live 再実行でのみ観測できる。offline replay は構造検証に限る
- 既存記録(final 等)は上書きせず、新ディレクトリに保存する。分母の取り扱いはこれまでどおり混ぜない
