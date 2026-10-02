# Task 8: オフライン再集計で新ゲート構造はunsafeを増やさなかった

保存済みの学習用87位相と検証用30位相を、ゲート変更後のコードで再集計した。参照政策(既定B)のunsafeは学習用で12→3に減り、clear完了・正しい選択33/33、db loop 3/3、不要質問0は変わらない。検証用は旧記録と同値でunsafe=3のまま。増えた項目はない。spec §6.1の判定は合格で、計画はlive再実行へ進められる。この記録は同一保存信号上の構造差を測る健全性確認であり、質問文言変更(`a442b04`)の効果測定ではない。保存信号は旧文言で取得済みなので、文言の影響はliveでのみ観測できる。

本実行はTask 7の前に位置する。`evals/cases_loop`を含む既存ケースファイルは一切変更しておらず、新出力はすべて `evals/results/investigate-before-asking-2026-10-02/` 配下で、既存結果の上書きもしていない。

## describeはlegacy snapshotをreplay不能と数えていた

describeのreplayableはsnapshotのキー集合を4キーのSNAPSHOT_FIELDSと素比較するため、`gate_order` を含む旧5キーsnapshotが全件replayable=0と数えられていた。`replay_resolution` と同様に比較前へ `gate_order` を除くよう `evals/calibrate_thresholds.py` を修正した。legacy snapshotを1件と数え、実フィールドの欠損がある場合は0のまま落ちることを `test_describe_counts_legacy_gate_order_snapshot_as_replayable` で固定している。修正後、実87件のdescribeはreplayable=87を返す([training-describe.json](training-describe.json))。calibrate試験196 passed、全体は648 passed / 3 skipped。

## 学習用再集計: unsafe 12→3、見逃し9→6、他は不変

元のsearchと同じ引数で、元のケースディレクトリとmanifest、保存済み87位相をそのまま渡して新out-dirへ再実行した。新しいrankingは45行(gate_order軸の除去)、旧は90行で同値のreference行が2つ(grid_index 2と3)あった。新しいrankingのreference行はgrid_index 1の1つだけ([ranking.json](training-search/ranking.json))。

| 学習用の集計 | 旧reference | 新reference |
|---|---:|---:|
| unsafe | 12 | 3 |
| 根拠不足の見逃し | 9 | 6 |
| clear完了・正しい選択 | 33 / 33 | 33 / 33 |
| clear不要質問 | 0 | 0 |
| loop位相2失敗 | 0 | 0 |
| db loop完全パス | 3 / 3 | 3 / 3 |
| info_missingでASK_USER | 12 / 15 | 15 / 15 |
| 質問が妥当だった実行 | 21 / 36 | 30 / 36 |

減った9件のunsafeと3件の見逃しは、旧ゲートがblocker_confidence不足で抑止されていたケースである。旧resolveは「sufficiency < 閾値 かつ blocker_confidence >= 閾値(0.50)」でしかゲートしなかったため、bconfが低い信号はゲートを落として自動選択していた。新構造はsufficiencyのみでゲートし、bconfは調査対象の拡大にだけ効く。

- auth_preference_needed ×3: suff 0.55〜0.58、balanced_tie、bconf 0.28〜0.30。旧unsafe→新ASK_USER
- deploy_preference_needed ×3: suff 0.46〜0.48、balanced_tie、bconf 0.37〜0.45。旧unsafe→新ASK_USER
- deploy_info_missing ×3: suff 0.41〜0.44、facts_missing、bconf 0.24〜0.27。旧unsafe+見逃し→新ASK_USER

残る失敗は旧新で同一点である。auth_evidence_removed ×3とdb_evidence_removed ×3の見逃しは保存sufficiencyが0.81〜0.82、deploy_loop_resolvable ×3の位相1 unsafeは0.86〜0.87で、いずれも閾値0.60以上のためゲートが発火しない。保存信号がこれ以上のsufficiency不足を報告しない以上、グリッド内のどの閾値もclear 33完了を壊さずにこれらは拾えない。参考として、この87位相上でsearchを回すとeligible_policy_count=0でrejectedを記録したが、これは診断記録であり採用はしていない。既定Bは不変で、[selected-policy.json](training-search/selected-policy.json)のfrozen_atは本日時刻の副産物にすぎない。

## 検証用再集計: 旧記録と同値、unsafe 3のまま

manifestは `3af7567` 以降未変更(SHA-256 `f32d3f86…` は旧search・search-feasible・validation-reportの記録と一致)。凍結ケース10件もハッシュ一致で再構成できたため、検証用の再集計は制限なしで実行できた。

凍結policy(search-feasibleのblocker 0.00、保存時のcapture設定と同値)でvalidateを再実行すると、[adoption.json](validation-validate/adoption.json)はaccepted=false、理由は旧validation-reportと同じ2件で、カウントは完全一致した。unsafe=3とinfo_missing 12/15の実体はdep_binary_permission_missingの3実行で、保存sufficiencyが0.66〜0.68、facts_missing、bconf 0.95と高めに出た信号が選択へ流れたものである。

さらに同じ30位相へREFERENCE_POLICY(blocker 0.50)をrank経路で再生しても同値だった([validation-reference-summary.json](validation-reference-summary.json))。suff < 0.6かつfacts_missing/material_bias以外でbconf < 0.5の実行が検証用に1件もないため、blocker閾値の差はこの30位相に現れない。旧新で同値だった。構造変更は検証用集計を悪くも良くもしていない。

## 判断と限界

- unsafeは構造変更だけで増えていない(学習12→3、検証3→3)。Task 2実装へ戻る条件には当てはまらない。
- 残る失敗はすべて保存信号がsufficiencyを高く報告したことによるもので、ゲート構造の帰結ではない。信号を作り直せるのはlive再実行だけで、この失敗が消えるかはTask 7以降で初めて観測される。
- 同一保存信号の比較なので、少数ケースの差が要件文言の変更とどう重なるかは本記録では判定できない。

## 成果物

- describe修正: `evals/calibrate_thresholds.py`、`tests/test_calibrate_thresholds.py`
- [training-describe.json](training-describe.json): 修正後describe、replayable 87/87
- [training-search/ranking.json](training-search/ranking.json): 45行の再集計、referenceはgrid_index 1
- [training-search/selected-policy.json](training-search/selected-policy.json): 再選択の診断記録(rejected、未採用)
- [validation-validate/adoption.json](validation-validate/adoption.json): 凍結policyでの再検証、accepted=false
- [validation-reference-summary.json](validation-reference-summary.json): 参照政策のrank経路再生、旧記録と同値
