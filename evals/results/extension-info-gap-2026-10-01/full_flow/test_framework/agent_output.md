Autarch は技術的評価だけでは確定できないと判断し、ユーザーに判断を委ねました(`decision: ASK_USER`)。オプションを選択することはしないでください、というエンジンの指示に従い、決定要因について確認します。

**決定要因は1つだけです:** pricing-service を「サードパーティ依存ゼロ」のポリシーで運用するつもりがあるかどうか。

- **A. pytest 維持(現状)** — 既存テスト・CI・README がそのまま動き、今後も pytest エコシステムを使える
- **B. stdlib unittest へ移行** — pytest の dev 依存を外して標準ライブラリだけで完結させるが、既存テストの書き換えと CI・ドキュメント更新が必要
- **C. pytest + プラグイン体制** — pytest を前提に pytest-cov / pytest-xdist 等を足して標準化するが、dev 依存が増える

**この方針(依存ゼロ主義)のご意向はどちらですか?** 「stdlib のみで運用したい」のであれば B、「pytest のままでよい」のであれば A または C に決まります。

---

**結果報告:** `/autarch` を実行し、リポジトリの証拠(pyproject.toml の dev extra `pytest>=8` とランタイム依存ゼロ、tests/test_pricing.py の pytest イディオム、README の「suite and onboarding docs assume pytest」、CI の `pip install -e .[dev]` → `pytest`)に基づいて3案(pytest 維持 / stdlib unittest への移行 / pytest + プラグイン体制)と5基準を含む決定ステートを `./autarch-state.json` に作成し、`decide.py` を実行しました。その結果は `human_preference` ルールの `ASK_USER`(confidence 0.99)でした。技術評価上は keep_pytest の composite が 0.8427 と最も高く、確率分布も keep_pytest 0.99 と圧倒的ですが、unittest への移行だけが依存フットプリント(1.0)とメンテナンス負荷(1.0)で優れるため、エンジンは「依存ゼロ方針という利用者の優先順位」を自動選択できず、利用者への確認を要求しました。したがって決定は未確定で、上記の1点(stdlib のみで運用する方針を持つか)への回答をいただければ確定します。なお、この回答を踏まえた再実行やオプション確定はエンジンの指示により行っていません。
