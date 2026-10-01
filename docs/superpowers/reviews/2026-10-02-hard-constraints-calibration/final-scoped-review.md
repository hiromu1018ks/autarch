# Final scoped re-review

対象は最終全体レビューのImportant 1件と修正起因の影響、および保留していた認証の再評価・最終文書のみ。同一レビュー席で1回の限定再レビューを実施した。全体レビューは繰り返していない。基準HEADは `f4e8920`、修正は未commitの作業ツリーにある。

## Final code verdict

**ADDRESSED / Approved**。

- `evals/calibrate_thresholds.py:125` はsnapshotの型付きparsedを直接検証し、合法criterion/alternative IDの値をキー名ベースで伏せ字にしない。`_validate_parsed` のexact field集合、既知ID、数値型・範囲、Choiceの最大確率、blocker enumの検査は維持される。
- `evals/calibrate_thresholds.py:78` はChoice文字列単体に秘密パターン検査を限定し、従来のsecret-looking choice拒否を維持する。通常の `credential_fit`、`token_option` 等は通る。state、request、logの既存伏せ字は変更されていない。
- `evals/calibrate_thresholds.py:127` は検証後にdeepcopyし、resolveの返却値がsnapshotの確率dictを共有しない。以前のredactが担っていたコピー性を失っていない。
- `tests/test_calibrate_thresholds.py:25` からの回帰試験は4語×criterion/alternativeの8通りで、実際のparseを経たsnapshotと直接resolveの全resolutionを照合する。秘密値8箇所・余分なmetadata/ID5箇所の拒否、入力非変更、返却dict変更後のsnapshot非変更も確認する。
- 実際の2ファイルのgit diffが `final-fix-wave.diff` とバイト単位で一致することを確認した。

修正起因の新たな破損は見つからなかった。Critical 0 / Important 0 / Minor 0。RED 8 failed / 13 passed、focused 22 passed、全体638 passed / 3 skipped、diff-check exit0は実装者の実行報告として確認した。このレビューで再試験する具体的な疑義は残らず、suiteやliveを再実行していない。

## Task 8 evidence and documentation verdict

**Approved — 実施と失敗・留保の記録は仕様に適合。修正後のlive判断成功は未検証。**

- `full-flow-after-response-fix/full_flow_runs.jsonl:1` はauthenticationの1件だけで、status=failed、verdict=null、Claude exit1、181.1秒。`command-outcome.json` はrunner exit0と呼び出し1回を別に記録する。agent_outputのEAI_AGAIN文面とstate/resolution未生成を確認した。runnerの正常終了をモデル評価成功へ読み替えていない。
- `full-flow-after-response-fix/synthetic_replay.py` は元の保存stateを読み、固定helperの合成応答をparse/mainへ通す。send_requestをstubへ置換し、合成ログを別ディレクトリに限定する。合成parsedとresolutionのsnapshotは一致し、合法credential IDの3つのScoreが保持されている。
- `synthetic_replay_provenance.json` はprovider/agent呼び出し0件、合成数値、実fixtureに対するdecision_ok=falseを明記する。これをlive品質の改善や原評価の分母へ加算していない。
- `STATE.md:3`、root `notes.md:94`、`final/notes.md:207` と新ディレクトリのnotesは、原評価、runtime修正の617/3、後続replay修正の638/3を区別する。held-out棄却、既定値維持、unsafe8/69、deployment誤採用、元full-flow decision_ok2/3、根拠・条件必須化・調査経路・費用の留保も維持する。
- 原評価23ファイルについて、現ファイルのSHA256をmanifestと照合し、さらに `git show f4e8920:<path>` のバイト列と全件一致することを確認した。追記notesを除く原記録は変更されていない。

Critical 0 / Important 0 / Minor 0。API接続失敗は環境上の限界として明示されており、追加のlive再試行や品質成功の主張は承認対象にしていない。文書lintはsudachipy未導入で実行できず、手動確認したとの報告があり、製品試験の結果とは分離されている。

## Declined to judge

今回新たに範囲外として保留した挙動はなし。最初の全体レビューに記した意味検証器の追加と棄却後の再探索禁止の扱いは継続する。

## Final assessment

**Ready to merge? Yes — 現作業ツリーのコード品質・評価記録に関する承認。**

全体レビューの唯一のImportantは解消され、新しい指摘はない。Task8の再実行結果と報告は承認するが、修正後のlive認証判断はAPI接続失敗により未観測のままである。

`.git/worktrees/hard-constraints-calibration/index.lock` のread-only制限により、修正コード・評価記録・文書のcommitと統合は未完了。レビュー承認はcommit/merge完了やlive品質検証完了を意味しない。controllerは承認済み状態へ文書のレビュー待ち表記を更新し、書き込み可能な環境で既存の承認済み統合手順を完了する。
