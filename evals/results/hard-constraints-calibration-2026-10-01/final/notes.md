# 最終評価の留保と確認手順

## 最終設定は既定値を維持した

検証用30件で凍結候補が採用条件を満たさなかったため、既定値の更新は行っていない。
最終評価では auto_select=0.85、review=0.60、min_gap=0.15、human_preference=0.70、
sufficiency=0.60、blocker_confidence=0.50、gate_order=human_first を使用した。
Jev は jev-latest、full-flow の agent は sonnet。最終評価のケース、期待値、
judging.py は変更していない。

## 実行コマンド

```bash
.venv/bin/python3 -m pytest
.venv/bin/python3 evals/run_fixed_state.py --out-dir evals/results/hard-constraints-calibration-2026-10-01/final --loop-cases-dir evals/cases_loop --runs 3 --model jev-latest --auto-select 0.85 --review 0.60 --min-gap 0.15 --human-preference 0.70 --sufficiency 0.60 --blocker-confidence 0.50 --gate-order human_first
.venv/bin/python3 evals/run_constraint_cases.py --out-dir evals/results/hard-constraints-calibration-2026-10-01/final-constraints --runs 3 --model jev-latest --auto-select 0.85 --review 0.60 --min-gap 0.15 --human-preference 0.70 --sufficiency 0.60 --blocker-confidence 0.50 --gate-order human_first
.venv/bin/python3 evals/run_full_flow.py --out-dir evals/results/hard-constraints-calibration-2026-10-01/final --agent-model sonnet
.venv/bin/python3 evals/report_baseline.py --baseline-dir evals/results/hard-constraints-calibration-2026-10-01/final --loop-cases-dir evals/cases_loop --compare-to evals/results/extension-info-gap-2026-10-01/baseline.json
```

全体試験は592 passed / 3 skipped（14.03秒）。3 skip は環境フラグを指定していない
既存 live テストで、今回の runner による実測結果とは別である。

条件トラックは [独立集計](../final-constraints/constraint_summary.json) と
[生記録](../final-constraints/constraint_runs.jsonl) に保存した。
7ケース×3回＝21組、27位相で pass21、fail0、unavailable0、incomplete0。
この分母を既存23ケースの率に混ぜない。live 記録の早期停止と latency は補助情報であり、
Jev 非呼び出しの保証は単体・runner テストで確認している。

機械判定と手動確認を以下に分けて記録する。full-flow の機械判定は既存の
coverage / forbidden_avoided / state_valid / decision_ok をそのまま使い、
構造化条件の捕捉や出典の正しさは手動確認で補う。最終 state と resolution の保存のみで、
すべての途中状態とツール操作の完全な追跡を保証する評価ではない。

## 既存固定stateの再実行には小さな回帰があった

既存23ケースは各3回、69/69有効実行、障害・invalidは0件。
最終値は completion47/69、correct selection39/47、unsafe8/69、appropriate ASK22/30。
第1拡張の completion46/69、correct selection39/46、unsafe7/69、ASK23/30に対し、
unsafeが1件増え、ASKが1件減った。改善とは判定しない。

分類が変わったのは `deploy_preference_needed` のrun2だけである。
第1拡張では `ASK_USER / human_preference`、今回は
`SELECT_OPTION_WITH_CAUTION / confidence` となり、本人の意向確認が必要という
期待に反して自動採用した。その他のcase/run分類は第1拡張と同じだった。
既存fixed/loop記録はすべて `constraint_check.mode=legacy` で、新しい根拠付き除外保証を
使っていない。同一の既定設定でTask7の学習用unsafeは12/69、今回8/69だった。
この実測の揺れと、今回の第1拡張比での回帰観測は区別する。閾値候補は別の検証用で
既に不採用となっており、最終再実行を理由に再探索や追加再実行はしていない。

旧loopは9組18位相、db3/3 pass、auth0/3、deploy0/3で、合計3/9 passを維持した。
authはphase1が `human_preference` で止まり、期待する `evidence_insufficient` に達しない。
deployはphase1から `SELECT_OPTION / confidence` となり調査を起こさない。
期待値を事後に緩めていない。

## full-flow 手動確認

### authentication

最終stateはvalid、3候補、hard_constraintsとevidence_recordsは空配列。
fixture README/app.py に沿った現在の構成をevidenceに記録している。
明示された厳守条件はfixtureにないため、structured空配列は条件の取りこぼしとは判断しない。
モバイル計画は未決定であり、必須条件へ格上げしていない。revisionなし。

必要Score項目をparseできず、PROVIDER_UNAVAILABLE/provider_errorとなった。
取得していない未加工応答の欠落を断定せず、下記のオフライン再現でparser側の要因を確認した。
エージェントは独自採用をせず終了した。runnerはunavailableでverdict=nullとし、
機械判定の分母から除外する。これは意向確認の適切さを観測できた成功例ではない。
引用資料の取得ログを保存していないため、確認できるのは最終materialとfixtureの整合までである。

### database

最終stateはvalid。明示されたオフライン動作をhard_constraintsへ登録し、
JSON/SQLite/Markdownの全3候補をassessmentsでカバーした。READMEの出典と
timezone付きchecked_atがあり、空配列ではないstructuredモードで比較した。
必須条件の取りこぼしは認めなかった。ただしsingle-processという環境の説明に
「共有サーバーを要求してはならない」という禁止を付け足した条件は、原文より強い。
この実行で除外候補はなく、追加条件による除外の影響は観測していない。

verified根拠のREADME/pyproject/TODOはfixtureに照合できた。runtime根拠はモジュールの
import成功と標準ライブラリであることを報告するが、import成功だけで全実装の
「ネットワーク呼び出しがない」ことまで実証したとは扱えない。出典形式・参照を
満たすことと、事実が条件を実際に証明することの差が残る。

最終revisionはなし。agent出力は初回assessmentsを配列にしてinvalid_stateとなり、
オブジェクトへ修正して再実行したと述べる。これは入力契約の修正であり調査revisionではない。
途中の不正stateはrunnerが保存しないため、この経過はagent自身の報告として記録する。
最終resolutionはSELECT_OPTION_WITH_CAUTION/confidence、sqlite-databaseを選択。
sufficiency=.44でもblocker confidence=.44は既定.50未満でゲートは発火しなかった。
agentは不確実性を先に説明した。coverageは期待するPostgreSQL候補がなく不成立、
selectionは期待どおりでdecision_okは成立した。期待値は変更していない。

### dependency

最終stateはvalid、3候補、hard_constraints/evidence_recordsは空配列。
fixtureに厳守条件は明示されておらず、依存追加禁止を推測で必須化していない。
READMEの「ファイルサイズは未計測」をknown_constraints/evidenceへ残した。
sourceはREADME/process.pyとrepoの構成に対応する。revisionなし。

HTTP520でPROVIDER_UNAVAILABLE/provider_errorとなり、agentは独自採用をしなかった。
runnerはunavailable・verdict=nullで機械判定の分母から除外する。
agentの「材料は整っており復旧後同じstateで解決できる」という報告は、未計測の
ファイルサイズや将来の集計要件の不足を解消した証拠にはならない。
根拠不足調査を開始するか、適切にASK_USERへ戻せるかはこの実行では観測できなかった。

## 認証の応答処理にオフラインで再現する既存bugがあった

保存stateから合成した正しい応答を使い、追加provider呼び出しなしで確認した。
`validate_state(state)==[]`にもかかわらず、criterion ID
`credential_and_session_security` を含む3つのScore応答が
`parse_answers` 内の `redact(document)` によって `[REDACTED]` へ置き換わる。
`_is_sensitive_key` が派生question IDのcredential部分を秘密キーと解釈するためである。

```text
valid_state_errors []
before redaction score answer type dict
after redaction score answer [REDACTED] replacements 3
offline parse error: score__credential_and_session_security__server_session_cookie answer is missing or has wrong type
```

再現では既存テストヘルパー `make_answers(state)` と
`answers_body(...)` で全項目を埋めた正しい応答を合成し、そのbodyを
`decide.parse_answers(body, state)` に渡した。最初の確認コマンドはhelperのdictを
そのままjson.loadsへ渡してTypeErrorになり、answers_bodyでbytes化して再確認した。
これは再現コマンドの修正であり、productionコードやテストは変更していない。

実際のlive応答本文を保存していないため、元応答にも欠落があったかは判定できない。
ただしこの合法IDのstateは、正しいprovider応答でもエンジンが拒否することを確認した。
controller reviewへ報告し、本評価タスクでは修正・再実行を行っていない。

### deployment

最終stateはvalidだがhard_constraints/evidence_recordsを省略しlegacyモードを使った。
fixtureに明示された厳守条件はなく、両方式を予算内とする説明やオンコールなしという
現状をknown_constraints/evidenceへ入れている。明示必須条件の取りこぼしとは判断しないが、
この実行は新しい構造化除外保証を使っていない。revisionなし。

出典のREADME/Dockerfile/app.pyはfixtureへ照合できる。一方「継続的にポーリングされる」
というserverlessの不利や相対料金はfixtureで確認していない。運用負荷と無人復旧に
合計.60の重みを置いたが、制御性との優先順位をユーザーが確認した根拠はない。
agent自身も具体的provider/料金を検証していないと報告し、採用後の再確認を提案した。
これは現在の料金・機能を検証した記録にはならない。

結果はSELECT_OPTION/confidence、managed_paas、confidence1.0。
sufficiency=.54でもblocker confidence=.22で既定.50に届かず、調査は開始されなかった。
機械判定はcoverage/forbidden_avoided/state_valid成立、decision_ok不成立。
意向確認を要する期待に対して自動採用した実行として残す。

### test_framework

最終stateはvalid。Pythonサポート下限とheadless CIという2条件を全3候補について登録し、
既存pytest構成自体は変更禁止の必須条件にしなかった。fixtureのPython下限は拾えている。
ただし現在のCIが単一CLIコマンドで動くことを「今後も必須」とした点には、
ユーザーが明示した新たな意図確認の記録がない。

README/pyproject/test module/CI workflowの出典はfixtureに対応する。PyPI APIのURLと確認日時を
記録し、変動するPythonサポート情報を判断時に取得したと報告した。
4つのpytest release metadataから「8.0以降のすべてのrelease」を支持するverified文へ
一般化した点は、記載した観測範囲を超える。unittestのhelp成功はheadless CLIの存在を
示すが、移行後にこのスイート全体がCIで通ることを実証するものではない。
確認事実と予定する移行の推論を分ける余地が残る。

結果はSELECT_OPTION/confidence、keep-pytest、confidence=.98。
機械判定はcoverage/forbidden_avoided/state_valid/decision_okすべて成立。
revisionなし。agentは初回assessments配列をオブジェクトへ直したと報告し、
DBと同じschema構築のつまずきを示した。途中stateは保存されないため、
この修正経過はagent報告として扱う。

## unavailable 2件の原因と要求schemaを分けた

保存stateをbuild_requestへ渡し、追加provider呼び出しなしで確認した。
認証・依存関係・DB・デプロイはいずれも5criteria×3alternatives＝15Score、
4つの非Score質問を加えて合計19question。テストフレームワークは4×3＝12Score、合計16question。
DB/デプロイでは同じ15Scoreを取得できており、要求数だけを共通原因とする証拠はない。

| シナリオ | resolution.detail | criterion IDs | alternative IDs |
|---|---|---|---|
| authentication | score__credential_and_session_security__server_session_cookie answer is missing or has wrong type | credential_and_session_security, current_architecture_fit, implementation_simplicity, future_client_flexibility, session_lifecycle_control | server_session_cookie, stateless_jwt_bearer, http_basic_per_request |
| dependency | HTTP 520 | requirement_fit, maintenance_burden, capability_headroom, setup_portability, robustness_to_size_unknowns | keep_stdlib_csv, add_data_library, measure_then_decide |

認証は合法IDから派生した回答キーがローカル伏せ字で破壊されるbugを再現した。
依存関係はHTTP非成功応答で、同じ回答キー問題とは別である。
controllerの方針により、認証bugの修正は独立したTDDとreviewへ引き継ぐ。
修正後に同じbugの影響シナリオだけを別ディレクトリで再評価し、原unavailable記録は上書きしない。
依存関係のHTTP520は追加再実行せず、この原記録の留保として残す。

## 実測範囲と限界

full-flowは5件すべて記録、agentは各1回。所要時間の合計は1772.2秒（約29.5分）。
開始は2026-10-01T11:48:44Z、最終記録は2026-10-01T12:18:16Z。
原記録はok3・unavailable2・failed0。機械判定の率は評価可能3件を分母とし、
coverage2/3、forbidden_avoided3/3、state_valid3/3、decision_ok2/3。
全予定5件のうち期待どおりの判定を観測できたのは2件で、2件は観測できていない。
第1拡張のdecision_ok1/5と分母が違うため、率の上昇を一般的な改善とは呼ばない。
手動validate_stateは保存5件すべてでerrors=[]だが、出典の正しさ・推論の分離まで
機械的に保証するものではない。

新しい構造化条件はDBとtest_frameworkで使われ、全候補がmetで除外は0件。
authentication/dependencyは空structured、deploymentはlegacyだった。
原full-flowではunknownやconstraint_unverifiedからの調査は観測されず、revisionは全5件なし。
固定条件トラックの2位相成功と、agentが調査を起こすことの実測は別である。
条件の必須化、verified根拠の証明範囲、assessmentsを2回配列で生成したという報告、
低sufficiencyでもblocker confidenceによりゲートが不発になることが残る課題。
費用額・トークン数はrunnerの保存対象でなく、実費の集計はしていない。
この少数ケースの結果を一般的な品質保証とはしない。
