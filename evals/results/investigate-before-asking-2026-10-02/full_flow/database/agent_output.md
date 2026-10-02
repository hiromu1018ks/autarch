進行中の決定「notes-cli のメモデータの保存方式」を `/autarch` で解決しました。リポジトリの調査（README の「完全オフライン・シングルユーザー・単一プロセス」という明示的要件、pyproject.toml の依存ゼロ、cli.py の TODO）に加え、3方式それぞれが標準ライブラリのみ・ネットワークなしで動作することをローカルのスモークテストと Python 公式ドキュメントで検証した上で、決定状態を `./autarch-state.json` に構築し `decide.py` を実行して、その stdout をそのまま `./autarch-resolution.json` に保存しました。その結果、3案（SQLite / 単一JSONファイル / Markdownファイル）はいずれもハード制約を満たして適格と判定されましたが、エンジンの裁定は **ASK_USER**（rule: `evidence_insufficient`、blocker: `user_preference_unknown`、Jev confidence 0.81、evidence sufficiency 0.48）で、技術的証拠だけでは自動選択が支持されませんでした。評価は確率的には SQLite 方式に大きく傾いているものの（probabilities: SQLite 0.87 / JSON 0.09 / Markdown 0.04）、多基準の総合スコアでは SQLite 0.698 と Markdown 0.685 がほぼ手のひら返しで、残る決定要素はユーザーの優先順位です。skill の規定により、エンジンが ASK_USER を返した場合に私が選択を代行することはできません。

**Autarch は技術的評価だけでは決定できず、あなたの優先順位が決め手になります。**

決定の分かれ目は一点です。**メモデータを CLI を経由せず直接扱いたいか、どうか。**

- **A. SQLite（標準ライブラリ sqlite3）** — 破損耐性（トランザクション書き込み）と検索・索引を優先。データは CLI 経由でのみ読み書きする単一のバイナリ DB ファイル
- **B. Markdown ファイル（1メモ1ファイル）** — プレーンテキストとしての可読性・可搬性を優先。エディタ、grep、git でメモを直接閲覧・編集できる
- **C. 単一 JSON ファイル** — 実装は最小だが、書き込み安全性と検索は自前実装になる中間案（総合評価は3案中最低）

**メモを日常的にエディタや grep・git で直接扱いたいですか？（はい → B / いいえ・CLI だけで十分 → A）**
