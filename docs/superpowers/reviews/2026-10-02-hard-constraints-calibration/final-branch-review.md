# Final whole-branch review

対象: `ab8c61c..f4e8920`。設計・計画、progress.mdのruling、engine・評価コード・新規fixture・関連テスト・文書と保存評価記録を、最終独立レビューの同一レビュー席で確認した。product、index、HEADは変更していない。本ファイルのみレビュー成果物として作成した。

## Strengths

- `skills/autarch/scripts/decide.py:424` の事前検査は、原stateの検証、コピーの伏せ字と再検証、ID/参照の保持確認、違反候補除外、未確認条件による停止、候補数検査の順序が設計と一致する。違反とunknownの重複、単一候補、revision消費済みを区別し、採点前停止からproviderを呼ばないことをCLI/runner試験で確認している。
- `skills/autarch/SKILL.md` は必須条件と希望、verifiedとinference、legacy保証範囲、共通の一度だけのrevision、候補不足時の処理を明示する。通常ログは根拠本文やsnapshotを複製しない。
- `evals/calibrate_thresholds.py` は同じ保存信号を用いる90設定の比較、学習用の可否条件を先に適用する選択、manifest/policyの凍結時刻・hash・coverage検査、不完全な実行の不採用を実装する。学習用を見た選択規則の明確化とheld-out後の再調整禁止を混同せず、旧探索の記録も保存している。
- `evals/constraint_cases.py` と専用runnerは既存judgingと分母を分離する。ケースと位相の重複、欠落、provider障害を成功にしない。既存出力ディレクトリの上書きも防ぐ。
- 評価報告はheld-out候補の棄却、既定値維持、fixed unsafeの7/69→8/69、full-flowの観測不能と誤採用を明記している。新しい構造化条件の保証とモデル判断の品質を混同せず、旧期待値を緩めていない。
- `f4e8920` の応答処理は期待された型付き値のみを取り出し、自由文・未知metadataを保存せずに合法IDを維持する。secret値を含む数値欄の拒否も試験している。

## Issues

### Critical (Must Fix)

なし。

### Important (Should Fix)

1. **合法IDのsnapshotをreplay時の再帰的伏せ字が破壊する。**
   - 場所: `evals/calibrate_thresholds.py:123`。
   - `replay_resolution` は検証前に `decide.redact(snapshot["parsed"])` を実行する。`scores` のcriterion IDや `probabilities`/各scoreのoption IDは辞書キーなので、`credential_fit`、`token_option`、`password_*`、`api_key_*` のような合法IDの値が `[REDACTED]` へ変わる。
   - `f4e8920` により同じstateは正常にparse・resolve・captureできるため、保存した正常snapshotを同じ設定で再判定できない。設計§5とTask4の「同一経路で正確に再判定」の契約違反である。現行の固定fixtureの集計値は再現したが、実際に認証full-flowで現れた種類のIDを再評価へ持ち込むと失敗する。
   - 読み取り専用のオフライン再現: `_valid_state()` のcriterion IDを `credential_fit` に変更し `snapshot_for(state)` でcapture相当のsnapshotを作ると、directは `SELECT_OPTION / option_a`、replayは `ValueError: parsed.scores[credential_fit] must contain exactly the required fields`。alternative IDを `token_option` に変えると、directは `SELECT_OPTION / token_option`、replayは `ValueError: invalid parsed.probabilities[token_option] ... out of range [0, 1]`。
   - 修正: 型付きsnapshotの既知IDと数値に、自由形式のキー名ベース伏せ字を適用しない。期待されたフィールド・ID・数値の厳密検証と秘密値拒否を維持する。criterion/alternative両方のkeyword IDについてcapture→replayの一致を検証する回帰試験を追加し、既存のsecret-looking choice拒否試験も維持する。

### Minor (Nice to Have)

なし。

## Verification and limitations

- このレビューでは全suiteを再実行していない。controllerの `617 passed / 3 skipped` は実行報告として扱う。
- 上記の具体的なreplay疑義だけをオフラインで再現した。ネットワーク呼び出しなし。
- 保存済みtraining87件・validation30件を読み取り専用でreplayし、全件のdecision/rule/selected_optionが元記録と完全一致した。frozen policyとmanifestを検証し、validation集計とadoption判定が保存adoption.jsonと一致することを確認した。validation unsafe=3、候補はrejectedのままである。
- constraintsとfinal-constraintsを再集計し、両方とも保存summaryと完全一致: pass21 / fail0 / unavailable0 / incomplete0。
- `git diff --check ab8c61c..f4e8920` はexit0。
- 元の5 full-flowはavailable3/5、decision_ok2/3。live応答本文・全中間state・source取得履歴は未保存であり、取得事実の完全な独立検証はできない。認証のみの修正後再実行と最終文書は本レビュー作成時点で実行中。同一レビュー席で、その追加結果と文書を受領後に追記する。

## Declined to judge

- 出典の真偽・記載事実から条件適合への意味判断をengine単体で保証する拡張: 設計が入力契約と決定的な除外を保証範囲としているため、意味検証器の追加は今回の範囲外。full-flowで残る根拠の過剰一般化・条件の格上げは既存notesの留保として残す。
- 棄却後の閾値再探索、既存auth/deploy loop期待値の変更、full-flowの誤採用を理由とした追加調整: 凍結した検証設計で禁止されており、今回の修正提案には含めない。失敗結果の隠蔽や期待値緩和がないことは確認した。

## Recommendations

上記Importantを一つの修正波で解消し、capture→replayのID境界に絞った試験と既存の秘密値拒否試験を確認する。認証の修正後実測は原記録と別に保存し、成功・不成立・観測不能のいずれでもそのまま文書へ反映する。既存の棄却済み候補や原評価を上書きしない。

## Assessment

**Ready to merge? With fixes**

必須条件の採点前検査と凍結評価の主要部分は設計に沿うが、正常captureのreplayに実証済みの不一致があるため現状のままのmergeは承認しない。コード上の指摘は上記1件で全件であり、認証のみの再実測・最終文書の確認が残る。修正後はこの指摘と修正起因の影響だけを確認し、別の全体レビューは行わない。

## Final assessment after the single scoped re-review — 2026-10-02

上記の暫定「With fixes」を、以下の最終判断で更新する。同一レビュー席で `final-fix-wave.diff` の2ファイル、唯一のImportantと修正起因の影響、保留していた認証再評価・最終文書だけを確認した。詳細は `final-scoped-review.md`。

- **Final code: Approved / Important ADDRESSED。** typed parsedを直接検証し、IDキーを再帰伏せ字にしない。Choiceの秘密パターン拒否と検証後のdeepcopyを維持する。4語×2箇所のcapture→replay一致、秘密値・余分なmetadataの拒否、非変更性の回帰試験があり、報告はfocused22 passed、全体638 passed / 3 skipped、diff-check exit0。再レビューでsuiteやliveを再実行していない。
- **Task8 evidence/docs: Approved。** 認証の1回の再実行はEAI_AGAIN、Claude exit1、state/resolutionなし、failed/nullとして保存される。合成のparser経路確認は別記録で、decision_ok=falseと非liveである限界を明記する。原23ファイルはmanifestと基準commit f4e8920の両方へバイト単位で一致した。
- **Remaining findings: Critical 0 / Important 0 / Minor 0。** 修正起因の破損は見つからず、新しい範囲外保留もない。

**Ready to merge? Yes（現作業ツリーのコード品質と評価記録の承認）。**

修正後のlive認証判断は接続失敗により未観測という留保を維持する。git indexのread-only制限で修正と文書は未commit、統合も未完了であり、この承認はcommit/mergeやlive品質検証の完了を意味しない。controllerによる最終ステータス表記の更新と、書き込み可能な環境でのcommit・承認済み統合手順が残る。
