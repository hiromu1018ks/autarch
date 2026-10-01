# 必須条件の採点前検査と閾値検証の設計

日付: 2026-10-01
状態: 設計方針承認済み・本仕様はレビュー待ち
関連: `STATE.md`、`local-proposals/autarch-extension-proposal.ja.md`、第1拡張の仕様と評価記録

## 1. 必須条件への適合を確認してから比較する

目的は、必須条件に違反した候補や、適合を確認できていない候補の自動採用を防ぐこと。ユーザーは品質保証を最優先とし、方式の選択を委ねた。根拠付きの適合状況を agent が登録し、engine が検査・除外する方針と、閾値を別途検証する方針を承認した。

agent は条件と根拠を収集する。engine は入力契約と候補の適格性を決定的に検査する。Jev は適格な候補の比較を担う。agent の申告だけで除外する方式は根拠を検査できず、Jev に適合判定を委ねる方式は除外もモデル応答に依存するため採用しない。

保証の範囲は入力契約と処理の不変条件である。出典が正しいこと、記載した事実が実際に条件を満たすことは engine だけでは保証できない。agent の根拠収集手順、単体テスト、固定 state、full-flow の評価で補う。

今回の範囲は必須条件の入力、検査、除外、未確認条件の調査、出力とログ、評価、および閾値検証。閾値の既定値変更は検証に合格した場合に限る。方針保存、採用後フィードバック、分野別ガイド、無関係な整理は含めない。

## 2. 条件・根拠・候補別の確認結果を構造化する

state に任意の `hard_constraints` と `evidence_records` を追加する。既存の `known_constraints` と文字列配列 `evidence` は維持する。

```json
{
  "evidence_records": [
    {
      "id": "offline_doc",
      "fact": "This service requires a network connection for each query.",
      "source": "docs/provider-runtime.md:18",
      "checked_at": "2026-10-01T09:00:00Z",
      "kind": "verified"
    }
  ],
  "hard_constraints": [
    {
      "id": "offline",
      "description": "Must work fully offline.",
      "assessments": {
        "local": {"status": "unknown", "evidence_ids": []},
        "cloud": {"status": "violated", "evidence_ids": ["offline_doc"]}
      }
    }
  ]
}
```

両フィールドは存在する場合は配列とし、null は拒否する。`hard_constraints` が非空なら `evidence_records` も必須とする。例は追加フィールドのみを示しており、goal・question・alternatives など既存の必須項目は別途必要となる。

`kind` は `verified` または `inference`。`status` は `met`、`violated`、`unknown`。`evidence_ids` は重複のない文字列配列とする。各条件の assessments は元の全候補 ID を過不足なくカバーする。条件 ID と根拠 ID は既存 ID 規則に従い、それぞれの配列内で一意とする。

`fact`、`source`、`description` は空でない文字列。`checked_at` はタイムゾーン付き RFC 3339 の日時とする。出典はファイルと位置、公式文書の URL、または明示的なユーザー発言の識別子を記録する。推論は確認済み事実と分ける。engine は日時の形式を検査するが、出典を開いたり、鮮度を一律の日数で判定したりしない。agent は料金・提供機能など変動する情報を判断時に再確認する。

`met` と `violated` は、存在する `verified` 根拠を1件以上参照すること。推論だけの結論は `unknown` として登録する。`unknown` は空の参照または既存根拠の参照を許す。参照不明、重複 ID、根拠なしの断定、列挙外の状態、候補の欠落は不正入力として扱い、Jev を呼ばない。

agent は、明示された必須条件を `hard_constraints` に登録する。希望や優先順位は criteria に置く。厳守か不明ならユーザーの意図を確認し、勝手に必須条件へ格上げしない。構造化条件がない旧 state は従来経路を維持する。この互換経路には新しい除外保証がないことを文書と出力で示す。

## 3. 未確認条件を残したまま採点へ進まない

元の state を検証した後、送信前の伏せ字処理を適用し、条件の事前検査を行う。判定で使う ID と参照は伏せ字後も一致していることを再検査する。不一致なら不正入力として止める。元の state は変更しない。

候補ごとに、いずれかの条件が `violated` なら除外する。違反のない候補に一つでも `unknown` がある場合は比較全体を止め、Jev を呼ばず調査へ戻す。違反候補の未確認条件は調査の対象にしない。全条件が `met` の候補だけを適格とする。

| 検査結果 | decision / rule | 次の処理 |
|---|---|---|
| 違反のない候補に未確認条件あり・revision なし | ASK_USER / constraint_unverified | agent が一度調査する |
| 同じ状態・revision あり | ASK_USER / investigation_exhausted | 未確認条件を示して質問する |
| 未確認条件なし・適格候補が0または1 | INSUFFICIENT_OPTIONS / constraint_candidates_insufficient | 候補追加または条件確認へ戻す |
| 未確認条件なし・適格候補が2以上 | 既存の Jev 評価経路 | 適格候補のみ比較する |

未確認による停止を候補数判定より先に行う。調査で候補が適格になる可能性を、早期の候補不足判定で失わないためである。違反候補は state の alternatives と質問の選択肢・Score の両方から除く。評価用 state の assessments も残った候補に合わせる。Jev 応答の候補 ID は評価用 state に照合する。除外候補が返れば ProviderError とし、自動採用しない。

候補が1つになっても自動採用しない。候補が0または1のときは Jev を呼ばず、SKILL の候補不足分岐で別の候補を作れるか確認する。作れなければユーザーへ条件を確認する。再生成の自動反復は追加せず、制約の緩和には本人の指示が必要となる。

## 4. 調査枠と出力を既存の仕組みに接続する

`constraint_unverified` は `blocker_class=facts_missing` とし、未確認の条件 ID・候補 ID を出力する。これは engine の決定であり、Jev の確信度は付けない。既存 `revision` を共有し、条件確認と根拠不足調査を合わせて一度までとする。revision がすでに存在すれば新しい調査枠を与えない。

agent は未確認の条件を調べ、構造化根拠と適合状況を更新する。見つからなければ `unknown` を維持する。`revision.action=investigation` を設定し、一度だけ再実行する。本人の意図が必要と判明したら、追加調査を続けず答えやすい質問を一つ返す。既存の秘密情報除外と伏せ字は新しい根拠にも適用する。

出力には `constraint_check` を追加する。内容は `mode`（legacy / structured）、`eligible_option_ids`、`excluded_options`（候補 ID、違反条件 ID、根拠 ID）、`unknown_assessments`（候補 ID、条件 ID）。構造化条件が空の場合は structured とし、全候補を適格とする。legacy は項目不在の場合のみとする。

採点前停止時の Jev 関連値は null、probabilities と score_summary は既存の空出力に合わせる。既存 decision 値は増やさない。ログにも constraint_check を保存し、根拠本文の複製は避ける。新フィールドにも既存の再帰的伏せ字を適用する。Jev 障害は引き続き PROVIDER_UNAVAILABLE で、自動採用しない。

## 5. 閾値の検証は除外の効果と分ける

現行 `sufficiency=0.60` では evidence_removed の0.80〜0.84を捕捉できない。一方、db の調査後の成功例も0.82〜0.83なので、0.85へ上げるだけでは正常な再評価を止める可能性がある。confidence と sufficiency は異なる質問の出力であり、同じ数値の閾値を使う根拠にはならない。

保存済み出力はゲート不発時に blocker の生値を落としている。現記録から分布と影響候補は調べられるが、全ポリシーの正確な再実行はできない。新たに `evaluation_signals` を追加し、Jev 成功時の blocker_class と blocker_confidence を常に保存する。既存の行動指示用 blocker フィールドの意味は変えない。事前停止・provider 障害では evaluation_signals は null。評価用記録には、伏せ字後の Jev 応答から parse した値を丸めずに保存する。confidence・Choice の確率・human_preference・sufficiency・blocker・各 Score の値と実行設定を含め、同じ parse/resolve 経路で再判定する。表示用に丸められた score_summary から勝者を復元しない。秘密情報を含み得る未加工の応答本文は保存しない。

検証は次の順で進める。

1. 保存済み記録から、状況別の confidence・sufficiency・human_preference と loop 位相別の分布を報告する。復元できない blocker 値は欠測として扱う。
2. 学習用は既存23ケースと既存3 loop の各位相を各3回実行する。これと別の検証用ケースを、実行前に固定する。検証用は5題材それぞれに「根拠不足」と「決め手を確認済み」の対を1組、計10ケース用意する。既存ケースの単なる語句置換は避け、別の決め手を使う。期待値はモデル出力を見る前に確定する。
3. B の現行設定で生信号を取得する。provider 障害は欠測として除外し、ケースごとの評価可能件数を示す。採用判定には各ケース3件の有効実行を必要とする。候補グリッドは sufficiency={0.60,0.75,0.80,0.85,0.90}、auto_select={0.85,0.90,0.95}、blocker_confidence={0.00,0.50,0.70}。review=0.60、min_gap=0.15、human_preference=0.70 は固定する。
4. 同一の生信号に対して現行順序と「根拠充足性ゲートを human_preference より先に置く順序」を比較する。先行ゲートは調査ループを起こす一方、意向確認を遅らせ得るので、preference_needed と full-flow の経路も検査する。
5. 学習用で選んだ一つの設定を凍結し、検証用を各3回実行する。検証用で調整を繰り返さない。失敗したら既定値を維持し、失敗結果を報告する。

選択は辞書式に行う。第一に unsafe の件数、第二に根拠不足ケースの見逃し件数、第三に loop 位相2で期待された選択に到達しない件数、第四に明確なケースの不要な質問件数を最小化する。同点なら変更する既定値が少ない設定を選び、なお同点なら現行順序、現行値との差が小さい設定を優先する。グリッドの記載順を最終の同点規則とする。

採用条件は、同一ケースの現行設定との比較で unsafe が増えず、根拠不足の見逃しが減り、constraint_clear の完了件数と正しい選択件数が減らず、db loop の完全パスを維持すること。検証用では unsafe 0件、根拠不足への適切な ASK_USER と確認後の正しい選択が各15/15であること。少数ケースの合格を一般的な品質保証とは呼ばず、件数・失敗例・モデル名・日時を併記する。

## 6. 比較可能性を保って品質を検証する

単体テストでは、不正な参照、根拠のない met/violated、推論のみ、全候補違反、1候補残存、未確認、複数条件、違反と未確認の重複、revision 済み、旧 state の互換性を検査する。高 confidence や高 Score が事前検査を迂回できないこと、除外候補がリクエストに残らないこと、伏せ字後の参照、ログと出力、ProviderError も確認する。

新しい必須条件ケースは独立の評価トラックに置く。2候補以上の適格候補が残る例、1候補・0候補、未確認から解決する2段階、解決しない2段階、推論だけを根拠にした不正入力を含める。題材は実行環境と既存構成への適合を中心にし、費用は日時付き根拠の検査例として扱う。全ケースを各3回実行する。

既存 `judging.py` の指標定義と23ケースは変更しない。候補不足を invalid に数える既存集計のまま新ケースを混ぜると意味が変わるため、新トラックは独立に事前検査の期待値、除外 ID、Jev 呼び出し有無、2段階の結果を集計する。非呼び出しは単体・runner テストで検証し、live 記録では出力と latency を補助情報として残す。

既存 auth/deploy loop の期待値を後付けで緩めない。新しい検証用の対を追加し、既存ケースの限界は記録する。full-flow は新 SKILL に沿った state の生成、必須条件の取りこぼし、根拠、調査経路、選択結果を確認する。主観的な確認と機械判定を分けて報告する。

効果を分離するため、A=現行記録、B=必須条件拡張＋現行閾値、C=B＋採用候補の閾値・順序として比較する。旧23ケースは A/B の互換性検査、新トラックは B の除外保証検査、検証用の対は B/C の閾値検査を担う。最後に既存23ケースと5 full-flow を再実行し、第1拡張の baseline と比較する。費用・provider 障害・不完全な実行は留保に残す。

## 7. 実装境界と引き継ぎ

`skills/autarch/scripts/decide.py` に schema 検査と、入力を変更しない候補検査の純粋関数を追加する。main は事前検査後の state を build_request / parse_answers / resolve に渡す。SKILL.md は条件登録・根拠確認・新停止理由の分岐を追加する。評価コードには独立トラック、生信号の取得とポリシー比較を追加する。runtime の依存追加は不要とする。

通常の全テスト、新トラック、生信号の検証、閾値の検証用評価、既存評価との比較を完了したら STATE.md を更新する。採用条件を満たす閾値がなければ既定値を変更せず、次に必要な質問形式や材料の改善を記録する。

本仕様の承認後に writing-plans で実装計画を作成する。計画のレビューと実行方法の選択を経て実装に入る。本仕様の作成段階では product code と閾値を変更しない。
