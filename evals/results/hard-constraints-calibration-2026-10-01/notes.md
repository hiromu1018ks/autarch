# Task 7: 学習記録を取得し、選択規則の修正をレビューへ渡した

必須条件トラックは21/21組が成功した。学習用は87/87位相、制約用は27/27位相を取得し、provider 障害・欠測・再試行は0件だった。旧選択規則の首位候補は学習条件を満たさず rejected。一方、下位18設定は学習条件を通過するため、controller の指示で条件を先に適用する選択規則へ修正した。修正後の実測探索と検証用実行は、レビュー待ちで未実施。既定値は変更していない。

## ケースと実行設定をモデル呼び出し前に固定した

結果ルートは `evals/results/hard-constraints-calibration-2026-10-01`。新規ディレクトリを使い、既存結果は上書きしていない。

検証用10ケースと manifest は `3af7567fa6595a69f84971ec9fc92721ef639cba` で凍結した。5対の決め手、確認済み側の選択、技術資料と架空の評価要件の区別は [design-notes.md](../../cases_calibration/metadata/design-notes.md) に記録した。期待値はモデル出力を見て変更していない。manifest はケースのバイト列 SHA-256、対の ID、題材、凍結日時を保存する。

B の設定は auto_select=0.85、review=0.60、min_gap=0.15、human_preference=0.70、sufficiency=0.60、blocker_confidence=0.50、human_first。モデル名は出力に記録された `jev-latest` で、背後の固定モデル名は返されていない。TYPESAFE_API_KEY と claude の存在を確認し、秘密値は保存していない。

| トラック | UTC開始〜終了（2026-10-01） | 所要時間 | decide実行 | モデル評価がある実行 | 結果 |
|---|---|---:|---:|---:|---|
| 学習用23ケース＋3 loopの全位相 | 11:22:18〜11:24:14 | 116秒 | 87 | 87 | 各ケース・位相3有効実行 |
| 独立した必須条件7ケース | 11:22:57〜11:23:28 | 31秒 | 27 | 9 | 21/21組 pass |

日本時間は各UTC時刻に9時間を加える。2段階制約ケースを含むため、27位相の判定単位は21組である。18実行は未確認条件、候補不足、不正根拠で採点前に停止した。Jev 成功時の evaluation_signals がある9件と、呼び出さない単体・runner試験を分けて確認した。latency は補助資料であり、非呼び出しの証明としては扱わない。

費用は確定できない。保存された応答に課金額や token usage はなく、96件のモデル評価に対応する実請求額は未取得。評価は既存仕様どおり `~/.autarch/decisions.jsonl` にも追記した。

## 旧記録は完全 replay が0件だった

[distribution.json](distribution.json) は第1拡張の保存済み87件から作成した。confidence、sufficiency、human_preference の欠測は0件。blocker は75件を復元できず unknown とした。全87件で evaluation_snapshot がないため replayable=0。旧派生ケース18件は situation が記録されていないので unknown/phase1 のまま表示し、意味を推測して補完していない。

evidence_removed の sufficiency は0.80〜0.84、clear は0.83〜0.93、loop位相2は0.80〜0.90。分布が重なることを示す記録であり、旧出力だけを使った正確な全政策比較は行っていない。

## 全体首位だけを選ぶ規則が通過候補を捨てていた

旧探索の [ranking.json](search/ranking.json) と [selected-policy.json](search/selected-policy.json) を保存した。旧首位は grid_index=72、sufficiency=0.90、blocker_confidence=0.00、auto_select=0.85、human_first。他の固定閾値はBと同じ。policyは `664bb4d` で凍結済みで、上書きしない。

| 学習用の集計 | B現行 | 旧首位 |
|---|---:|---:|
| unsafe | 12 | 0 |
| 根拠不足の見逃し | 9 | 0 |
| clear完了・正しい選択 | 33 / 33 | 9 / 9 |
| clear不要質問 | 0 | 24 |
| db loop完全パス | 3 / 3 | 0 / 3 |
| loop位相2失敗 | 0 | 8 |

不採用理由は clear completions decreased、clear correct selections decreased、db loop did not fully pass。auth_constraint_clearの3件はevidence_insufficientへ変わり、db loop位相2も選択に届かない。失敗例全件はpolicy内のfailuresに残した。

ただし「通過候補なし」ではない。90設定のうち下位18設定は学習条件を通過した。旧仕様解釈の「全体首位を一度選び、学習条件に抵触したら終了」が検証対象を失わせるため、controller は学習条件を可否制約として先に適用する順序を明示した。数値条件と同点規則は維持している。

修正 `046c680` は通過候補のうち辞書式で最も高いものを一つ選ぶ。通過候補なしなら rejected として全体首位の診断記録を残す。出力は selection.rule、eligible_policy_count、overall_rank を追加する。仕様§5と計画Task6/7に設計意図の明確化を記載した。検証用の結果による再選択は禁止のまま。

## 時刻検査と選択規則を失敗テストから修正した

凍結時刻の追加試験は18 failed / 4 passedを確認してから実装し、対象173 passed、全体590 passed / 3 skippedで `cb7db61` をcommitした。4 passedは既存のmanifest/case改変、異なる設定、3有効実行未満の拒否。最初の試験呼び出しはテスト内import不足を修正して再実行している。

manifestとpolicyのfrozen_atは、有効で未来でないタイムゾーン付きRFC3339を要求する。学習記録のrecorded_atはmanifest凍結後、policy凍結は学習記録後、検証記録はmanifestとpolicy双方の凍結後でなければ拒否する。ここで検査するのはrunnerが保存する記録時刻であり、第三者による日時の偽装まで保証しない。

選択規則修正は2 failedから開始し、対象175 passed、全体592 passed / 3 skippedを確認した。既存live試験3件は未指定の環境フラグによるskip。`git diff --check`も成功。新規runtime依存はなく、既存23ケース、loop期待値、judging.pyは変更していない。

レビュー後は同じ保存済み学習信号を別の新規out-dirで探索し、最終候補をcommitしてから検証用30実行へ進む。現時点のheld-outは0件、adoption.jsonは未作成、acceptedの最終判定も未確定。Task8の既定値更新はまだ許されない。
