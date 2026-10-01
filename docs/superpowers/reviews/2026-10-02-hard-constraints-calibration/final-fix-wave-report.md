# 合法IDのcaptureとreplayを一致させた

最終レビューのImportant 1件を修正した。credential、password、token、api_keyを含むcriterion/alternative IDの8通りで、captureしたsnapshotのreplay結果が直接resolveした結果と完全一致する。全体試験は638 passed / 3 skipped。コードの変更は`evals/calibrate_thresholds.py`と`tests/test_calibrate_thresholds.py`だけで、live呼び出しと再委任は0件。controllerの限定再レビューへ渡す。

Gitのindexはsandboxで読み取り専用だった。指定2ファイルの`git add`がexit128で失敗したためcommitは作成していない。エラーはPermission denied相当の書き込み制約で、実際の文面は`Read-only file system`だった。制約を迂回せず、差分を作業ツリーに残した。

## 伏せ字が構造上のIDを秘密欄と誤認していた

`final-branch-review.md`のCritical/Important/Minor全項目、`response-id-fix-brief.md`・report・review、progressのruling、承認済み設計と計画を確認した。対象は設計§5とTask4の「同じparse/resolve経路で正確に再判定」の契約である。最終レビューの修正対象はImportant 1件のみだった。

replayは`snapshot["parsed"]`を再帰的に伏せ字へ変えた後で検査していた。criterionの`credential_fit`はScoreのdict全体が`[REDACTED]`になり、alternativeの`token_option`は確率とScoreの数値が置換された。正常なparse/captureでもreplayだけがValueErrorになった。

修正では既存`_validate_parsed`へ元の型付き値を渡す。exact field集合、state由来の既知ID、数値型・有限値・範囲、Choiceと最大確率の一致、blocker enumの検査は維持した。検査後にdeepcopyしてresolveへ渡すため、返却した確率dictを呼び出し側が編集しても保存snapshotは変わらない。

従来のsecret-looking Choice拒否は、Choice文字列単体を`decide.redact`した結果との比較で維持した。known keyword IDはそのまま通り、`sk-...`のような秘密パターンはgenericなValueErrorで拒否する。globalのredact、state/request/logの処理、既定値、fixture、凍結済み閾値と採用判定は変更していない。

## 正常結果の一致と秘密値の拒否を検査した

新規21試験のうち8件は4語×criterion/alternativeの正常IDである。既存の`make_answers`、`answers_body`、`snapshot_for`を通した実際のparse結果を使う。directの`SELECT_OPTION / confidence / <既知候補ID>`を明示的に確認し、replayの全resolution、確率値、criterionのScoreを照合した。stateとsnapshotの非変更、返却dict編集後のsnapshot非変更も確認した。

残る13件は型付き数値6箇所・Choice・blockerへの合成秘密値8件と、snapshot/parsed/確率/criterion/候補Scoreへの余分なキー5件である。両IDを`credential_fit`と`token_option`にしたstateで、正常IDの保持と不正値の拒否を両立させた。いずれもValueErrorになり、例外文へ合成秘密値を含めず、入力を変更しない。既存のsecret-looking Choice identity拒否も成功した。

未信頼の自由文やmetadataを返す経路は追加していない。snapshotと各mapの集合を照合した後でのみ数値エラーのlabelへ既知IDを使う。余分なキー、未知Choice、未知enum、秘密文字列の数値はresolveへ到達しない。

## REDからGREENまでをオフラインで実行した

実行場所は`/home/misty/Projects/autarch/.worktrees/hard-constraints-calibration`。

```text
$ .venv/bin/python3 -m pytest tests/test_calibrate_thresholds.py -k 'captured_keyword_identifiers or rejects_secret_values or rejects_secret_metadata' --tb=short -q
8 failed, 13 passed, 175 deselected in 0.40s
exit 1
```

REDの8件はcriterionの4件で`parsed.scores[<keyword>_fit] must contain exactly the required fields`、alternativeの4件で`parsed.probabilities[<keyword>_option] is out of range [0, 1]`になった。レビューの再現と同じ原因である。security 13件は既存経路でも拒否され、成功した。先行して同じ選択条件を詳細traceback付きで1回実行し、8 failed / 13 passedを確認した。実装前のRED再実行はexit codeを直接保存するためで、コードはまだ変更していなかった。

```text
$ .venv/bin/python3 -m pytest tests/test_calibrate_thresholds.py -k 'captured_keyword_identifiers or rejects_secret_values or rejects_secret_metadata or secret_choice_identity' -q
22 passed, 174 deselected in 0.06s
exit 0

$ .venv/bin/python3 -m pytest
collected 641 items
638 passed, 3 skipped in 12.82s
exit 0

$ git diff --check
[outputなし]
exit 0

$ git add -- evals/calibrate_thresholds.py tests/test_calibrate_thresholds.py
fatal: Unable to create '/home/misty/Projects/autarch/.git/worktrees/hard-constraints-calibration/index.lock': Read-only file system
exit 128
```

全体試験は修正後に1回実行した。skipは既存live試験3件で、失敗した試験はない。diff-checkも成功した。自己レビューでChoice単体の秘密パターン拒否、検査順序、copy後のresolve、返却値の参照、例外文、変更範囲を確認した。並行して進んだ文書・評価記録の編集は触っていない。

日本語報告にはnatural-japaneseをクイックで使用した。`.venv/bin/python3 .agents/skills/natural-japanese/scripts/lint.py --json --genre tech <本report>`はexit1、`ModuleNotFoundError: No module named 'sudachipy'`で起動できなかった。依存やネットワークは追加せず、同skillの手動チェックリストと見出し・段落冒頭の通読で確認した。製品試験とは別の報告文検査の制限として残す。

## 限定再レビューとcommitが残る

今回のコード上の指摘は1件を対処し、未対処は0件。意味判断の品質、full-flowの実測、閾値の再選択は今回の範囲外で、元の留保を変更していない。新たな実装上の懸念は自己レビューで見つからなかった。controllerがこの指摘と修正起因の影響だけを確認し、承認後に書き込み可能な環境で指定2ファイルをcommitする。sandbox制約によるcommit未作成は上記のまま残る。
