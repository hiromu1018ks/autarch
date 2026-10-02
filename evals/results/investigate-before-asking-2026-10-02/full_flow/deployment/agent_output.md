## Autarch の実行結果

`decide.py`（モデル jev-latest）は `decision: ASK_USER` を返しました。ハード制約は登録されていないため 3 案すべてが適格（structured mode、除外なし）でしたが、エビデンス充足度が 0.31 と低く、ブロッカーは `user_preference_unknown`（確信度 0.49）、Jev の確信度は 0.73 でした。確率分布は managed_container_platform 0.82 / static_hosting_cdn 0.12 / self_managed_vps 0.06、基準別の複合スコアは static_hosting_cdn 0.681・managed_container_platform 0.6793・self_managed_vps 0.3276 と管理プラットフォームと静的ホスティングがほぼ同点で、技術的根拠だけでは自動選択できません。リポジトリの事実（`app.py` は 8080 番ポートで定数レスポンスを返す標準ライブラリのみのサーバ、`Dockerfile` は HEALTHCHECK・TLS なし、README は「どちらも予算可能・保守は 1 名で可能・on-call なし・強い希望はまだなし」）は取り込み済みで、`autarch-state.json` と `autarch-resolution.json` に保存しました。エンジンが ASK_USER を返したため、私が選択肢を決めることはせず、1 つだけ決め手となる質問を投げます。

**Autarch は技術的根拠だけでは決定できませんでした。** ブロッカーは事実の不足ではなく、チームの優先順位（どれだけの運用を自分たちで引き受けるか）です。README は「強い希望はまだない」と明示している通り、この軸だけが未確定です。

- **A. Managed Container Platform** — 既存の Docker イメージをそのまま預ける。保守・TLS・自動再起動はプラットフォーム側、費用は従量制
- **B. Self-Managed Virtual Server** — 小型 VM を自分たちで運用。定額で主導権は完全だが、OS パッチや TLS 更新は 1 名の保守に集中
- **C. Static Hosting behind CDN** — 定数レスポンスなので静的ページ化して CDN に置く。運用負荷はほぼゼロだが `app.py`/`Dockerfile` は実行体でなくなる

決め手はひとつです。**この status-page を今後も「動くサービス」として拡張する（他システムへの実際のヘルスチェックを追加する等）予定はありますか？** — 予定があるなら A、なくて運用ゼロを最優先なら C、インフラの主導権を優先するなら B となります。
