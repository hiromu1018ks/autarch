# Investigate Before Asking 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 「分からないことは agent が自分で調べ、ユーザーの意向が必要なことだけ質問する」判別を、Jev 質問の文言と `resolve()` のゲート構造で確実にする。

**Architecture:** 判別軸(調査で取得できるか/意向依存か)を Jev の質問文言と blocker 定義文に直接組み込み、`resolve()` は sufficiency 単独でゲートを発火させて blocker_class で行き先(調査 or 意向質問)を決める。`gate_order` 機構は廃止する。閾値の数値・分類名・rule/decision 語彙・judging.py 指標は一切変えない。

**Tech Stack:** Python 3.10+ stdlib only(decide.py)、pytest、TypeSafe AI API(Jev)、Claude Code(full-flow 評価)。

**Spec:** `docs/superpowers/specs/2026-10-02-investigate-before-asking-design.md`

## Global Constraints

- 閾値数値は固定: `auto_select 0.85`、`review 0.60`、`min_gap 0.15`、`human_preference 0.70`、`sufficiency 0.60`、`blocker_confidence 0.50`
- `blocker_class` の分類名(`user_preference_unknown`/`facts_missing`/`material_bias`/`balanced_tie`)、`rule`/`decision` の出力語彙、`evals/judging.py` の指標定義は不変
- `decide.py` は stdlib-only(依存追加禁止)
- 既存の評価記録ディレクトリ(`evals/results/` 配下の既存もの)は上書き・変更しない。新記録は `evals/results/investigate-before-asking-2026-10-02/` へ
- SKILL.md・README の本文は英語(README.ja.md は日本語)
- live 実行は `~/.autarch/decisions.jsonl` へ追記される(回避不可、仕様どおり)
- コミットメッセージの末尾に `Co-Authored-By: Claude Code <noreply@anthropic.com>` を付ける

## Review Focus

1. **criteria なしの state でゲート発火** — score 計算の前にゲートが切れるべき。Task 2 の `test_no_criteria_state_gates_before_scoring`
2. **意向系 blocker + revision あり** — revision の消費は調査側のみに影響し、意向質問(`human_preference`)は妨げない。Task 2 の `test_intent_blocker_ignores_revision`
3. **低 blocker_confidence + revision あり** — 調査側フォールバックが revision で尽き、`investigation_exhausted` として質問へ流れる。Task 2 の `test_low_confidence_with_revision_is_exhausted`
4. **過去の captured snapshot(`gate_order` フィールド付き)が calibrate で弾かれない** — Task 6 の `test_replay_ignores_legacy_gate_order_field`
5. **旧 `--gate-order` フラグ付きの CLI 実行が usage error(exit 2)で拒否される** — Task 2 の `test_gate_order_flag_is_rejected`

---

### Task 1: Jev 質問文言の変更

**Files:**
- Modify: `skills/autarch/scripts/decide.py:54-91`(定数)
- Test: `tests/test_decide.py`(`test_module_exposes_constants` と `TestBuildRequest`)

**Interfaces:**
- Consumes: なし(独立)
- Produces: 新しい `NOUL_INSTRUCTIONS`・`BLOCKER_DESCRIPTIONS`(文言のみ。分類名・protocol・parse 構造は不変)

- [ ] **Step 1: 失敗テストを書く**

`tests/test_decide.py` の `test_module_exposes_constants`(11行目)の該当行を更新し、`TestBuildRequest` に文言テストを追加する:

```python
def test_module_exposes_constants():
    assert decide.REDACTED == "[REDACTED]"
    assert "password" in decide.SENSITIVE_KEY_TERMS
    assert "credentials" in decide.SENSITIVE_KEY_TERMS
    assert len(decide.STRING_PATTERNS) >= 7
    assert decide.PATTERN_EXEMPT_KEYS == frozenset({"id"})
    assert decide.NOUL_INSTRUCTIONS.startswith("Does resolving this decision depend")
    assert decide.CHOICE_INSTRUCTIONS == (
        "Select the option that best satisfies the goal and constraints."
    )
```

`TestBuildRequest` への追加:

```python
    def test_question_wordings_distinguish_investigable_from_intent(self):
        state = _valid_state()
        payload = decide.build_request(state, "jev-test")
        questions = payload["questions"]
        assert questions["requires_human_preference"]["instructions"] == (
            "Does resolving this decision depend on the user's own preference, "
            "plans, or intent — something the agent cannot obtain by "
            "investigating sources?"
        )
        assert questions["blocker_class"]["criteria"]["facts_missing"] == (
            "A fact needed to compare the alternatives is missing, and the "
            "agent can obtain it by investigating sources (repository, "
            "documentation, web search)"
        )
        assert questions["blocker_class"]["criteria"]["user_preference_unknown"] == (
            "What is missing is the user's own preference, plan, or intent; "
            "no investigation can supply it"
        )
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `.venv/bin/python3 -m pytest tests/test_decide.py::test_module_exposes_constants tests/test_decide.py::TestBuildRequest -x -q`
Expected: FAIL(現行文言は "require..." で始まるため)

- [ ] **Step 3: 定数を変更する**

`skills/autarch/scripts/decide.py` の `NOUL_INSTRUCTIONS`(54行目)と `BLOCKER_DESCRIPTIONS` の2項目(74行目〜)を置換:

```python
NOUL_INSTRUCTIONS = (
    "Does resolving this decision depend on the user's own preference, "
    "plans, or intent — something the agent cannot obtain by "
    "investigating sources?"
)
```

```python
BLOCKER_DESCRIPTIONS = {
    "user_preference_unknown": (
        "What is missing is the user's own preference, plan, or intent; "
        "no investigation can supply it"
    ),
    "facts_missing": (
        "A fact needed to compare the alternatives is missing, and the "
        "agent can obtain it by investigating sources (repository, "
        "documentation, web search)"
    ),
    "material_bias": (
        "Alternatives or criteria are described unevenly in a way that "
        "biases the comparison"
    ),
    "balanced_tie": (
        "The alternatives are evenly matched on the provided material; "
        "a deciding priority is needed"
    ),
}
```

`BLOCKER_INSTRUCTIONS`・`SUFFICIENCY_INSTRUCTIONS`・`CHOICE_INSTRUCTIONS`・`BLOCKER_CLASSES` は変更しない。

- [ ] **Step 4: テストが通ることを確認**

Run: `.venv/bin/python3 -m pytest tests/test_decide.py -q`
Expected: 全 PASS

- [ ] **Step 5: Commit**

```bash
git add skills/autarch/scripts/decide.py tests/test_decide.py
git commit -m "feat: state the investigable-vs-intent axis in Jev questions"
```

---

### Task 2: resolve() のゲート構造再設計と gate_order 廃止

**Files:**
- Modify: `skills/autarch/scripts/decide.py:722-787`(resolve)、`102`(GATE_ORDERS)、`958-1024`(main の CLI と snapshot)
- Test: `tests/test_decide.py`(`TestResolveSufficiencyGate` の置換・`TestCliContractViaSubprocess`)

**Interfaces:**
- Consumes: なし
- Produces: `decide.resolve(state, parsed, thresholds) -> dict`(**gate_order 引数削除**)。`decide.GATE_ORDERS` 定数は削除。`evaluation_snapshot` から `gate_order` キーを除去(snapshot は `schema_version, parsed, thresholds, evaluated_option_ids` の4キー)。CLI は `--gate-order` を受け付けない(usage error, exit 2)

- [ ] **Step 1: 失敗テストを書く**

`tests/test_decide.py` の `TestResolveSufficiencyGate`(1121行目〜)を以下のクラスで**置換**する(既存テストのうち `test_low_blocker_confidence_falls_back_to_legacy_rules` と `test_human_preference_rule_precedes_gate` は前提が変わるため削除し、残りは新しいクラスへ統合・更新):

```python
class TestResolveSufficiencyGate:
    def _run(self, state=None, **answer_kwargs):
        state = state or _valid_state()
        answers = make_answers(state, **answer_kwargs)
        parsed = decide.parse_answers(answers_body(answers), state)
        return decide.resolve(state, parsed, _thresholds())

    def test_insufficient_evidence_blocks_auto_select(self):
        resolution = self._run(choice="option_a", confidence=0.95,
                               sufficiency=0.2, blocker="facts_missing",
                               blocker_confidence=0.8)
        assert resolution["decision"] == "ASK_USER"
        assert resolution["rule"] == "evidence_insufficient"
        assert resolution["selected_option"] is None
        assert resolution["blocker_class"] == "facts_missing"
        assert resolution["blocker_confidence"] == 0.8
        assert resolution["evidence_sufficiency"] == 0.2

    def test_sufficiency_alone_triggers_gate(self):
        # deployment full-flow pattern: sufficiency .54, blocker_confidence .22
        resolution = self._run(choice="option_a", confidence=0.95,
                               sufficiency=0.54, blocker_confidence=0.22)
        assert resolution["decision"] == "ASK_USER"
        assert resolution["rule"] == "evidence_insufficient"
        assert resolution["blocker_class"] == "facts_missing"

    def test_low_confidence_falls_back_to_investigation(self):
        resolution = self._run(confidence=0.95, sufficiency=0.4,
                               blocker="user_preference_unknown",
                               blocker_confidence=0.22)
        assert resolution["rule"] == "evidence_insufficient"
        assert resolution["blocker_class"] == "user_preference_unknown"

    def test_low_confidence_with_revision_is_exhausted(self):
        state = _valid_state()
        state["revision"] = {"round": 1, "action": "investigation",
                             "summary": "checked the repository"}
        resolution = self._run(state=state, confidence=0.95, sufficiency=0.4,
                               blocker_confidence=0.3)
        assert resolution["rule"] == "investigation_exhausted"

    def test_every_blocker_class_blocks_auto_select(self):
        for blocker in decide.BLOCKER_CLASSES:
            resolution = self._run(confidence=0.95, sufficiency=0.1,
                                   blocker=blocker, blocker_confidence=0.9)
            assert resolution["decision"] == "ASK_USER", blocker
            assert resolution["blocker_class"] == blocker

    def test_intent_blocker_routes_to_human_preference(self):
        resolution = self._run(confidence=0.95, sufficiency=0.2,
                               blocker="user_preference_unknown",
                               blocker_confidence=0.9)
        assert resolution["decision"] == "ASK_USER"
        assert resolution["rule"] == "human_preference"
        assert resolution["blocker_class"] == "user_preference_unknown"
        assert resolution["blocker_confidence"] == 0.9

    def test_intent_blocker_ignores_revision(self):
        state = _valid_state()
        state["revision"] = {"round": 1, "action": "investigation",
                             "summary": "checked the repository"}
        resolution = self._run(state=state, confidence=0.95, sufficiency=0.2,
                               blocker="user_preference_unknown",
                               blocker_confidence=0.9)
        assert resolution["rule"] == "human_preference"

    def test_gate_fires_before_human_preference_at_high_noul(self):
        # auth_loop pattern: high human preference AND investigable facts missing
        resolution = self._run(noul=0.95, confidence=0.99, sufficiency=0.3,
                               blocker="facts_missing", blocker_confidence=0.8)
        assert resolution["rule"] == "evidence_insufficient"

    def test_sufficient_evidence_high_noul_asks_preference(self):
        # deploy_preference_needed pattern
        resolution = self._run(noul=0.9, confidence=0.99, sufficiency=0.9)
        assert resolution["rule"] == "human_preference"
        assert resolution["blocker_class"] is None

    def test_human_preference_via_gate_reports_blocker(self):
        resolution = self._run(noul=0.9, confidence=0.95, sufficiency=0.2,
                               blocker="balanced_tie", blocker_confidence=0.8)
        assert resolution["rule"] == "human_preference"
        assert resolution["blocker_class"] == "balanced_tie"
        assert resolution["blocker_confidence"] == 0.8

    def test_revision_exhausts_investigation(self):
        state = _valid_state()
        state["revision"] = {"round": 1, "action": "investigation",
                             "summary": "checked the repository"}
        resolution = self._run(state=state, confidence=0.95, sufficiency=0.1,
                               blocker="facts_missing", blocker_confidence=0.9)
        assert resolution["decision"] == "ASK_USER"
        assert resolution["rule"] == "investigation_exhausted"
        assert resolution["blocker_class"] == "facts_missing"

    def test_revision_with_sufficient_evidence_selects_normally(self):
        state = _valid_state()
        state["revision"] = {"round": 1, "action": "material_fix",
                             "summary": "rebalanced descriptions"}
        resolution = self._run(state=state, choice="option_a",
                               confidence=0.95, sufficiency=0.9)
        assert resolution["decision"] == "SELECT_OPTION"
        assert resolution["rule"] == "confidence"

    def test_sufficient_evidence_skips_gate(self):
        resolution = self._run(choice="option_a", confidence=0.95,
                               sufficiency=0.9)
        assert resolution["decision"] == "SELECT_OPTION"
        assert resolution["blocker_class"] is None

    def test_no_criteria_state_gates_before_scoring(self):
        state = _valid_state()
        state["criteria"] = []
        resolution = self._run(state=state, confidence=0.95, sufficiency=0.2,
                               blocker_confidence=0.8)
        assert resolution["rule"] == "evidence_insufficient"
        assert resolution["score_summary"] is None
```

`TestCliContractViaSubprocess`(1514行目〜)へ追加:

```python
    def test_gate_order_flag_is_rejected(self, tmp_path):
        state_file = tmp_path / "state.json"
        state_file.write_text(json.dumps(_valid_state()), encoding="utf-8")
        completed = subprocess.run(
            [sys.executable, str(DECIDE_SCRIPT), "--state-file", str(state_file),
             "--gate-order", "human_first"],
            capture_output=True, text=True, timeout=60,
        )
        assert completed.returncode == 2
        assert "gate-order" in completed.stderr or "gate_order" in completed.stderr
```

(既存の subprocess テストが使っている定数名 `DECIDE_SCRIPT`・import を確認し、同じものを使う。`_valid_state()` が module-level で使えるかも確認する。)

さらに `TestEvaluationCapture`(1782行目〜)の snapshot 期待に `gate_order` が含まれていれば削除する(`rg -n "gate_order" tests/test_decide.py` で確認)。

- [ ] **Step 2: テストが失敗することを確認**

Run: `.venv/bin/python3 -m pytest tests/test_decide.py::TestResolveSufficiencyGate tests/test_decide.py::TestCliContractViaSubprocess -q`
Expected: FAIL(`resolve() takes keyword-only argument 'gate_order'` 等)

- [ ] **Step 3: resolve() を新構造に書き換える**

`skills/autarch/scripts/decide.py` の `resolve()`(722-787行)のゲート部分を置換:

```python
def resolve(state: dict, parsed: dict, thresholds: dict) -> dict:
    """Apply the deterministic resolution policy (spec section 8)."""
    probabilities = parsed["probabilities"]
    confidence = parsed["confidence"]
    human_preference = parsed["human_preference"]
    has_criteria = bool(state.get("criteria"))
    score_summary = compute_score_summary(state, parsed) if has_criteria else None

    resolution = {
        "decision": None,
        "rule": None,
        "selected_option": None,
        "confidence": confidence,
        "probability": None,
        "probabilities": probabilities,
        "human_preference_probability": human_preference,
        "score_summary": score_summary,
        "evidence_sufficiency": parsed["evidence_sufficiency"],
        "blocker_class": None,
        "blocker_confidence": None,
        "evaluation_signals": {
            "blocker_class": parsed["blocker_class"],
            "blocker_confidence": parsed["blocker_confidence"],
        },
        "evaluation_snapshot": None,
        "reason": "",
    }

    human_gate = human_preference >= thresholds["human_preference"]
    gate_fires = parsed["evidence_sufficiency"] < thresholds["sufficiency"]
    if gate_fires:
        blocker = parsed["blocker_class"]
        resolution["blocker_class"] = blocker
        resolution["blocker_confidence"] = parsed["blocker_confidence"]
        investigates = blocker in ("facts_missing", "material_bias") or (
            parsed["blocker_confidence"] < thresholds["blocker_confidence"]
        )
        has_revision = isinstance(state.get("revision"), dict)
        if investigates and has_revision:
            resolution["decision"] = "ASK_USER"
            resolution["rule"] = "investigation_exhausted"
            resolution["reason"] = (
                "The single investigation round has been spent and the "
                "evidence still does not support automatic selection; "
                "returning the decision to the user."
            )
        elif investigates:
            resolution["decision"] = "ASK_USER"
            resolution["rule"] = "evidence_insufficient"
            resolution["reason"] = (
                f"Jev classifies the decision blocker as '{blocker}' "
                f"(evidence sufficiency {parsed['evidence_sufficiency']:.2f}); "
                "the evidence does not support automatic selection."
            )
        else:
            resolution["decision"] = "ASK_USER"
            resolution["rule"] = "human_preference"
            resolution["reason"] = (
                "Jev indicates this decision depends on the user's personal "
                "preference or intent; it must not be auto-selected."
            )
        return resolution

    if human_gate:
        resolution["decision"] = "ASK_USER"
        resolution["rule"] = "human_preference"
        resolution["reason"] = (
            "Jev indicates this decision depends on the user's personal "
            "preference or intent; it must not be auto-selected."
        )
        return resolution
```

(789行目以降の choice/score 一致性・gap・confidence bands はそのまま。)

続けて同じファイルで:

1. `GATE_ORDERS = ("human_first", "evidence_first")`(102行)を削除
2. `main()` の `parser.add_argument("--gate-order", ...)`(960行)を削除
3. `resolve(redacted_state, parsed, thresholds, gate_order=args.gate_order)`(1018行)を `resolve(redacted_state, parsed, thresholds)` へ
4. `evaluation_snapshot` の `"gate_order": args.gate_order`(1024行)を削除

- [ ] **Step 4: テストが通ることを確認**

Run: `.venv/bin/python3 -m pytest tests/test_decide.py -q`
Expected: 全 PASS

- [ ] **Step 5: 全テストを走らせる(他モジュールの破損を確認)**

Run: `.venv/bin/python3 -m pytest -q`
Expected: evals 系テスト(`test_run_fixed_state.py`・`test_calibrate_thresholds.py` 等)が FAIL する(**Task 5・6 で直す。ここでは test_decide.py/test_skill_md.py が全 PASS であることと、FAIL が gate_order 起因のみであることを確認する**)

- [ ] **Step 6: Commit**

```bash
git add skills/autarch/scripts/decide.py tests/test_decide.py
git commit -m "feat: gate on sufficiency alone and route by blocker class"
```

---

### Task 3: SKILL.md の更新(調査前置・判別ミラー・assessments 例)

**Files:**
- Modify: `skills/autarch/SKILL.md`(Step 4・Step 6・Step 11)
- Test: `tests/test_skill_md.py`

**Interfaces:**
- Consumes: Task 2 の新ゲート構造(rule と blocker の対応)
- Produces: SKILL.md の追加文言(後続タスク・README 更新の参照元)

- [ ] **Step 1: 失敗テストを書く**

`tests/test_skill_md.py` の `TestSkillMarkdown` へ追加:

```python
    def test_step4_requires_investigation_before_state(self):
        text = _read()
        assert "Investigate before writing the state" in text
        assert "do not defer them to a" in text
        assert "never investigate those" in text

    def test_step6_shows_assessments_object_example(self):
        text = _read()
        assert '"assessments"' in text
        assert "must be an object keyed by option id" in text

    def test_step11_routes_intent_blockers_to_deciding_question(self):
        text = _read()
        assert "Blocker `user_preference_unknown` or `balanced_tie`" in text
        assert "one deciding question" in text
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `.venv/bin/python3 -m pytest tests/test_skill_md.py -q`
Expected: FAIL(新文言が未追加)

- [ ] **Step 3: SKILL.md を編集する**

`skills/autarch/SKILL.md` の3箇所:

**(a) Step 4(Gather evidence)の冒頭へ段落追加:**

```markdown
Investigate before writing the state. Before you build the state JSON,
check the repository, project documentation, and — when relevant —
external documentation or web search for facts the comparison needs.
Facts you can obtain by investigation belong in the state now; do not
defer them to a post-evaluation investigation round. Only the user's own
preference, plans, or intent is exempt: never investigate those — return
them as a question.
```

**(b) Step 6 の `hard_constraints` 説明(148行目付近)へ、assessments の具体例と注意を追加:**

```markdown
Each constraint has `id`, non-empty `description`, and `assessments`
covering exactly all original alternative IDs. `assessments` must be an
object keyed by option id, never an array:

```json
"hard_constraints": [
  {
    "id": "offline",
    "description": "Must work fully offline.",
    "assessments": {
      "sqlite": {"status": "met", "evidence_ids": ["runtime_confirmation"]},
      "json": {"status": "unknown", "evidence_ids": []}
    }
  }
]
```
```

**(c) Step 11 の分岐頭(220行目付近)へ、rule と行き先の対応を1文追加:**

```markdown
The engine returns `evidence_insufficient` when the missing piece is
investigable (blocker `facts_missing` or `material_bias`), and
`human_preference` when what is missing is your intent (blocker
`user_preference_unknown` or `balanced_tie`, or sufficient evidence with
high preference dependence). Follow the rule below either way.
```

- [ ] **Step 4: テストが通ることを確認**

Run: `.venv/bin/python3 -m pytest tests/test_skill_md.py -q`
Expected: 全 PASS

- [ ] **Step 5: Commit**

```bash
git add skills/autarch/SKILL.md tests/test_skill_md.py
git commit -m "docs: instruct investigation before state and mirror the routing"
```

---

### Task 4: README.md / README.ja.md の更新

**Files:**
- Modify: `README.md`(52-65行の decision policy、203行の --gate-order)
- Modify: `README.ja.md`(対応箇所)

**Interfaces:**
- Consumes: Task 2 の新ゲート構造
- Produces: なし(文書)

- [ ] **Step 1: README.md の decision policy を更新**

「Decision policy」の番号付きリスト(54-61行)を差し替え:

```markdown
1. **Provider error** → `PROVIDER_UNAVAILABLE` — never auto-select on a failed/unusable API response
2. **Evidence sufficiency** (< 0.60) → `ASK_USER` — the blocker class routes the outcome: missing-but-investigable facts or biased material trigger one investigation/repair round; a user-preference or tie blocker asks one deciding question
3. **Human-preference gate** (Noul ≥ 0.70 with sufficient evidence) → `ASK_USER` — if the decision depends on your taste or intent, Autarch refuses to choose even at high confidence
4. **Choice/Score consistency** — if the Choice winner and the weighted Score winner disagree → `ASK_USER`
5. **Probability gap** — if the top two options are within 0.15 of each other → `ASK_USER`
6. **Confidence bands** — ≥ 0.85 → `SELECT_OPTION`, ≥ 0.60 → `SELECT_OPTION_WITH_CAUTION`, else → `ASK_USER`
```

203行目の ``--gate-order` accepts the default `human_first` or `evidence_first`.` を削除する。

- [ ] **Step 2: README.ja.md を同様に更新**

README.ja.md の decision policy リストと205行目の `--gate-order` 文を、上記に対応する日本語で更新:

```markdown
2. **根拠の充足度**(< 0.60)→ `ASK_USER` — blocker 分類が行き先を決めます。調査で取得できる事実の欠落や資料の偏りは1回の調査・修復ラウンドへ、ユーザーの意向・優先順位の欠落は1つの意思決定質問へ振り分けます
3. **ユーザー意向ゲート**(Noul ≥ 0.70 かつ根拠十分)→ `ASK_USER` — 決定があなたの好み・意向に依存する場合、confidence が高くても自動選択しません
```

- [ ] **Step 3: 全体テストで文書整合テストの破損がないことを確認**

Run: `.venv/bin/python3 -m pytest tests/ -q -k "skill or decide"`
Expected: PASS(README を検査するテストがあれば更新。`rg -n "gate" tests/` で確認)

- [ ] **Step 4: Commit**

```bash
git add README.md README.ja.md
git commit -m "docs: update decision policy for sufficiency-first routing"
```

---

### Task 5: evals runners から --gate-order を削除

**Files:**
- Modify: `evals/run_fixed_state.py:49,119,216`
- Modify: `evals/run_constraint_cases.py:43,89`
- Test: `tests/test_run_fixed_state.py`(該当箇所)

**Interfaces:**
- Consumes: Task 2 の `resolve(state, parsed, thresholds)`
- Produces: runners の CLI 引数から `--gate-order` が消えた状態。環境記録 JSON から `gate_order` キーが消える

- [ ] **Step 1: 既存テストの gate_order 期待を確認・更新**

Run: `rg -n "gate" tests/test_run_fixed_state.py tests/test_run_full_flow.py tests/test_constraint_cases.py`
出力された `gate_order` 参照をすべて削除する(コマンド列の期待に `--gate-order` が含まれていれば削る)。

- [ ] **Step 2: run_fixed_state.py を更新**

`run_once` のコマンド列から `"--gate-order", args.gate_order,`(49行)を削除。`parser.add_argument("--gate-order", ...)`(119行)を削除。環境記録の `"gate_order": args.gate_order`(216行)を削除。

- [ ] **Step 3: run_constraint_cases.py を更新**

同様に `--gate-order` の add_argument(43行)と `gate_order` の記録(89行)を削除。

- [ ] **Step 4: テストが通ることを確認**

Run: `.venv/bin/python3 -m pytest tests/test_run_fixed_state.py tests/test_constraint_cases.py -q`
Expected: 全 PASS

- [ ] **Step 5: Commit**

```bash
git add evals/run_fixed_state.py evals/run_constraint_cases.py tests/
git commit -m "refactor: drop gate-order from eval runners"
```

---

### Task 6: calibrate_thresholds.py から gate_order を削除(過去 snapshot 互換)

**Files:**
- Modify: `evals/calibrate_thresholds.py`(23, 45-47, 102-131, 139-147, 187-190, 226, 285-288, 539-541, 624, 633行)
- Test: `tests/test_calibrate_thresholds.py`

**Interfaces:**
- Consumes: Task 2 の `resolve(state, parsed, thresholds)`・4キーの `evaluation_snapshot`
- Produces: `replay_resolution(state, snapshot, thresholds) -> dict`(**gate_order 引数削除**)。`REFERENCE_POLICY` は thresholds のみ。`candidate_policies()` は 45 件(5×3×3)。過去 snapshot の `gate_order` キーは読み込み時に除去して許容

- [ ] **Step 1: 失敗テストを書く**

`tests/test_calibrate_thresholds.py` を更新:

1. ヘルパー(9-21行)から `gate_order` を削る:

```python
def replay(state, snapshot, thresholds=None):
    return calibrate.replay_resolution(
        state, snapshot, thresholds or _thresholds())
```

`_snapshot()` 系フィクスチャから `"gate_order": "human_first"` エントリを削除(snapshot は4キー)。

2. `test_gate_order_variants`(111行目付近)を削除し、代わりに過去互換テストを追加:

```python
def test_replay_ignores_legacy_gate_order_field():
    state = _state()
    snapshot = _snapshot()
    snapshot["gate_order"] = "evidence_first"  # legacy captured snapshot
    resolution = replay(state, snapshot)
    assert resolution["decision"] in ("ASK_USER", "SELECT_OPTION",
                                      "SELECT_OPTION_WITH_CAUTION")
```

3. `test_snapshot_field_changes`(148, 159行)の `gate_order` 変異ケースを削除。
4. `test_requires_*`(207行)の必須フィールド一覧から `gate_order` を削除。
5. ランキング系(276, 396-398, 412, 533-534, 600, 814行)の `row["gate_order"]` / `policy["gate_order"]` 参照を削除。grid サイズの期待は `90 → 45` に(534行: `== 45`)。
6. snapshot への `gate_order` 注入(477, 613, 712, 757行)を削除。

- [ ] **Step 2: テストが失敗することを確認**

Run: `.venv/bin/python3 -m pytest tests/test_calibrate_thresholds.py -q`
Expected: FAIL(現行 replay_resolution は gate_order を要求)

- [ ] **Step 3: calibrate_thresholds.py を更新**

1. `SNAPSHOT_FIELDS`(23行)から `"gate_order"` を削除(4キーに)
2. `_validate_order`(45-47行)を削除
3. `replay_resolution` を変更:

```python
def replay_resolution(state: dict, snapshot: dict, thresholds: dict) -> dict:
    """Replay validated unrounded signals against the original state and a policy.

    Capture settings are validated for provenance; the supplied thresholds
    select the replay policy. Constraints are regenerated by the engine.
    Neither the state nor the snapshot is mutated. Snapshots captured before
    the gate-order removal may carry a legacy "gate_order" key; it is ignored.
    """
    snapshot = {key: value for key, value in snapshot.items() if key != "gate_order"}
    _require_fields(snapshot, SNAPSHOT_FIELDS, "snapshot")
    if type(snapshot["schema_version"]) is not int or snapshot["schema_version"] != 1:
        raise ValueError("unsupported evaluation snapshot schema_version")
    _validate_thresholds(snapshot["thresholds"])
    _validate_thresholds(thresholds)
    _require_finite(state)
    evaluated, constraint_check, early = decide.check_constraints(state)
    if early is not None:
        raise ValueError(f"state cannot be evaluated: {early['rule']}")
    option_ids = snapshot["evaluated_option_ids"]
    if (not isinstance(option_ids, list) or not all(_valid_id(item) for item in option_ids)
            or len(set(option_ids)) != len(option_ids)
            or option_ids != [a["id"] for a in evaluated["alternatives"]]):
        raise ValueError("evaluated_option_ids must match the engine's evaluated options exactly")
    parsed = snapshot["parsed"]
    _validate_parsed(parsed, evaluated)
    parsed = copy.deepcopy(parsed)
    resolution = decide.resolve(evaluated, parsed, thresholds)
    resolution["constraint_check"] = decide.redact(constraint_check)[0]
    return resolution
```

4. `REFERENCE_POLICY` から `"gate_order": "human_first"` を削除
5. `candidate_policies()` から `for order in (...)` 軸と `"gate_order": order` を削除(45 件に)
6. `_index_runs` の capture 検査(187-189行)から `or snapshot.get("gate_order") != capture_policy["gate_order"]` を削除し、replay 呼び出し(190行)から第4引数を削除
7. `_policy_summary` 内の replay 呼び出し(226行)から `policy["gate_order"]` を削除
8. ランキングの `changes`/`rank_key`(285-288行)から gate_order 比較を削除
9. `describe`/`validate` の policy 読み書き(539-541, 624, 633行)から gate_order を削除

- [ ] **Step 4: テストが通ることを確認**

Run: `.venv/bin/python3 -m pytest tests/test_calibrate_thresholds.py -q`
Expected: 全 PASS

- [ ] **Step 5: 全体テスト**

Run: `.venv/bin/python3 -m pytest -q`
Expected: 全 PASS(skip 3 は live 系)

- [ ] **Step 6: Commit**

```bash
git add evals/calibrate_thresholds.py tests/test_calibrate_thresholds.py
git commit -m "refactor: remove gate order from calibration, keep legacy snapshots"
```

---

### Task 7: deploy_loop state の修正(調査誘発)

**Files:**
- Modify: `evals/cases_loop/deploy_loop_resolvable.json`(state.evidence と investigation.injected_evidence)
- Test: `tests/test_eval_loop_cases.py`(既存の schema・語彙検査がそのままカバー)

**Interfaces:**
- Consumes: Task 2 の新ゲート構造(sufficiency < 0.60 で発火)
- Produces: deploy_loop の phase1 が `evidence_insufficient / facts_missing` に誘導される state

- [ ] **Step 1: state の evidence を更新**

`evals/cases_loop/deploy_loop_resolvable.json` の `state.evidence` を差し替え:

```json
"evidence": [
  "the content is written as markdown sources",
  "the site is currently built by a legacy pipeline whose output format is not recorded in the repository"
]
```

`investigation.injected_evidence` を差し替え:

```json
"injected_evidence": [
  "the legacy pipeline outputs static HTML files",
  "no dynamic endpoints or server-side rendering exist"
]
```

(phase1 期待 `rule: evidence_insufficient, blocker_class: facts_missing` と phase2 期待は変更しない。)

- [ ] **Step 2: schema・語彙テストが通ることを確認**

Run: `.venv/bin/python3 -m pytest tests/test_eval_loop_cases.py tests/test_case_schema.py -q`
Expected: 全 PASS

- [ ] **Step 3: Commit**

```bash
git add evals/cases_loop/deploy_loop_resolvable.json
git commit -m "test: make deploy_loop phase1 investigate the legacy pipeline"
```

---

### Task 8: offline replay による構造検証

**Files:**
- Create: `evals/results/investigate-before-asking-2026-10-02/offline-replay/notes.md`(結果記録)
- 参照のみ: `evals/results/hard-constraints-calibration-2026-10-01/training/fixed_state_runs.jsonl`、`validation/fixed_state_runs.jsonl`

**Interfaces:**
- Consumes: Task 6 後の `calibrate_thresholds.py`(describe 相当の再集計)と既存 snapshots
- Produces: 新構造での unsafe・loop 集計の記録(live 実行前の健全性確認)

- [ ] **Step 1: describe コマンドの引数を確認**

Run: `.venv/bin/python3 evals/calibrate_thresholds.py --help` と `describe --help`
(describe の capture policy・cases の指定方法を確認する)

- [ ] **Step 2: training snapshots を再集計**

training の runs(87位相)を describe で再集計し、`unsafe`・`evidence_misses`・`loop_phase2_failures`・`db_loop_passes` を、`evals/results/hard-constraints-calibration-2026-10-01/training` 記録時の値と比較する。コマンド例(describe の実際の引数は Step 1 の確認に従う):

```bash
.venv/bin/python3 evals/calibrate_thresholds.py describe \
  --runs-file evals/results/hard-constraints-calibration-2026-10-01/training/fixed_state_runs.jsonl \
  --out-file evals/results/investigate-before-asking-2026-10-02/offline-replay/training-summary.json
```

- [ ] **Step 3: validation snapshots も同様に再集計**

```bash
.venv/bin/python3 evals/calibrate_thresholds.py describe \
  --runs-file evals/results/hard-constraints-calibration-2026-10-01/validation/fixed_state_runs.jsonl \
  --out-file evals/results/investigate-before-asking-2026-10-02/offline-replay/validation-summary.json
```

- [ ] **Step 4: 結果を記録し判断する**

`notes.md` に新旧の集計値と差分を記録する。**unsafe が構造変更だけで増えていないか**を確認する。増加がある場合は Task 2 の実装に戻る(フォールバック条件の見直し)。全項目で増加なし、または減少なら次へ。

- [ ] **Step 5: Commit**

```bash
git add evals/results/investigate-before-asking-2026-10-02/offline-replay/
git commit -m "test: record offline replay of new gate structure"
```

---

### Task 9: live 再実行・比較・状態記録の更新

**Files:**
- Create: `evals/results/investigate-before-asking-2026-10-02/`(runner が生成)
- Modify: `STATE.md`、`README.md`/`README.ja.md` の Implementation and validation status

**Interfaces:**
- Consumes: Task 1-7 の実装・Task 8 の健全性確認
- Produces: 新実装での評価記録と、比較レポート

- [ ] **Step 1: 全体テストの緑を確認**

Run: `.venv/bin/python3 -m pytest -q`
Expected: 全 PASS(skip 3 は live 系)

- [ ] **Step 2: 固定 state + loop の live 実行**

```bash
.venv/bin/python3 evals/run_fixed_state.py \
  --out-dir evals/results/investigate-before-asking-2026-10-02 \
  --loop-cases-dir evals/cases_loop --runs 3 --model jev-latest \
  --auto-select 0.85 --review 0.60 --min-gap 0.15 \
  --human-preference 0.70 --sufficiency 0.60 --blocker-confidence 0.50
```

ネットワークと `TYPESAFE_API_KEY` が必要。`~/.autarch/decisions.jsonl` に追記される。

- [ ] **Step 3: 条件トラックの live 実行**

```bash
.venv/bin/python3 evals/run_constraint_cases.py \
  --out-dir evals/results/investigate-before-asking-2026-10-02-constraints \
  --runs 3 --model jev-latest \
  --auto-select 0.85 --review 0.60 --min-gap 0.15 \
  --human-preference 0.70 --sufficiency 0.60 --blocker-confidence 0.50
```

- [ ] **Step 4: full-flow の live 実行**

```bash
.venv/bin/python3 evals/run_full_flow.py \
  --out-dir evals/results/investigate-before-asking-2026-10-02 \
  --agent-model sonnet
```

- [ ] **Step 5: 比較レポート生成**

```bash
.venv/bin/python3 evals/report_baseline.py \
  --baseline-dir evals/results/investigate-before-asking-2026-10-02 \
  --loop-cases-dir evals/cases_loop \
  --compare-to evals/results/hard-constraints-calibration-2026-10-01/final
```

成功基準(spec §1)を確認: auth_loop/deploy_loop pass の改善、unsafe 8/69 からの減少、full-flow deployment の decision_ok 成立。**失敗観測が残った場合は結果を正直に記録し、改善と断定しない**(これまでの評価記録の慣行どおり)。

- [ ] **Step 6: notes.md に留保を記録**

`evals/results/investigate-before-asking-2026-10-02/notes.md` に、新旧シグナル分布(human_preference・sufficiency・blocker_class・blocker_confidence の観測値の対比)、失敗が残ったケースの詳細、実測の揺れと構造改善の区別を記録する。`SUMMARY.md` 再生成で消えないよう `notes.md` に書く。

- [ ] **Step 7: STATE.md と README のステータスを更新**

`STATE.md` の冒頭サマリと今回のセクション追加(日付・実施内容・結果・残課題)。`README.md`/`README.ja.md` の Implementation and validation status も今回の結果で更新。

- [ ] **Step 8: Commit**

```bash
git add evals/results/investigate-before-asking-2026-10-02/ STATE.md README.md README.ja.md
git commit -m "test: record investigate-before-asking evaluation"
```

---

## 実行上の注意

- Task 2 の Step 5 で evals 系テストが一時的に FAIL するのは想定どおり(Task 5・6 で修正)。**Task 2 だけで作業を止めないこと**
- Task 8・9 は live 実行を含む。ネットワーク制限・API 障害(EAI_AGAIN・HTTP 5xx 等)が起きた場合は、既存の慣行どおり失敗として記録し、迂回しない
- 評価の分母・期待値を結果に合わせて事後に緩めない(既存の方針を踏襲)
