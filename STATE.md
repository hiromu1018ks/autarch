# Autarch 拡張開発の状態

「情報不足の分類と一度の追加調査」を実装し、`extension-info-gap-2026-10-01` として再評価した(未 merge、branch `info-gap-investigation`)。固定 state トラックの2指標が大きく改善、full-flow は据え置き。次は必須条件の判定と、データが揃った閾値の見直し。ファイルは節目ごとに更新する。

## 現在地: 第1拡張(情報不足の分類と追加調査)の実装と再評価まで完了

- 第1拡張の実装: decide.py に Jev 新質問2種(noul `evidence_sufficiency` + choice `blocker_class` 4分類)、根拠充足性ゲート、state `revision` による一度制限。SKILL.md Step 11 を分岐形式に書き換え(調査→再実行→`investigation_exhausted`→問い直し)
- 評価の拡張: 2段階ケース `evals/cases_loop/` 3件 + runner の2段階実行 + `report_baseline.py` の loop 集計と `--compare-to`。`judging.py` の指標定義は不変
- 通常テストは 216 passed / 3 skipped(live 系3件は環境変数指定時のみ)
- 再評価記録: `evals/results/extension-info-gap-2026-10-01/`(Jev 87回 + agent 5回、`baseline.json` に baseline との比較、`notes.md` に留保)
- 文書: spec `docs/superpowers/specs/2026-10-01-info-gap-investigation-design.md`、計画 `docs/superpowers/plans/2026-10-01-info-gap-investigation.md`

## 第1拡張の効果(baseline-2026-10-01 との比較)

| 指標 | baseline | 拡張後 | 変化 |
|---|---|---|---|
| Appropriate Ask Rate | 53.33% | 76.67% | +23.3pt |
| Unsafe Auto-selection Rate | 20.29% | 10.14% | −10.1pt |
| evidence_removed 撹乱 | 0/6 | 0/6 | 変わらず |
| Correct Selection Rate | 73.58% | 84.78% | +11.2pt |
| completion_rate | 76.81% | 66.67% | −10.1pt(全て旧 Unsafe の転換) |
| loop_pass_rate | — | 33.3%(3/9) | db は完全パス |

- completion 低下の7実行はすべて以前 Unsafe だった info_missing / preference_needed ケース。クリアケースの完了低下なし。reorder / detail_asymmetry / violating_candidate は 6/6 維持
- evidence_removed では Jev の sufficiency が 0.80〜0.84 まで下がるが、ゲート閾値 0.60 に届かない。**閾値見直しのデータが揃った**(生記録に分布あり)
- full-flow は baseline と同水準(decision_ok 1/5)。agent 構築 state は `human_preference` がゲート前に発火しやすく、`evidence_insufficient` が返らず調査ループは不発。弱点は engine のルール順序と agent の state 構築に移った

## baseline が示した弱点: 候補作成ではなく、根拠が足りないときの挙動に偏る

| 指標 | 値 | 読み |
|---|---|---|
| Unsafe Auto-selection Rate | 20.29%(14/69) | 情報不足・意向確認ケースでの誤った自動選択。内訳は info_missing 9件、preference_needed 5件 |
| Appropriate Ask Rate | 53.33% | ユーザーへ戻すべきケースの半分近くを戻せていない |
| evidence_removed 撹乱 | pass 0/6 | 判断に必要な根拠を削除しても confidence 0.85 以上のまま自動選択した |
| full-flow Decision Correctness | 20%(1/5) | 候補の coverage 80%・違反候補の回避 100%・state の妥当性 100% に対し、決定を戻す判断が弱い |

並び順変更と説明量の非対称の撹乱は 6/6 で pass、必須条件違反候補の誤採用は 0 件だった。候補を作る部分は健全で、根拠が足りないときに問い直すか調べるかの判断が効いていない。

## 改修の経緯

測定方式(hybrid: 固定 state + full-flow)は Autarch 自身に評価を依頼して決めた。Jev は Choice でハイブリッド、重み付き Score で固定 state のみを首位とし、ASK_USER に割れた。決め手は「初回の baseline から agent 側の品質も測るか」で、リリース済みスキルの品質を優先するオーナーの判断でハイブリッドになった。

実装は11タスクを TDD で進めた(失敗テスト→実装→全テスト緑を各タスクで確認)。計画にない修正は3件入れている。

1. `perturbation_run_pass` に `auto_select=0.85` の既定値を追加(計画のテストが3引数で呼ぶため)
2. `pytest.ini` に `testpaths=tests` を追加(fixture 内のテストファイルを pytest が収集して失敗するため)
3. full-flow の prompt を stdin で渡すように変更(claude CLI の可変長 `--allowedTools` が末尾の prompt 引数を飲み込む)。初回の5シナリオが全滅したので記録を破棄して再実行し、経緯を `notes.md` に残した

merge 前の全体レビュー(opus、fresh context)は Critical 0・Important 3・Minor 7。Important の3件は修正済みで、それぞれ失敗テストを経由して直している。

- `match_group` がキーワード側を小文字化しておらず、大文字キーワードが無条件不一致になる(spec の大文字小文字不問に違反)
- full-flow で Jev が PROVIDER_UNAVAILABLE を返したとき判定対象外(unavailable)にせず decision_ok=False に数え込んでいた
- `SUMMARY.md` 再生成時に手書きの留保が消える。`notes.md` を置いて再生成でも残るようにした

修正後、baseline の数値が生記録から独立に再現すること、再生成で数値が変わらないことを確認して merge した。

## ネクストアクション

1. **必須条件の判定(採点前の除外)**を設計・実装する。brainstorming → spec → 実装計画の流れ。現行 baseline では違反候補の誤採用が 0 件なので、効果は除外した結果の候補数の扱い(1候補以下になった場合の確認)側に出る見込み
2. **閾値の見直し**にデータが揃った。`sufficiency` は evidence_removed で 0.80〜0.84 に分布しており、0.60 では捕捉できない。auto_select(0.85)との関係も含めて再検討する
3. loop ケースの修正: `auth_loop_resolvable`(human_preference が先発してゲート未到達)と `deploy_loop_resolvable`(state の薄さ不足)の設計直し。ループ機構自体は db で検証済み
4. full-flow の課題: agent 構築 state で `human_preference` が先行発火し `evidence_insufficient` に届かない。engine のルール順序(human_preference と ゲートの前後)を含めた再検討
5. 前段の小作業は引き続き保留(旧 Minor 7件の robustness pass、`evidence_removed` 合格基準の見直し、database シナリオの coverage 期待の調整)
6. `origin/main` への push は任意のタイミング(第1拡張の merge 後が自然)

閾値変更の効果確認は、同じケースセットで再実行して `extension-info-gap-2026-10-01/baseline.json` と比較する。

## 留意事項

- 評価の実行は `decide.py` 経由で `~/.autarch/decisions.jsonl` にも追記される(log path の指定はできない)
- baseline 再実行の費用感: 固定 state 69回は数分で終わる(Jev の応答が速い)。full-flow は1シナリオ2〜4分の agent 実行が5回
- full-flow の agent model は baseline 記録に残る。2026-10-01 baseline は sonnet
