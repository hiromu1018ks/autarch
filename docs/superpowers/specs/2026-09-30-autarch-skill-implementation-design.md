# Autarch Skill 実装設計

**日付:** 2026-09-30
**ステータス:** Approved（設計レビューでの修正指示を反映）
**関連文書:** `docs/Autarch_requirements_v0.2.md`（要件定義書 v0.2）

---

## 1. 方針

- 要件定義書に含まれる機能を今回の実装で完了させる。「MVPだから省略する」「後で追加する」は適用しない。対象: Choice / Score / Noul、汎用 Core、secret redaction、decision logging、error handling、input / response validation、human preference 判定のすべて。
- 最終判定は Agent の自由判断に委ねず、`decide.py` がコードとして決定的に処理する。
- Core（`decide.py`）は分野非依存とする。Coding 固有の語彙・知識（package.json, Git, database, authentication 等）をコードに埋め込まない。

### Dependencies

```text
Runtime dependencies:
- Python 3.10+
- stdlib only

Development / test dependencies:
- pytest
```

配布される Skill 自体は外部 Python package に依存しない状態を維持する。

---

## 2. 全体構造

```text
autarch/
├── .claude/skills/autarch -> ../../skills/autarch   # symlink（開発中の /autarch 認識用）
├── skills/autarch/
│   ├── SKILL.md
│   └── scripts/
│       └── decide.py
├── tests/
│   ├── test_decide.py        # ネットワークなしの全経路テスト
│   └── test_live.py          # 実API結合テスト（明示的live指定時のみ）
└── docs/
```

- 実装開始前に `git init` する。
- `.claude/skills/autarch` は相対 symlink でコミットする。リポジトリを clone した環境でも `/autarch` が認識される。
- 配布形式は `skills-lock.json` の規約（GitHub リポジトリの `skills/<name>/SKILL.md`）に合致する。

---

## 3. 呼び出し仕様 — 明示実行のみ

`SKILL.md` の frontmatter:

```yaml
---
name: autarch
description: Resolve a decision by generating alternatives and evaluating them with Jev.
disable-model-invocation: true
---
```

自動発動は禁止。ユーザーが明示的に `/autarch` を実行した場合のみ動作する。Agent が自己判断で発動することはない。

---

## 4. Decision State Schema

`decide.py` の入力。Agent が SKILL.md の手順に従って構築し、ファイルに書き出す。

```jsonc
{
  "goal": string,                   // 必須。ユーザーの当初目的
  "question": string,               // 必須。正規化した Decision Problem
  "known_constraints": [string],    // 任意。省略時 []
  "environment": object | string,   // 任意。実行環境等の補足情報
  "evidence": [string],             // 任意。省略時 []。収集した根拠（各1項目=1文字列）
  "alternatives": [Alternative],    // 必須。2〜5件
  "criteria": [Criterion]           // 任意。0〜8件。省略時は Choice 単独評価
}
```

### Alternative

```jsonc
{
  "id": string,               // 必須。一意・非空・64文字以内
  "name": string,             // 必須
  "description": string,      // 必須
  "advantages": [string],     // 任意
  "disadvantages": [string],  // 任意
  "assumptions": [string]     // 任意
}
```

### Criterion

```jsonc
{
  "id": string,          // 必須。一意・非空・64文字以内
  "name": string,        // 必須
  "weight": number,      // 任意。>= 0。省略時 1.0
  "rubric": [string]     // 必須。2件以上。順序付きで、index が score level（0=最低）
}
```

### id の共通制約

`id`（alternative / criterion とも）は Jev の question 名・criteria キーに埋め込まれるため、次の制約を課す:

- 正規表現 `^[A-Za-z0-9][A-Za-z0-9._-]*$` に一致すること（改行・空白・制御文字を含まない）
- 64文字以内
- `__`（二連アンダースコア）を含まないこと（question 名 `score__<crit>__<opt>` の区切りと衝突しないため）
- 同一 state 内で重複しないこと

### 評価軸の扱い

- schema に挙げた以外の未知のキーは拒否せず、そのまま state object に含めて Jev へ送信する（redaction は state 全体へ適用されるため安全である）。
- 評価軸は Agent が質問と context から生成する（SKILL.md Step 5）。Coding 固有の軸を Core は強制しない。
- `weight` が省略された criterion は weight 1.0 として扱う。全 criterion が省略なら実質的に等ウェイトになる。weight は正規化してから使用する。
- criteria が空（省略）の場合、Score 評価と Choice/Score 整合性チェックは実行せず、Choice 単独で判定する（§8）。

---

## 5. Jev Request 構築

- Endpoint: `POST https://api.typesafe.ai/v1/systemone`（`--endpoint` で上書き可）
- 認証: `Authorization: Bearer $TYPESAFE_API_KEY`
- `state` は **object のまま渡す**（JSON 文字列化しない）。TypeSafe の `SystemOneRequest.state` は string / object / array を直接受け付ける。
- 1リクエストに全質問（Noul 1件 + Choice 1件 + Score `|criteria| × |alternatives|` 件）を混在させる。
- timeout は `--timeout`（デフォルト30秒）。リトライはしない。1回だけ送信し、失敗はすべて `PROVIDER_UNAVAILABLE` として扱う。

### questions

```jsonc
{
  "requires_human_preference": {
    "type": "noul",
    "instructions": "Does resolving this decision require the user's personal preference, business intent, subjective taste, or value judgment?"
  },
  "best_option": {
    "type": "choice",
    "instructions": "Select the option that best satisfies the goal and constraints.",
    "criteria": {
      "<alternative.id>": "<name>: <description>"
    }
  },
  "score__<criterion.id>__<alternative.id>": {
    "type": "score",
    "instructions": "How well does the option '<alternative.name>' satisfy the '<criterion.name>' criterion?",
    "criteria": [ "<rubric の level 説明を昇順に>" ]
  }
}
```

- Choice の `criteria` は alternative の id → `"{name}: {description}"` のマップ。
- Score は criterion × alternative の全組み合わせで1質問ずつ生成する。

---

## 6. Jev Response 解析・検証

期待する response は `{ "model": string, "answers": { <question name>: answer }, "usage": {...} }`。

次の検証を順に実施し、**いずれかに違反したら `PROVIDER_UNAVAILABLE`** として安全側に倒す（§8 手順1）:

| # | 検証 |
|---|---|
| R1 | HTTP status が 2xx であること（違反時は status code を detail に含める） |
| R2 | response body が JSON として parse できること |
| R3 | `answers` が存在し object であること |
| R4 | `answers.requires_human_preference` が存在し、`type == "noul"`、`noul` が数値で `0 <= noul <= 1` |
| R5 | `answers.best_option` が存在し、`type == "choice"`、`choice` が alternative id に存在、`confidence` が数値で `0 <= confidence <= 1`、`probabilities` が**全 alternative id を含み**各値が `0 <= p <= 1`、かつ `probabilities[choice]` が全確率の最大値と一致すること |
| R6 | 各 `score__*` answer が存在し、`type == "score"`、`score` が数値で `0 <= score <= len(rubric) - 1`、`confidence` が `0 <= confidence <= 1`、`probabilities` のキーが rubric index（`"0"`..`"N-1"`）と完全一致すること |

- `probabilities` への厳格な完全キー要求は意図的なものである。API が期待する形を返さない場合、判定の根拠が不完全なので自動決定しない。
- detail には HTTP status・例外クラス名・違反した検証番号のみを含め、秘密や response 全文は含めない。

---

## 7. Secret Redaction

適用順序:

```text
parse JSON (exit 2 on malformed)
  ↓
input validation (§11) — 構造検証は値の中身に依存しないため raw に対して実施
  ↓
recursive key-based redaction（Python object 上で）
  ↓
string-value pattern redaction（object 内の全 string 値に再帰適用）
  ↓
JSON serialization
  ↓
Jev API へ送信
```

### Key-based redaction

dict を再帰走査し、キーを「lowercase + `-`/空白を `_` に正規化」した文字列が、sensitive term を**部分文字列として**含む場合、その値全体（型を問わず）を `"[REDACTED]"` に置換する。部分一致採用は意図的で、`db_password` のような複合キーを取りこぼさないためである（`tokenizer` 等の偽陽性は安全性優先で受け入れる）。

sensitive terms:

```text
password
passwd
token
access_token
refresh_token
api_key
apikey
secret
private_key
authorization
credential
credentials
```

### String pattern redaction

string 値（および配列要素の string）に再帰適用する正規表現:

```text
sk-[A-Za-z0-9_-]{8,}
ghp_[A-Za-z0-9]{20,}
github_pat_[A-Za-z0-9_]{20,}
AKIA[0-9A-Z]{16}
Bearer [A-Za-z0-9._~+/=-]{15,}
-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----
(?i)(password|passwd|token|api_key|secret)\s*[=:]\s*\S+
```

最後のパターンは `password=` / `token:` 等の「key=value 形式」の値部分を `"[REDACTED]"` に置換する。

### 出力の制約

- redaction 件数のみ stderr に出力する（例: `redacted: 3 value(s)`）。
- 実値は `stdout` / `stderr` / decision log / exception text のいずれにも出さない。HTTP 例外の message には Authorization header の値が含まれないことを確認のうえ、status と例外クラス名のみ detail に使う。
- log 用の `sanitized_question` にも string pattern redaction を適用し、500文字で打ち切る。

---

## 8. Resolution Engine

判定は次の順序で、すべてコードが決定的に実行する。上位ルールが下位を上書きする。

### 手順 0 — Input validation

state の検証（§11）に失敗した場合: `INSUFFICIENT_OPTIONS`（rule=`invalid_state`）。API 呼び出し前に判定する。

### 手順 1 — Provider error

§6 の検証 R1〜R6 のいずれか、または API key 未設定（`TYPESAFE_API_KEY` が空）に該当する場合: `PROVIDER_UNAVAILABLE`（rule=`provider_error`）。**自動選択しない。**

### 手順 2 — Human preference gate

`requires_human_preference.noul >= --human-preference`（デフォルト 0.70）の場合: `ASK_USER`（rule=`human_preference`）。Choice / Score が高 confidence でもこの判定を上書きしない。

### 手順 3 — Choice winner

`answers.best_option.choice` を Choice winner とする。

### 手順 4 — Score winner（criteria がある場合）

各 criterion の期待スコア（response の `score`）を次で [0,1] に正規化する:

```text
norm = score / (len(rubric) - 1)
```

重み付き合成スコア（weight は総和で正規化）:

```text
composite(option) = Σ_i (w_i × norm_i(option)) / Σ_i w_i
```

`composite` が最大の候補を Score winner とする。最大値を持つ候補が複数（厳密な同点）で一意に決まらない場合は不一致扱いとする。正規化後の weight 総和が 0 になる場合（全 criterion が `weight: 0`）は等ウェイトへフォールバックする。

### 手順 5 — Choice / Score consistency

criteria があり、Choice winner ≠ Score winner の場合: `ASK_USER`（rule=`choice_score_disagreement`）。自動でどちらかを採用しない（安全側）。

criteria がない場合はこの手順をスキップする。

### 手順 6 — Probability gap

Choice の `probabilities` を降順に並べ、1位と2位の差を計算する:

```text
gap = p1 - p2
gap < --min-gap (デフォルト 0.15) → ASK_USER (rule=probability_gap)
```

### 手順 7 — Confidence

```text
confidence >= --auto-select (0.85) → SELECT_OPTION
confidence >= --review      (0.60) → SELECT_OPTION_WITH_CAUTION
confidence <  --review      (0.60) → ASK_USER (rule=low_confidence)
```

`SELECT_OPTION` / `SELECT_OPTION_WITH_CAUTION` の `selected_option` は Choice winner とする。

---

## 9. 出力契約（stdout / stderr / exit code）

### stdout

常に machine-readable な**1個の JSON object のみ**。人間向けの文言・ログを混ぜない。人間向け表示は Agent が SKILL.md の指示に従って組み立てる。

resolution JSON schema:

```jsonc
{
  "decision": "SELECT_OPTION | SELECT_OPTION_WITH_CAUTION | ASK_USER | PROVIDER_UNAVAILABLE | INSUFFICIENT_OPTIONS",
  "rule": "confidence | human_preference | choice_score_disagreement | probability_gap | low_confidence | provider_error | invalid_state",
  "selected_option": "alternative id | null",
  "confidence": 0.94,                      // best_option の confidence。未取得なら null
  "probability": 0.87,                     // selected_option の choice_probability。未取得なら null
  "probabilities": { "id": 0.87, ... },    // 候補ごとの choice_probability。未取得なら null
  "human_preference_probability": 0.12,    // noul 値。未取得なら null
  "score_summary": {                       // criteria がない、または未取得なら null
    "<option id>": {
      "<criterion id>": 0.75,              // 正規化済み期待スコア
      "composite": 0.68
    }
  },
  "reason": "短い判定理由",
  "detail": "PROVIDER_UNAVAILABLE 等の詳細。秘密を含まない",  // 通常 null
  "model": "jev-latest"
}
```

### 用語 — probability は分布であり点数ではない

`probability`（内部呼称 `choice_probability`）は候補集合内の確率分布であり、総和がおおよそ1になる。各候補の独立した点数（「72点」「24点」）ではない。候補単体への複数軸評価は Jev Score（`score_summary`）が担う。SKILL.md にもこの解釈を明記する。

### stderr

次のもののみを出す（秘密値は絶対に出さない）:

- redaction 件数
- diagnostic message / warning（例: decision log への書き込み失敗）
- internal error の内容

### exit code

```text
0:  resolution JSON を正常に生成した場合。
    SELECT_OPTION / SELECT_OPTION_WITH_CAUTION / ASK_USER /
    PROVIDER_UNAVAILABLE / INSUFFICIENT_OPTIONS のすべてが該当する。
    PROVIDER_UNAVAILABLE は Autarch として正常に処理された resolution なので exit 0。

2:  CLI usage error / state-file 不存在 / malformed input JSON。
    診断は stderr に出し、stdout には何も出さない。

1:  想定外の internal error。
    例外クラス名を stderr に出し、stdout には何も出さない。
```

---

## 10. Decision Log

`~/.autarch/decisions.jsonl` に1 decision = 1行で追記する（ファイルがなければ作成）。

```jsonc
{
  "timestamp": "2026-09-30T12:34:56Z",     // ISO 8601 UTC
  "sanitized_question": "...",             // redaction 済み・500文字上限
  "option_ids": ["sqlite", "postgresql"],
  "criteria_ids": ["requirement_fit", "simplicity"],
  "score_summary": { ... },                // §9 と同型。null 可
  "choice_probabilities": { "id": 0.87 },
  "choice_confidence": 0.94,
  "human_preference_probability": 0.12,
  "resolution": "SELECT_OPTION",
  "model": "jev-latest",
  "latency_ms": 812                        // HTTP request の所要時間
}
```

- state 全文は保存しない。秘密は一切残さない。
- `INSUFFICIENT_OPTIONS` / `PROVIDER_UNAVAILABLE` も記録する（取得済みの値のみ。未取得は null）。
- ログ書き込みに失敗しても resolution には影響させず、warning を stderr に出すだけとする。

---

## 11. Input Validation

state parse 後、API 呼び出し前に次を検証する。**候補構造の不正はすべて `INSUFFICIENT_OPTIONS`**（exit 0, rule=`invalid_state`）。state JSON 自体の破損・CLI 使用ミス（ファイル不在・JSON として不正）は exit 2 で別扱いする。

検証項目:

```text
state が object であること
goal が存在し string であること（空文字不可）
question が存在し string であること（空文字不可）
alternatives が存在し array であること
alternatives が 2〜5 件であること
各 alternative:
  id が存在し、§4 の id 制約を満たすこと（非空・正規表現・64文字以内・__ を含まない）
  id が重複していないこと
  name が存在し string であること
  description が存在し string であること
criteria が存在する場合:
  criteria が array であり 0〜8 件であること
  各 criterion の id が存在し §4 の id 制約を満たし重複がないこと
  name が存在すること
  weight が存在する場合は数値かつ >= 0 であること
  rubric が array かつ 2 件以上であること
```

- rubric を「2件以上」とするのは、1件の rubric では `norm = score / (len-1)` が定義できないため（順序付き評価として意味をなさない）。
- 違反時の `detail` には検証項目名のみを含める（値は含めない）。

---

## 12. CLI 仕様

```bash
python3 skills/autarch/scripts/decide.py \
  --state-file /tmp/autarch-state.json \
  [--model jev-latest] \
  [--auto-select 0.85] \
  [--review 0.60] \
  [--min-gap 0.15] \
  [--human-preference 0.70] \
  [--timeout 30] \
  [--endpoint https://api.typesafe.ai]
```

- API key は環境変数 `TYPESAFE_API_KEY` のみから読む。`~/.bashrc` 等で export する運用とする。
- `--state-file` は必須。`--endpoint` は live テストや将来的な互換 endpoint のために用意する。

---

## 13. SKILL.md 実行フロー

frontmatter（§3）に続き、次の Step 1〜13 を Agent への指示として記述する。

```text
Step 1  現在ユーザーが判断を求められている質問を特定する
Step 2  質問を明確な Decision Problem へ正規化する
Step 3  2〜5個の materially different / feasible / neutral な候補を生成する
Step 4  判断に必要な context / evidence だけを収集する
Step 5  候補を比較するための評価 criteria を生成する
Step 6  state JSON を書き出す
Step 7  decide.py を実行する
Step 8  resolution JSON を読む
Step 9  SELECT_OPTION なら選択肢を採用して元の Agent 作業を続行する
Step 10 SELECT_OPTION_WITH_CAUTION なら不確実性を短く明示した上で採用して続行する
Step 11 ASK_USER なら専門的な元質問をそのまま返さず、
        ユーザー本人にしか答えられない最小質問へ変換する
Step 12 PROVIDER_UNAVAILABLE なら Jev による判断ができなかったことを明示し、
        勝手に候補を採用しない
Step 13 INSUFFICIENT_OPTIONS なら候補生成をやり直すか、
        候補を構成できない理由をユーザーへ返す
```

### SKILL.md に必ず含める制約指示

**中立な候補生成（Step 3）:**

```text
Generate alternatives neutrally.

Do not describe any option as recommended, best, preferred,
safer, simpler, superior, or inferior before Jev evaluation
unless that statement is directly established by evidence.

Describe every alternative using the same structure and
comparable level of detail.
```

候補は全て同一 schema（id / name / description / advantages / disadvantages / assumptions）で、同等の詳細度で記述する。

**秘密を含めない（Step 4）:**

```text
Do not read or include .env files, credential files,
private keys, authentication tokens, or secret stores
as evidence.
```

**用語（Step 8）:** `probability` は候補集合内の確率分布であり点数ではない。これを「72点」のように解釈して説明しない。

**ASK_USER の形式（Step 11）:** 元の質問（例: 「JWTとSession Cookieどちらにしますか？」）をそのまま返してはならない。Autarch が得た Score / Choice / evidence を使い、違いを決める軸を1つに絞った、専門知識がなくても答えられる最小質問へ変換する（要件定義書 §10 の UX 原則に従う）。

**実行（Step 7）:** `decide.py` の exit code が 0 以外（usage error / internal error）の場合は、判断を捏造せず、Autarch の実行に失敗したことをユーザーへ伝える。

---

## 14. 汎用性の維持

- `decide.py` のコード・文字列定数に Coding 固有の語彙・ロジックを出さない。Core が扱うのは Generic Decision State（§4）のみ。
- Coding 固有の情報（repository, package.json, dependencies, tests 等）は SKILL.md の Step 4 で Agent が context / evidence として収集するものであり、コードは関知しない。
- この構成により、旅行・商品比較・SaaS 選定・業務判断でも、SKILL.md の収集指示を差し替えるだけで同じ `decide.py` が使える。

---

## 15. テストマトリクス

`tests/test_decide.py` は `urllib.request.urlopen` を monkeypatch し、API key・ネットワークなしで全経路を検証する。

### 正常系

| ケース | 期待 |
|---|---|
| 高 confidence・高 gap・整合 | `SELECT_OPTION` |
| confidence 0.60〜0.85 | `SELECT_OPTION_WITH_CAUTION` |
| confidence < 0.60 | `ASK_USER` (low_confidence) |
| gap < 0.15 | `ASK_USER` (probability_gap) |
| noul >= 0.70 | `ASK_USER` (human_preference) |
| Choice winner ≠ Score winner | `ASK_USER` (choice_score_disagreement) |
| criteria なし | Choice 単独で判定（整合チェック無効） |
| 重み付き composite の計算 | 数値が仕様どおり |

### Provider 系（すべて `PROVIDER_UNAVAILABLE`, exit 0）

```text
API key なし
HTTP 401 / 422 / 429 / 5xx
timeout
network error
malformed JSON
answers field なし
必要な question answer なし
不正な answer type
```

### Response validation（すべて `PROVIDER_UNAVAILABLE`）

```text
choice が alternative に存在しない
confidence < 0 / confidence > 1
probability < 0 / probability > 1
probability key 欠落（alternative の一部が probabilities に無い）
probabilities[choice] が最大値でない
Score response 不正（範囲外 / rubric index 不一致）
Noul < 0 / Noul > 1
```

### Input validation（すべて `INSUFFICIENT_OPTIONS`, exit 0）

```text
alternatives 0件 / 1件 / 6件
duplicate option IDs
empty option ID
id に制約違反文字（空白・__ 等）
name 欠落 / description 欠落
criteria schema 不正（weight 負 / rubric 1件 / id 重複）
```

### CLI・入力破損（exit 2）

```text
state-file 不存在
malformed state JSON
必須引数欠落
```

### Redaction

```text
sensitive key（db_password, apiKey, PRIVATE_KEY 等）
sk- / ghp_ / github_pat_ / AKIA / Bearer token / PRIVATE KEY block
password= / token: 形式
nested object / nested array
送信 body に実値が含まれないこと
stdout / stderr / log に実値が含まれないこと
redaction 件数が stderr に出ること
```

### その他

```text
decision log への追記（sanitized_question の redaction と500文字打ち切りを含む）
log 書き込み失敗時に resolution が影響を受けないこと
exit code 契約（0 / 2 / 1）
stdout が単一 JSON であること
```

---

## 16. Live 結合テスト

- `tests/test_live.py` に分離する。
- 環境変数 `AUTARCH_LIVE=1` かつ `TYPESAFE_API_KEY` が設定されている場合のみ実行し、通常の `pytest` 実行では skip する。
- 実 API に1リクエスト送信し、response 検証・resolution 生成・decision log 追記が完結することを確認する。
- live テストは小さな state（alternatives 2件・criteria 1件）でコストを抑える。

---

## 17. 決定事項の一覧（曖昧さの残存確認）

本設計で確定させた事項:

```text
state schema / criteria schema ............ §4
id 制約 .................................. §4（正規表現・64文字・__ 禁止・一意）
Jev request schema ....................... §5（state は object のまま・質問混在）
Noul / Score / Choice question 生成 ...... §5（instructions 文面を固定）
weighted score 計算 ...................... §8（norm = score/(len-1)、weight 正規化）
Choice/Score consistency rule ............ §8 手順5（不一致は ASK_USER）
human preference threshold ............... --human-preference 0.70、noul >= で ASK_USER
confidence rule .......................... §8 手順7（0.85 / 0.60）
probability gap rule ..................... §8 手順6（gap < 0.15 で ASK_USER）
resolution states ........................ 5状態 + rule の列挙（§9）
input validation ......................... §11
response validation ...................... §6（R1〜R6）
redaction algorithm ...................... §7（key 部分一致・regex 一覧・件数のみ報告）
logging schema ........................... §10
exit codes ............................... §9（0 / 2 / 1）
SKILL.md execution flow .................. §13（Step 1〜13・中立生成・秘密禁止）
test matrix .............................. §15
```

「実装時に決める」「将来検討する」としている項目は存在しない。
