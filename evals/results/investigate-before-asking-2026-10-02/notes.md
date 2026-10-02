# investigate-before-asking の live 再評価: unsafe 8/69 が 0/69、loop 9/9、full-flow は 4/5

新ゲート構造(充足度のみでゲート、blocker_class で経路分担、blocker_confidence は調査対象の調整に限定)での初回 live 実測。固定 state の誤自動選択は 8/69 から 0/69 になり、問い直しは 30/30、2段階 loop は 9/9 だった。一方で full-flow の database 1件が新たに失敗し、evidence_removed の見逃し 6 件は旧実測と同一点に残った。以下の数値はすべて分母を緩めず、失敗はそのまま記録する。

## 実行設定

コマンドと閾値は計画どおりで、case の期待値・judging.py は変更していない。

```bash
.venv/bin/python3 -m pytest -q   # 648 passed / 3 skipped (3 skip は live 系)
.venv/bin/python3 evals/run_fixed_state.py --out-dir evals/results/investigate-before-asking-2026-10-02 --loop-cases-dir evals/cases_loop --runs 3 --model jev-latest --auto-select 0.85 --review 0.60 --min-gap 0.15 --human-preference 0.70 --sufficiency 0.60 --blocker-confidence 0.50
.venv/bin/python3 evals/run_constraint_cases.py --out-dir evals/results/investigate-before-asking-2026-10-02-constraints --runs 3 --model jev-latest (閾値は同上)
.venv/bin/python3 evals/run_full_flow.py --out-dir evals/results/investigate-before-asking-2026-10-02 --agent-model sonnet
.venv/bin/python3 evals/report_baseline.py --baseline-dir evals/results/investigate-before-asking-2026-10-02 --loop-cases-dir evals/cases_loop --compare-to evals/results/hard-constraints-calibration-2026-10-01/final/baseline.json
```

Jev は jev-latest、full-flow の agent は sonnet。比較対象は 2026-10-01 最終評価([baseline.json](../../hard-constraints-calibration-2026-10-01/final/baseline.json))。`--compare-to` にはディレクトリではなく baseline.json を渡した(runner は JSON ファイルを読む。前回最終評価の notes も同様)。

## 固定 state: 8件の誤自動選択がすべて問い直しに変わった

69/69 有効、unavailable・invalid 0。

| 指標 | 旧最終 (2026-10-01) | 今回 |
|---|---|---|
| completion | 47/69 (68.12%) | 39/69 (56.52%) |
| correct selection | 39/47 (82.98%) | 39/39 (100%) |
| unsafe | 8/69 (11.59%) | **0/69** |
| appropriate ASK | 22/30 (73.33%) | **30/30** |

completion の減 8 件は旧 unsafe 8 件と完全に一致し、クリア・撹乱ケースの完了低下はない。旧 unsafe の内訳と、今回の行き先は次のとおり。

| 旧 unsafe | 旧の挙動 | 今回 |
|---|---|---|
| auth_preference_needed ×3 | SELECT_OPTION/jwt_stateless (conf 1.0) | ASK_USER、suff 0.55、balanced_tie、bconf 0.35–0.38 |
| deploy_info_missing ×3 | SELECT_OPTION/paas_container (conf 1.0) | ASK_USER、suff 0.41–0.44、facts_missing、bconf 0.17–0.23 |
| deploy_preference_needed run2/3 | SELECT_OPTION_WITH_CAUTION/paas_container | ASK_USER、suff 0.49–0.50、balanced_tie、bconf 0.37–0.38 |

旧ゲートは「suff < 閾値 かつ bconf >= 0.50」が必要条件だったため、bconf が 0.50 未満のこれらの信号はゲートを素通りして自動選択していた。今回の 30 件の問い直しのうち 21 件は bconf 0.50 未満で、それでも sufficiency が 0.60 未満の時点で止まる。SELECT_OPTION_WITH_CAUTION は固定 state から消えた(rule の内訳は旧 confidence 47 / evidence_insufficient 9 / human_preference 11 / disagreement 2 に対し、今回 confidence 39 / evidence_insufficient 27 / human_preference 3)。

撹乱は detail_asymmetry 6/6・reorder 6/6・violating_candidate 6/6 を維持し、evidence_removed だけが 0/6 のまま。この 6 件は suff 0.81–0.82 でゲート閾値に届かず、旧実測・Task 8 のオフライン再集計と同一点である。信号がこれ以上の不足を報告しない限り、0.60 のままでは拾えない。

## loop: auth を含む 9/9。deploy は改修後ケースでの実測

9組 18位相、phase1 は 9件全部が ASK_USER / evidence_insufficient / facts_missing、phase2 は 9件全部が SELECT_OPTION / confidence で正解選択。

| case | 旧最終 | 今回 | phase1 の信号 |
|---|---|---|---|
| auth_loop_resolvable | 0/3 | **3/3** | suff 0.22–0.24、bconf 0.54–0.56 |
| db_loop_resolvable | 3/3 | 3/3 | suff 0.37–0.39、bconf 0.38–0.40 |
| deploy_loop_resolvable | 0/3 | **3/3** | suff 0.53–0.58、bconf 0.87–0.89 |

auth_loop はケースファイル無変更のまま、旧は human_preference が先発して expected の evidence_insufficient に届かなかったのが、今回は facts_missing で止まる同条件の改善である。deploy_loop は Task 7 で evidence に「legacy pipeline の出力形式が記録されていない」という調べられる unknown を追加した改修後のケースでの実測であり、旧ケースとの同条件比較ではない。旧ケースでの保存 suff は 0.86–0.87 でゲート不発だったことと、今回の 0.53–0.58 は両方事実として残す。

## 条件トラック: 21/21 で旧最終と同値

7ケース×3回＝21組、27位相で pass 21、fail・unavailable・incomplete 0。旧最終の [constraint_summary.json](../../hard-constraints-calibration-2026-10-01/final-constraints/constraint_summary.json) と同値で、この分母を既存 23 ケースの率に混ぜていない。生記録は [constraint_runs.jsonl](../investigate-before-asking-2026-10-02-constraints/constraint_runs.jsonl)、集計は [constraint_summary.json](../investigate-before-asking-2026-10-02-constraints/constraint_summary.json)。所要 33 秒。

## full-flow: 4/5。database 1件の失敗を残す

5件すべて status=ok(旧最終は ok3・unavailable2)。合計 1690.9 秒(約28.2分)。

| scenario | 期待 | 実測 | 判定 | suff / blocker / bconf |
|---|---|---|---|---|
| authentication | ASK_USER | ASK_USER | **true** | 0.59 / user_preference_unknown / 0.40 |
| database | SELECT_OPTION | ASK_USER | **false** | 0.48 / user_preference_unknown / 0.35 |
| dependency | ASK_USER | ASK_USER | **true** | 0.45 / user_preference_unknown / 0.24 |
| deployment | ASK_USER | ASK_USER | **true** | 0.31 / user_preference_unknown / 0.49 |
| test_framework | SELECT_OPTION | SELECT_OPTION/pytest (conf 1.0) | **true** | 0.83 / なし / なし |

機械判定は coverage 4/5、forbidden回避 4/5、判定妥当 4/5、state妥当 5/5。旧最終の「評価可能3件の decision_ok 2/3」と今回は評価可能5件の 4/5 で、分母が違う。率の上昇をそのまま改善とは呼ばない。

変化の内訳。authentication は旧、応答キーの伏せ字 bug で unavailable だったものが、修正後の再評価([auth-live-recheck](../../hard-constraints-calibration-2026-10-01/auth-live-recheck-2026-10-02/notes.md))に続き今回も ASK_USER となり 4 項目を通した。dependency は旧 HTTP 520 に続く初の実測で、期待どおり ASK_USER。deployment は旧、suff 0.54・bconf 0.22 でゲート不発のまま managed_paas を自動採用して decision_ok false だったのが、今回は suff 0.31 の時点で止まり、拡張予定の確度を問う 1 点質問を返した。spec §1 の「full-flow deployment の decision_ok 成立」はこれで成立した。

database は今回の失敗である。agent 自体は README のオフライン・シングルプロセス要件を hard_constraints 2件に登録し、evidence_records 7件、3案すべて適格の structured モードだった。技術評価は SQLite 優位(probability 0.87)だが、多基準の複合スコアが SQLite 0.698 対 Markdown 0.685 の僅差で、Jev は残る決定要素をユーザーの優先順位と判定して問い直した。出力された質問自体は意図軸(「CLI を経由せず直接扱いたいか」)で筋が通っている。ただしこのシナリオの期待は選択(requires_human_preference=false)であり、decision_ok は成立しない。旧最終では同じシナリオが suff 0.44・bconf 0.44 でゲート不発、自動採用が正解として数えられていた。充足度単独ゲート化の帰結が表れた失敗で、過剰な問い直しが今回の構造の代償として実測されたことになる。

なお database の forbidden_avoided false は採点側のキーワード一致による。「…database file managed through Python's built-in sqlite3 module」という候補説明文の managed が禁止グループ ["managed"] に一致した。judging.py は変更しておらず、観測どおりに記録する。

agent の state 構築は 5件とも structured モード・除外 0・unknown_assessments 0・revision なし。unknown をきっかけに agent が自発的に調査→再実行する経路は、この 5 件では発火しなかった。

## 新シグナルの分布: sufficiency はほぼ不変で、構造差が差分の説明になる

固定 state 69 実行の比較。Jev の信号そのものはほとんど動いていない。

| 信号 | 旧最終 | 今回 |
|---|---|---|
| sufficiency (constraint_clear) | 0.81–0.94、平均 0.86 | 0.81–0.94、平均 0.86 |
| sufficiency (info_missing) | 0.22–0.42 | 0.22–0.44 |
| sufficiency (preference_needed) | 0.16–0.57 | 0.16–0.55 |
| blocker_class の記録 | null 60 / facts_missing 9 | null 39 / facts_missing 12 / balanced_tie 11 / user_preference_unknown 7 |
| blocker_confidence の記録 | 9件のみ (0.58–0.98、全部 0.50 以上) | 30件 (0.15–0.96。0.30 未満 6、0.30–0.49 が 15、0.50 以上 9) |
| human_preference_probability | 0.21–0.84 | 0.18–0.84 |

旧は bconf が 0.50 未満だとゲート条件を満たさず、blocker_class も bconf も記録されないまま自動選択していた。今回の構造では sufficiency が閾値未満なら blocker 情報が必ず表面化し、bconf は調査対象を広げる方向にだけ効く。sufficiency の分布がほぼ同じなので、固定 state の差分は信号の揺れではなくゲート構造の帰結として説明できる。Jev question 文言の変更(a442b04)がこの分布を sensibly 動かした証拠は、固定 state では観測されなかった。

## オフライン再集計と live は別の測定である

Task 8 の [オフライン再集計](offline-replay/notes.md) は、旧文言で保存済みの信号を新構造で読み直したもので、学習用 unsafe 12→3 を確認したが文言変更の効果は測れなかった。今回の live は新文言で信号を取り直す初回の実測である。両者の unsafe の減少幅(オフライン学習用 −9、live 固定 state −8)はケース集合も分母も違い、足して比較するものではない。

full-flow は agent が新しい SKILL.md の問いに沿って state を構築するため、文言の効果が最も出る場所である。実測では 5 件中 4 件が意向軸の 1 点質問(モバイル対応の確度、メモを直接扱いたいか、status-page の拡張予定、stdlib 継続のトリガー)を生成した。ただし各シナリオ 1 回で、統計的な主張はできない。

## 留保と限界

- database の full-flow 失敗は今回の構造で新たに観測された。旧最終で正解と数えられていた自動採用が、今回は問い直しになり機械判定上は失敗である。「問い直しが増えた」ことと「判定が正しい」ことは別で、改善と断定しない。constraint_clear で sufficiency が 0.48 に下がる state 構築自体が妥当かは、シナリオ1回では分からない。
- evidence_removed 0/6 は旧と同一点。suff 0.81–0.82 の信号が変わらない限り、clear 33 完了を壊さずにこれを拾う閾値はグリッドにない(Task 8 の診断と同じ結論)。
- deploy_loop の 3/3 は Task 7 改修後のケースでの実測で、旧ケースとの同条件比較ではない。auth_loop と db_loop はケース無変更。
- full-flow は各シナリオ 1 回、5 件が分母。旧最終は評価可能 3 件で、率の差を品質の差として読めない。agent の出典が fixture の事実を実際に証明するか、推論と事実を分離できているかまで機械判定は保証しない。今回も state の最終形と agent 自身の報告からの手動確認にとどまる。
- unknown 調査→再実行の経路は full-flow の 5 件で不発。条件トラック env_unknown_resolved や loop ケースの 2 段階成功は、runner が注入した調査の成功であり、agent が自発的に調査を起こす実測とは別である。
- full-flow の ASK 4件の信号は intent 系 blocker(user_preference_unknown)・bconf 0.24–0.49 で、エンジン側では低 confidence の fallback 経路(rule evidence_insufficient)に該当する。修正前の SKILL.md Step 11 は blocker class を先に照合していたため、agent は調査をせず即座に問い直した。unknown 調査→再実行の経路が 5 件で不発だったのは、この文書とエンジンの食い違いが一因である。
- Step 11 は rule を先に照合するよう SKILL.md を修正し、低 confidence fallback を明記した。本修正の live 効果は未再測で(再実行はしていない)、開いた留保として残す。
- 費用・トークン数は runner の保存対象でなく未集計。decide.py 経由で `~/.autarch/decisions.jsonl` に追記されている(既定の動作)。
- この少数ケースの結果を一般的な品質保証とはしない。
