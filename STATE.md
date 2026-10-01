# Autarch 拡張開発の状態

評価基盤が完成し、現行版の baseline を 2026-10-01 に記録した。次は「情報不足の分類と一度の追加調査」の設計に入る。ファイルは節目ごとに更新する。

## 現在地: baseline 記録まで完了、拡張の設計が未着手

- 提案(`local-proposals/autarch-extension-proposal.ja.md`)の最初の実装段階が完了し、`main`(commit `87a336d`)に merge 済み。`origin/main` には未 push
- 評価インフラは `evals/` に一式(`case_schema` / `judging` / `run_fixed_state` / `run_full_flow` / `report_baseline`)。通常テストは 160 passed / 2 skipped(live 系2件は `AUTARCH_EVAL_LIVE=1` を指定したときだけ走る)
- baseline は `evals/results/baseline-2026-10-01/`(Jev 69回 + agent 5回の生記録、集計 `baseline.json`、日本語 `SUMMARY.md`、経緯メモ `notes.md`)
- 文書: spec が `docs/superpowers/specs/2026-10-01-eval-baseline-design.md`、実装計画が `docs/superpowers/plans/2026-10-01-eval-baseline.md`

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

1. **「情報不足の分類と一度の追加調査」の設計から始める**。brainstorming → spec → 実装計画の流れで。効果を見る指標は Appropriate Ask Rate・evidence_removed・Unsafe Auto-selection Rate の3つに決めてある
2. 続いて**必須条件の判定(採点前の除外)**を入れる。現行 baseline では違反候補の誤採用が 0 件なので、この拡張の効果は除外した結果の候補数の扱い(1候補以下になった場合の確認)側に出る見込み
3. 各拡張の後は**同じケースセット・シナリオで再実行**し、`baseline-2026-10-01/baseline.json` と比較する。指標の定義は `evals/judging.py` を流用して変えない
4. 再実行の前に片付ける小作業(いずれも半日以内の見込み):
   - 保留 Minor 7件の robustness pass。内容は(1)両 runner の subprocess timeout 未処理、(2)decide.py 出力不正時の分類を "unavailable" から "invalid" へ、(3)再集計が `runs_per_case` を見ず run 1〜3 だけ集計、(4)full-flow 指標の分母を judged 数ではなく5へ、(5)`environment.json` 欠落時の traceback を exit 2 へ、(6)workdir の skill symlink を相対 path へ、(7)`evidence_removed` で confidence 欠落を 0.0 扱いするのをやめる
   - `evidence_removed` の合格基準(ASK_USER または confidence < auto_select)の見直し。baseline の confidence 分布と突き合わせる
   - case set の見直し候補: database シナリオの「postgres 候補必須」の期待は、完全オフライン前提の fixture と噛み合わず、coverage を1シナリオ分だけ低く出している
5. `origin/main` への push(本日時点で16 commit 未反映)は任意のタイミングで

閾値(auto_select 0.85 等)の見直しは、拡張を入れた後のデータが揃ってからに手を付ける。現段階は confidence の分布を記録するだけにとどめる。

## 留意事項

- 評価の実行は `decide.py` 経由で `~/.autarch/decisions.jsonl` にも追記される(log path の指定はできない)
- baseline 再実行の費用感: 固定 state 69回は数分で終わる(Jev の応答が速い)。full-flow は1シナリオ2〜4分の agent 実行が5回
- full-flow の agent model は baseline 記録に残る。2026-10-01 baseline は sonnet
