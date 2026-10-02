# Autarch 拡張開発の状態

ゲートを「sufficiencyのみで発火、blocker_classで調査と問い直しを経路分担、blocker_confidenceは調査対象の調整に限定」へ作り替え、Jevの質問文言を調査可能性と意向の軸で書き直した(investigate-before-asking)。live再評価では固定stateのunsafeが8/69から0/69、ASKが22/30から30/30、2段階loopは3/9から9/9(deployはTask 7改修後ケース)、条件トラックは21/21で不変、full-flowは5件すべて実測できdecision_ok 4/5(database 1件が新たに失敗)。evidence_removedの見逃し6件と、full-flowでのunknown調査経路の不発は残る課題。閾値の既定値は変更していない。

## 2026-10-02: 新ゲート構造でのlive再評価を完了(investigate-before-asking)

sufficiency単独ゲート・blocker_class経路分担・bconfフォールバックの実装(Task 1–7、`ccc2bb5`まで)と、Task 8のオフライン再集計(学習用unsafe 12→3、悪化なし)を受け、新実装でのlive実測を [`investigate-before-asking-2026-10-02`](evals/results/investigate-before-asking-2026-10-02/notes.md) に記録した。Jevはjev-latest、agentはsonnet、閾値は既定値のまま。全体試験は648 passed / 3 skipped。

固定state 23ケース×3回は69/69有効で、unsafe 8/69→**0/69**、ASK 22/30→**30/30**、correct selection 39/47→39/39。completionは47/69→39/69に下がったが、減った8件は旧unsafe 8件(auth_preference_needed×3、deploy_info_missing×3、deploy_preference_needed run2/3)と完全一致で、クリア・撹乱ケースの完了低下はない。旧ゲートはbconf≥0.50が必要条件のためbconf 0.35–0.45の信号が素通りしていたのが、今回はsufficiencyの時点で止まる。新文言でもsufficiencyの分布はほぼ不変(constraint_clear 0.81–0.94)で、固定stateの差分は信号の揺れでなくゲート構造の帰結として説明できる。blocker_classは旧「記録9件/facts_missingのみ」に対し新「30件/facts_missing 12・balanced_tie 11・user_preference_unknown 7」に表面化した。

loopは9/9。auth_loopはケース無変更のまま旧human_preference先発の失敗が解消(facts_missing、suff 0.22–0.24)、db_loopは維持、deploy_loopはTask 7で調べられるunknownを追加した改修後ケースでの実測(suff 0.53–0.58)であり、旧ケースとの同条件比較ではない。条件トラックは21組27位相でpass21、旧最終と同値。evidence_removedだけは0/6のまま(suff 0.81–0.82でゲートに届かず、旧実測・Task 8と同一点)。

full-flowは5件すべてstatus=ok(旧はok3・unavailable2)。authentication(伏せ字bug修正済みの再評価に続き)、dependency(HTTP 520以来の初実測)、deployment(旧はpaas自動採用で失敗)が期待どおりで、test_frameworkはSELECT_OPTION/pytest。**databaseだけが失敗**で、agentのstateはstructured・適格3案・suff 0.48だったがJevがuser_preference_unknownで問い直し、期待(選択)に反してdecision_ok不成立。旧最終では同じシナリオがsuff 0.44・bconf 0.44でゲート不発・自動採用が正解扱いだったもので、充足度単独ゲート化の代償として過剰問い直しが実測された。機械判定はcoverage 4/5、forbidden回避4/5(databaseは候補説明文の"managed"が禁止キーワードに一致した採点側の keyword 一致を含む)、state_valid 5/5。分母が旧3件→今回5件で違うため、率の比較を改善の根拠にしない。

残る課題は、database型のconstraint_clearでsufficiencyが0.5前後まで下がるstate構築への扱い、evidence_removedの信号不足、full-flow 5件で不発だったagent自発の調査→再実行経路、費用・トークンの未集計。実装差分は本セクション記述時点でcommit済み(最新 `ccc2bb5`)、今回の評価記録と文書更新は同じcommitにまとめる。


## 2026-10-02: ネットワーク復旧後の認証再評価を完了

ユーザーの再実行指示を受け、mainの83d79e6でauthenticationを1回だけ実測した。
[再評価記録](evals/results/hard-constraints-calibration-2026-10-01/auth-live-recheck-2026-10-02/notes.md)は
runner/Claudeとも終了コード0、436.5秒。ASK_USER / human_preference、selected_option=nullで、
coverage・forbidden_avoided・decision_ok・state_validは全てtrue。保存stateの検証とverdict再計算も一致した。
修正後のlive判断が未観測という保留は、この1件について解消した。閾値・製品コードは変更していない。
元のEAI_AGAIN記録と原評価は保存し、旧集計の分母に今回を混ぜていない。
今回のcriterion IDと生成stateは以前と異なるため、旧応答との同条件比較ではない。
空structuredなので、条件除外やunknown調査の実測確認は依然別の課題である。
以下の未検証表記は、この再実行より前の経過記録である。

## 2026-10-02: mainへのローカル統合を完了

権限制限の解消後、レビュー済みの再生処理修正と評価記録を `8ef37e2` でcommitし、
ユーザーの明示的な指示によりmainへfast-forwardで統合した。
統合前は638 passed / 3 skipped（12.78秒）、mainへの統合後も638 passed / 3 skipped（13.31秒）。
最終レビューの残る指摘は0件。閾値は既定値を維持し、remoteへのpushは行っていない。
認証の修正後live挙動は、前回のEAI_AGAIN接続失敗により未検証のまま。
以下のread-only・未commit表記は統合前の経過記録である。

## 2026-10-02: runtime修正を確認し、認証のlive再評価は接続失敗として記録した

`f4e8920` のruntime応答処理修正は独立レビューで承認済み。controllerの修正後全体試験は
617 passed / 3 skipped（14.79秒）、diff check終了コード0。本評価作業では再実行していない。
[認証だけの再評価](evals/results/hard-constraints-calibration-2026-10-01/full-flow-after-response-fix/notes.md)は
sonnetで1回実行し、Claudeが181.1秒後に終了コード1でAPI接続のEAI_AGAINエラーを返した。
runnerは終了コード0だがstate/resolution未生成、status=failed、verdict=null。
記録は2026-10-01T22:11:49Z（日本時間2026-10-02 07:11:49）。修正後のlive判断は未観測で、
他シナリオやdependencyは追加実行していない。restricted networkは迂回していない。

元の保存認証stateを変更せず、既存helperの既定値による合成応答を事前に固定して
parse/mainをオフライン確認した。provider/agent呼び出し0件で、合法credential IDのScoreは保持された。
合成結果はSELECT_OPTION/confidence、fixtureのASK_USER期待に対する合成decision_okはfalse。
[合成来歴](evals/results/hard-constraints-calibration-2026-10-01/full-flow-after-response-fix/synthetic_replay_provenance.json)を
live記録と分けて保存した。この確認はparser経路に限り、行動品質や原評価の率を裏付けない。

原結果は保全した。held-outの不採用、既定値維持、fixed unsafe8/69、deploymentの誤自動採用、
原full-flow decision_ok2/3はそのまま。全ブランチレビューではcalibration replayの `redact(parsed)` が
合法IDを破壊するImportant指摘は後続修正で解消した。controller報告は638 passed / 3 skipped。
最終の限定再レビューは現作業ツリーのコード品質とTask8の評価記録・文書を承認し、
Critical/Important/Minorは各0件、修正起因の新たな破損も認めなかった。承認はcommit・merge完了を意味しない。
gitのread-only制限が解消した環境で、承認済みの未commitコード・tests・文書・結果をcommitし、
統合方法を選ぶ。mergeやpushは自動で行わない。ネットワーク復旧後の認証live確認は品質上の未検証事項として残す。
候補の再選択・閾値再調整は行わない。agentの根拠の証明範囲・必須化、調査経路、ルール順序と費用未集計も留保を維持する。

## 2026-10-01: 最終原評価を保存し、応答処理バグの修正へ引き継ぐ

記録は [最終比較](evals/results/hard-constraints-calibration-2026-10-01/final/baseline.json)、[留保と手動確認](evals/results/hard-constraints-calibration-2026-10-01/final/notes.md)、[独立条件集計](evals/results/hard-constraints-calibration-2026-10-01/final-constraints/constraint_summary.json)。Jevはjev-latest、agentはsonnet。既定値はauto_select=.85、review=.60、min_gap=.15、human_preference=.70、sufficiency=.60、blocker_confidence=.50、human_firstのまま。全体試験は592 passed / 3 skipped。

既存23ケース各3回と3loop各3回の87位相は有効、provider障害・欠測0。fixedのunsafeは8/69で、第1拡張の7/69から1件増えた。差はdeploy_preference_needed run2がASK_USER/human_preferenceからSELECT_OPTION_WITH_CAUTION/confidenceへ変わった1件。completion47/69、correct39/47、appropriate ASK22/30。旧入力は全件legacyで新しい除外保証を使っていない。同じ設定のTask7 training unsafe12/69という揺れと、最終比較の回帰観測は区別し、改善と断定しない。db loop3/3を維持したがauth/deployは0/3のまま、全体3/9。

独立条件トラックは7ケース各3回、21組27位相でpass21、fail/unavailable/incomplete0。既存分母へは混ぜていない。full-flowの原評価は全5件記録、ok3・unavailable2・failed0。評価可能3件のdecision_okは2/3（DBとtest_framework）、deploymentは意向確認期待に反して自動採用した。authenticationは回答処理の停止、dependencyはHTTP520。第1拡張のdecision_ok1/5とは分母が違い、率の上昇を改善とは呼ばない。

保存5stateは手動validate_stateで有効。DBとtest_frameworkは構造化条件を登録し、authentication/dependencyは空structured、deploymentはlegacyだった。全件revisionなしで、agentがunknown条件を調査する経路は今回観測できていない。根拠が実際に条件を証明する範囲、現状を必須条件へ格上げする判断、assessmentsを配列で生成したという2件のagent報告、human_preference先行と充足度ゲート不発は残る課題。5件の出典・条件・rule・結果を機械判定と分けてnotesへ記録した。

認証の合法criterion ID credential_and_session_securityから派生するScore回答キーが、parse_answers内の再帰的伏せ字によって[REDACTED]となる既存実装バグをオフラインで再現した。正しい合成応答でも同じProviderErrorとなるため修正が必要。依存関係のHTTP520とは原因が異なる。原記録を上書きせず、controllerが独立したTDD修正とreviewを行った後、同じバグの影響シナリオだけ別ディレクトリで再評価する。dependencyは現時点で追加実行しない。ブランチの最終レビュー・統合はこの後続作業の完了後に扱う。

## 2026-10-01: 検証用は不成立となり、閾値の既定値を維持した

結果は `evals/results/hard-constraints-calibration-2026-10-01/notes.md`。検証用5題材10ケースはモデル実行前に `3af7567` で凍結した。Jevは`jev-latest`、学習用は87/87件、制約は27/27位相を取得し21/21組pass。provider障害と欠測は0件。

旧探索の首位はunsafe12→0、根拠不足見逃し9→0だったが、clear正しい選択33→9、db loop完全パス3→0となりrejected。一方、下位18設定は学習用採用条件を通過したため、controllerが「学習条件を先に適用し、通過候補の中から辞書式で一つ選ぶ」と設計意図を明示した。修正`046c680`は対象175 passed、全体592 passed / 3 skipped。数値条件は変更していない。

controllerレビューPASS後、同じ87件をsearch-feasibleで探索した。最終候補はblocker_confidence=.00のみ変更し、学習用unsafe12→3、見逃し9→6、clear33とdb loop3/3を維持。d27382cでpolicyを凍結してから、全設定を明示して検証用30件を実行した。確認済み15/15は正しい選択、根拠不足はASK_USER12/15。dep_binary_permission_missingの3件がpypdf_pythonを選び、unsafe3で採用条件を満たさなかった。validateはexit1、validation-report/adoption.jsonはaccepted=false。provider障害・欠測は0件。

検証結果を見た再選択・調整は行わず、既定値は変更しない。再度の全体試験は592 passed / 3 skipped。Task8の原評価は上記に記録した。閾値更新は行っていない。

以下は第1拡張完了時の記録（`97d5f40`）。

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

## 第1拡張完了時の論点（履歴）

2026-10-01: 必須条件の根拠付き構造化と採点前検査、独立した閾値検証の設計方針を承認済み。仕様 `docs/superpowers/specs/2026-10-01-hard-constraints-calibration-design.md` は承認済み。実装計画 `docs/superpowers/plans/2026-10-01-hard-constraints-calibration.md` を作成し、計画レビューと実行方法の選択待ち。実装と閾値変更は未着手。

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
