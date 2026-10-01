# 情報不足の分類と一度の追加調査 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** decide.py に根拠充足性ゲート(Jev への新質問2種)と `revision` による一度制限を導入し、SKILL.md に追加調査ループを足し、2段階評価ケースで測定して baseline と比較する。

**Architecture:** 分類は Jev への追加質問(noul `evidence_sufficiency` + choice `blocker_class`)で取得し、`resolve()` の human_preference ルール直後に挿入するゲートで自動選択をブロックする(新 decision 値は作らない)。追加調査の実行主体は agent で、state の `revision` フィールドが「調査枠を使い切った」ことの真実の源。評価は既存23+5を無変更再実行し、別途 `cases_loop/` の2段階ケースでループを機械測定する。

**Tech Stack:** Python 3.10+ stdlib only / pytest / Jev (TypeSafe AI SystemOne API) / claude CLI(full-flow のみ)

**Spec:** `docs/superpowers/specs/2026-10-01-info-gap-investigation-design.md`(本計画は spec から議論を展開する。実行者は両方を読むこと)

## Global Constraints

- `evals/judging.py` は**一切変更しない**(指標定義不変は STATE.md の約束)。loop 判定は `report_baseline.py` に新関数で置く
- decide.py の出力は既存フィールド不変・**追加のみ**。decision 値は既存5種のまま
- SKILL.md は13ステップ構成を維持する(`tests/test_skill_md.py` が Step 1〜13 の存在を検証)。変更は Step 8・11 のみ
- しきい値の既定値: `--sufficiency 0.60` / `--blocker-confidence 0.50`(spec §4.3)
- blocker の4分類 id は固定: `user_preference_unknown` / `facts_missing` / `material_bias` / `balanced_tie`
- `revision` の制約: `round` は 1 のみ・`action` は `investigation` / `material_fix`・`summary` は空でない文字列で上限500字(spec §4.5)
- 固定 state の loop 記録は `case_kind: "loop"` + `phase: 1|2` を持つ。通常記録は既存形式のまま(loop フィールドなし)
- テストは TDD(失敗テスト→実装→緑→commit)。実行コマンドは `python3 -m pytest <file> -v`、全体は `python3 -m pytest`
- commit message の末尾に `Co-Authored-By: Claude Code <noreply@anthropic.com>` を付ける
- 日本語で応答する。SKILL.md 本体・decide.py の文字列(reason 等)は英語

## Review Focus

実装中に最も刺さりやすい入力クラスと期待挙動(spec が暗に含むが個別タスクのテストだけでは拾い切れないもの):

1. **Jev が `blocker_class` の `probabilities` を4分類ちょうどで返さない、または `choice` が最大確率でない** → `ProviderError` で拒否し `PROVIDER_UNAVAILABLE` 扱い。`best_option` と同じ厳格さでなければならない(Task 1 のテスト)
2. **`revision.summary` に秘密パターン(`sk-...` 等)が入る** → `redact()` の再帰処理で送信前に伏せ字されること(spec §4.6。summary は通常の文字列値)(Task 2 のテスト)
3. **`revision.round` に `true`(bool)が入る** → Python の `True == 1` で受け入れられてはならない。検証エラーにする(Task 2 のテスト)
4. **loop 記録が既存23ケースの指標分母に混入する** → `report_baseline.py` は `case_kind == "loop"` を除外して baseline 比較を守る(Task 7 のテスト)
5. **位相2 state(evidence 追記 + revision 付与)が `validate_state` を通らない** → すべての loop ケースで機械保証する(Task 4・5 のテスト)

---

### Task 1: decide.py — 新Jev質問の request 同梱と parse 検証

**Files:**
- Modify: `skills/autarch/scripts/decide.py`(定数・`build_request`・`parse_answers`)
- Test: `tests/test_decide.py`

**Interfaces:**
- Consumes: 既有の `build_request(state, model)` / `parse_answers(body, state)` の構造
- Produces: `parse_answers` の返り値に `evidence_sufficiency: float`・`blocker_class: str`・`blocker_confidence: float` が増える(Task 2 の `resolve()` が消費)。定数 `SUFFICIENCY_INSTRUCTIONS`・`BLOCKER_INSTRUCTIONS`・`BLOCKER_CLASSES`・`BLOCKER_DESCRIPTIONS`

- [ ] **Step 1: 失敗テストを書く(定数・build_request・parse)**

`tests/test_decide.py` の `test_module_exposes_constants` に追記:

```python
    assert decide.SUFFICIENCY_INSTRUCTIONS == (
        "Is there enough evidence in the state to select an option automatically?"
    )
    assert decide.BLOCKER_INSTRUCTIONS == (
        "The decision cannot be resolved automatically on the provided "
        "material. Select the primary blocker."
    )
    assert decide.BLOCKER_CLASSES == (
        "user_preference_unknown",
        "facts_missing",
        "material_bias",
        "balanced_tie",
    )
```

既存テスト3件の期待値を更新(`TestBuildRequest` 内)。`test_payload_shape` の `set(questions)`:

```python
        assert set(questions) == {
            "requires_human_preference",
            "best_option",
            "evidence_sufficiency",
            "blocker_class",
            "score__fit__option_a",
            "score__fit__option_b",
        }
```

`test_no_criteria_means_no_score_questions` の set:

```python
        assert set(payload["questions"]) == {
            "requires_human_preference",
            "best_option",
            "evidence_sufficiency",
            "blocker_class",
        }
```

`test_matrix_covers_all_criteria_times_alternatives` の最後の行:

```python
        assert len(payload["questions"]) == 4 + 6
```

テストヘルパー `make_answers` に新質問の既定応答を追加(既定は「ゲート閉」= sufficiency 高):

```python
def make_answers(state, noul=0.1, choice=None, confidence=0.9, probabilities=None,
                 sufficiency=0.9, blocker="facts_missing", blocker_confidence=0.9):
    """Build a consistent answers dict whose winner is `choice`."""
    choice = choice or state["alternatives"][0]["id"]
    if probabilities is None:
        losers = [a["id"] for a in state["alternatives"] if a["id"] != choice]
        share = 0.15 / len(losers) if losers else 0.0
        probabilities = {a["id"]: (0.85 if a["id"] == choice else share)
                         for a in state["alternatives"]}
    blocker_probabilities = {
        name: (0.7 if name == blocker else 0.1)
        for name in decide.BLOCKER_CLASSES
    }
    answers = {
        "requires_human_preference": {"type": "noul", "noul": noul},
        "evidence_sufficiency": {"type": "noul", "noul": sufficiency},
        "blocker_class": {
            "type": "choice",
            "choice": blocker,
            "confidence": blocker_confidence,
            "probabilities": blocker_probabilities,
        },
        "best_option": {
            "type": "choice",
            "choice": choice,
            "confidence": confidence,
            "probabilities": probabilities,
        },
    }
```

(関数の残り(score ループ構築)は変更しない。)

`TestParseAnswers` の後に新規クラスを追加:

```python
class TestParseAnswersNewQuestions:
    def test_parsed_values_present(self):
        state = _valid_state()
        answers = make_answers(state, sufficiency=0.25, blocker="material_bias",
                               blocker_confidence=0.8)
        parsed = decide.parse_answers(answers_body(answers), state)
        assert parsed["evidence_sufficiency"] == 0.25
        assert parsed["blocker_class"] == "material_bias"
        assert parsed["blocker_confidence"] == 0.8

    def test_missing_sufficiency_answer_raises(self):
        state = _valid_state()
        answers = make_answers(state)
        del answers["evidence_sufficiency"]
        with pytest.raises(decide.ProviderError):
            decide.parse_answers(answers_body(answers), state)

    def test_sufficiency_out_of_range_raises(self):
        state = _valid_state()
        for bad in (-0.01, 1.01, True):
            answers = make_answers(state, sufficiency=bad)
            with pytest.raises(decide.ProviderError):
                decide.parse_answers(answers_body(answers), state)

    def test_missing_blocker_answer_raises(self):
        state = _valid_state()
        answers = make_answers(state)
        del answers["blocker_class"]
        with pytest.raises(decide.ProviderError):
            decide.parse_answers(answers_body(answers), state)

    def test_unknown_blocker_class_raises(self):
        state = _valid_state()
        answers = make_answers(state)
        answers["blocker_class"]["choice"] = "mood_unknown"
        with pytest.raises(decide.ProviderError):
            decide.parse_answers(answers_body(answers), state)

    def test_blocker_confidence_out_of_range_and_boolean_rejected(self):
        state = _valid_state()
        for bad in (-0.1, 1.1, True):
            answers = make_answers(state, blocker_confidence=bad)
            with pytest.raises(decide.ProviderError):
                decide.parse_answers(answers_body(answers), state)

    def test_blocker_probabilities_must_cover_every_class(self):
        state = _valid_state()
        answers = make_answers(state)
        del answers["blocker_class"]["probabilities"]["balanced_tie"]
        with pytest.raises(decide.ProviderError):
            decide.parse_answers(answers_body(answers), state)

    def test_blocker_choice_not_highest_probability_raises(self):
        state = _valid_state()
        answers = make_answers(state, blocker="facts_missing")
        answers["blocker_class"]["probabilities"] = {
            "user_preference_unknown": 0.1,
            "facts_missing": 0.2,
            "material_bias": 0.1,
            "balanced_tie": 0.6,
        }
        with pytest.raises(decide.ProviderError):
            decide.parse_answers(answers_body(answers), state)

    def test_new_questions_required_in_build_request(self):
        payload = decide.build_request(_valid_state(), "m")
        assert payload["questions"]["evidence_sufficiency"] == {
            "type": "noul",
            "instructions": decide.SUFFICIENCY_INSTRUCTIONS,
        }
        blocker = payload["questions"]["blocker_class"]
        assert blocker["type"] == "choice"
        assert blocker["instructions"] == decide.BLOCKER_INSTRUCTIONS
        assert blocker["criteria"] == decide.BLOCKER_DESCRIPTIONS
        assert set(blocker["criteria"]) == set(decide.BLOCKER_CLASSES)
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `python3 -m pytest tests/test_decide.py -v`
Expected: FAIL(`SUFFICIENCY_INSTRUCTIONS` が無い、`make_answers` が `sufficiency` を受け付けない等の AttributeError / KeyError)

- [ ] **Step 3: 実装**

`skills/autarch/scripts/decide.py`。`CHOICE_INSTRUCTIONS` 定義の後に追加:

```python
SUFFICIENCY_INSTRUCTIONS = (
    "Is there enough evidence in the state to select an option automatically?"
)
BLOCKER_INSTRUCTIONS = (
    "The decision cannot be resolved automatically on the provided "
    "material. Select the primary blocker."
)
BLOCKER_CLASSES = (
    "user_preference_unknown",
    "facts_missing",
    "material_bias",
    "balanced_tie",
)
BLOCKER_DESCRIPTIONS = {
    "user_preference_unknown": (
        "The user's preference, plan, or intent is needed and not present "
        "in the state"
    ),
    "facts_missing": (
        "A technical fact needed to compare the alternatives is missing "
        "from the evidence"
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

`build_request` の `questions` dict に2つ追加(`best_option` の直後、score ループの前):

```python
    questions = {
        "requires_human_preference": {
            "type": "noul",
            "instructions": NOUL_INSTRUCTIONS,
        },
        "best_option": {
            "type": "choice",
            "instructions": CHOICE_INSTRUCTIONS,
            "criteria": {
                alternative["id"]: f"{alternative['name']}: {alternative['description']}"
                for alternative in alternatives
            },
        },
        "evidence_sufficiency": {
            "type": "noul",
            "instructions": SUFFICIENCY_INSTRUCTIONS,
        },
        "blocker_class": {
            "type": "choice",
            "instructions": BLOCKER_INSTRUCTIONS,
            "criteria": dict(BLOCKER_DESCRIPTIONS),
        },
    }
```

`parse_answers` の `probabilities` 構築後(score ループの前)に追加:

```python
    sufficiency_answer = answers.get("evidence_sufficiency")
    if (not isinstance(sufficiency_answer, dict)
            or sufficiency_answer.get("type") != "noul"):
        raise ProviderError(
            "evidence_sufficiency answer is missing or has wrong type"
        )
    evidence_sufficiency = _require_number(
        sufficiency_answer.get("noul"), 0.0, 1.0, "evidence_sufficiency.noul"
    )

    blocker_answer = answers.get("blocker_class")
    if (not isinstance(blocker_answer, dict)
            or blocker_answer.get("type") != "choice"):
        raise ProviderError("blocker_class answer is missing or has wrong type")
    blocker = blocker_answer.get("choice")
    if blocker not in BLOCKER_CLASSES:
        raise ProviderError("blocker_class.choice is not one of the blocker classes")
    blocker_confidence = _require_number(
        blocker_answer.get("confidence"), 0.0, 1.0, "blocker_class.confidence"
    )
    raw_blocker_probabilities = blocker_answer.get("probabilities")
    if (not isinstance(raw_blocker_probabilities, dict)
            or set(raw_blocker_probabilities) != set(BLOCKER_CLASSES)):
        raise ProviderError(
            "blocker_class.probabilities must cover every blocker class"
        )
    blocker_probabilities = {
        name: _require_number(
            value, 0.0, 1.0, f"blocker_class.probabilities[{name}]"
        )
        for name, value in raw_blocker_probabilities.items()
    }
    if blocker_probabilities[blocker] != max(blocker_probabilities.values()):
        raise ProviderError(
            "blocker_class.choice does not match the highest probability"
        )
```

返り値 dict に追加:

```python
    return {
        "human_preference": human_preference,
        "choice": selected,
        "confidence": confidence,
        "probabilities": probabilities,
        "scores": scores,
        "evidence_sufficiency": evidence_sufficiency,
        "blocker_class": blocker,
        "blocker_confidence": blocker_confidence,
    }
```

- [ ] **Step 4: テストが通ることを確認**

Run: `python3 -m pytest tests/test_decide.py -v`
Expected: 全 PASS(既存テストも含む。`make_answers` の既定でゲート閉なので既存の resolve テストは影響なし)

- [ ] **Step 5: Commit**

```bash
git add skills/autarch/scripts/decide.py tests/test_decide.py
git commit -m "feat: ask Jev for evidence sufficiency and blocker classification

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 2: decide.py — 根拠充足性ゲート・revision 検証・CLI フラグ・log record

**Files:**
- Modify: `skills/autarch/scripts/decide.py`(`validate_state`・`resolve`・`_empty_resolution`・`build_log_record`・`main`)
- Test: `tests/test_decide.py`

**Interfaces:**
- Consumes: Task 1 の `parsed["evidence_sufficiency"]` / `parsed["blocker_class"]` / `parsed["blocker_confidence"]`
- Produces: `resolve()` が出力する `rule` の新値 `evidence_insufficient` / `investigation_exhausted` とフィールド `evidence_sufficiency`・`blocker_class`・`blocker_confidence`。CLI フラグ `--sufficiency` / `--blocker-confidence`。thresholds dict のキー `sufficiency` / `blocker_confidence`(Task 6 が runner 経由で使用)

- [ ] **Step 1: 失敗テストを書く**

`test_module_exposes_constants` に追記:

```python
    assert decide.DEFAULT_SUFFICIENCY == 0.60
    assert decide.DEFAULT_BLOCKER_CONFIDENCE == 0.50
    assert decide.REVISION_ACTIONS == ("investigation", "material_fix")
    assert decide.REVISION_SUMMARY_LIMIT == 500
```

`_thresholds()` ヘルパーを更新:

```python
def _thresholds():
    return {
        "auto_select": 0.85,
        "review": 0.60,
        "min_gap": 0.15,
        "human_preference": 0.70,
        "sufficiency": 0.60,
        "blocker_confidence": 0.50,
    }
```

`TestValidateState` の後に新規クラス:

```python
class TestValidateStateRevision:
    def _state(self):
        state = _valid_state()
        state["revision"] = {
            "round": 1,
            "action": "investigation",
            "summary": "checked pyproject.toml and README",
        }
        return state

    def test_valid_revision_passes(self):
        assert decide.validate_state(self._state()) == []

    def test_revision_absent_is_fine(self):
        assert decide.validate_state(_valid_state()) == []

    def test_revision_must_be_object(self):
        state = _valid_state()
        state["revision"] = ["round 1"]
        assert any("revision must be an object" in e
                   for e in decide.validate_state(state))

    def test_round_must_be_exactly_one(self):
        for bad in (0, 2, True, None, "1", 1.5):
            state = self._state()
            state["revision"]["round"] = bad
            assert any("revision.round" in e
                       for e in decide.validate_state(state)), bad

    def test_action_must_be_known(self):
        state = self._state()
        state["revision"]["action"] = "rethinking"
        assert any("revision.action" in e for e in decide.validate_state(state))

    def test_summary_must_be_non_empty_string(self):
        state = self._state()
        state["revision"]["summary"] = "   "
        assert any("revision.summary" in e for e in decide.validate_state(state))

    def test_summary_length_capped(self):
        state = self._state()
        state["revision"]["summary"] = "x" * 501
        assert any("revision.summary" in e for e in decide.validate_state(state))

    def test_revision_summary_secret_pattern_is_redacted(self):
        state = self._state()
        state["revision"]["summary"] = "found key sk-abcdef1234567890 in config"
        redacted, count = decide.redact(state)
        assert "sk-abcdef1234567890" not in redacted["revision"]["summary"]
        assert count == 1
```

`TestResolve` の後に新規クラス:

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

    def test_every_blocker_class_blocks_auto_select(self):
        for blocker in decide.BLOCKER_CLASSES:
            resolution = self._run(confidence=0.95, sufficiency=0.1,
                                   blocker=blocker, blocker_confidence=0.9)
            assert resolution["decision"] == "ASK_USER", blocker
            assert resolution["blocker_class"] == blocker

    def test_low_blocker_confidence_falls_back_to_legacy_rules(self):
        resolution = self._run(choice="option_a", confidence=0.95,
                               sufficiency=0.2, blocker_confidence=0.3)
        assert resolution["decision"] == "SELECT_OPTION"
        assert resolution["rule"] == "confidence"
        assert resolution["blocker_class"] is None

    def test_sufficient_evidence_skips_gate(self):
        resolution = self._run(choice="option_a", confidence=0.95,
                               sufficiency=0.9)
        assert resolution["decision"] == "SELECT_OPTION"
        assert resolution["blocker_class"] is None

    def test_human_preference_rule_precedes_gate(self):
        resolution = self._run(noul=0.9, confidence=0.95, sufficiency=0.1,
                               blocker="user_preference_unknown",
                               blocker_confidence=0.9)
        assert resolution["rule"] == "human_preference"

    def test_preference_blocker_ignores_revision(self):
        state = _valid_state()
        state["revision"] = {"round": 1, "action": "investigation",
                             "summary": "checked the repository"}
        resolution = self._run(state=state, confidence=0.95, sufficiency=0.1,
                               blocker="user_preference_unknown",
                               blocker_confidence=0.9)
        assert resolution["rule"] == "evidence_insufficient"

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
```

`TestMain` に追記:

```python
    def test_sufficiency_flags_plumb_through(self, tmp_path, monkeypatch, capsys):
        state = _valid_state()
        answers = make_answers(state, choice="option_a", confidence=0.95,
                               sufficiency=0.55, blocker="facts_missing",
                               blocker_confidence=0.9)
        self._patch_api(monkeypatch, answers)
        self._patch_log(monkeypatch, tmp_path)
        state_file = self._write_state(tmp_path, state)
        # Default threshold 0.60 -> gate fires (0.55 < 0.60).
        decide.main([f"--state-file={state_file}"])
        output = json.loads(capsys.readouterr().out)
        assert output["rule"] == "evidence_insufficient"
        # Raised threshold 0.50 -> gate stays closed, legacy rules select.
        self._patch_api(monkeypatch, answers)
        decide.main([f"--state-file={state_file}", "--sufficiency", "0.5"])
        output = json.loads(capsys.readouterr().out)
        assert output["decision"] == "SELECT_OPTION"

    def test_invalid_revision_is_insufficient_options(self, tmp_path, monkeypatch,
                                                      capsys):
        state = _valid_state()
        state["revision"] = {"round": 2, "action": "investigation",
                             "summary": "second attempt"}
        self._patch_log(monkeypatch, tmp_path)
        decide.main([f"--state-file={self._write_state(tmp_path, state)}"])
        output = json.loads(capsys.readouterr().out)
        assert output["decision"] == "INSUFFICIENT_OPTIONS"
        assert "revision.round" in output["detail"]
```

既存テスト `test_build_log_record_shape_and_sanitization` を更新: `output` dict に `"evidence_sufficiency": 0.9, "blocker_class": None` を追加し、期待 set に `"evidence_sufficiency"`, `"blocker_class"` を追加。

- [ ] **Step 2: テストが失敗することを確認**

Run: `python3 -m pytest tests/test_decide.py -v`
Expected: FAIL(新クラスが AttributeError / 期待と異なる rule)

- [ ] **Step 3: 実装**

`skills/autarch/scripts/decide.py`。

定数(`DEFAULT_HUMAN_PREFERENCE` の後):

```python
DEFAULT_SUFFICIENCY = 0.60
DEFAULT_BLOCKER_CONFIDENCE = 0.50

REVISION_ACTIONS = ("investigation", "material_fix")
REVISION_SUMMARY_LIMIT = 500
```

`validate_state` の criteria 検証ブロックの後・`return errors` の前に追加:

```python
    revision = state.get("revision")
    if revision is not None:
        if not isinstance(revision, dict):
            errors.append("revision must be an object")
        else:
            round_value = revision.get("round")
            if (not isinstance(round_value, int) or isinstance(round_value, bool)
                    or round_value != 1):
                errors.append("revision.round must be 1")
            if revision.get("action") not in REVISION_ACTIONS:
                errors.append(
                    "revision.action must be one of " + str(REVISION_ACTIONS)
                )
            summary = revision.get("summary")
            if not isinstance(summary, str) or not summary.strip():
                errors.append("revision.summary must be a non-empty string")
            elif len(summary) > REVISION_SUMMARY_LIMIT:
                errors.append(
                    "revision.summary must be at most "
                    f"{REVISION_SUMMARY_LIMIT} characters"
                )
```

`resolve()`: resolution 初期化 dict に3フィールド追加:

```python
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
        "reason": "",
    }
```

human_preference ブロックの return の直後にゲートを挿入:

```python
    gate_fires = (
        parsed["evidence_sufficiency"] < thresholds["sufficiency"]
        and parsed["blocker_confidence"] >= thresholds["blocker_confidence"]
    )
    if gate_fires:
        blocker = parsed["blocker_class"]
        resolution["blocker_class"] = blocker
        resolution["blocker_confidence"] = parsed["blocker_confidence"]
        has_revision = isinstance(state.get("revision"), dict)
        if has_revision and blocker in ("facts_missing", "material_bias"):
            resolution["decision"] = "ASK_USER"
            resolution["rule"] = "investigation_exhausted"
            resolution["reason"] = (
                "The single investigation round has been spent and the "
                "evidence still does not support automatic selection; "
                "returning the decision to the user."
            )
        else:
            resolution["decision"] = "ASK_USER"
            resolution["rule"] = "evidence_insufficient"
            resolution["reason"] = (
                f"Jev classifies the decision blocker as '{blocker}' "
                f"(evidence sufficiency {parsed['evidence_sufficiency']:.2f}); "
                "the evidence does not support automatic selection."
            )
        return resolution
```

`_empty_resolution` に3フィールド追加(`"reason": ""` の前あたり、既存スタイルに合わせて):

```python
def _empty_resolution(decision: str, rule: str) -> dict:
    return {
        "decision": decision,
        "rule": rule,
        "selected_option": None,
        "confidence": None,
        "probability": None,
        "probabilities": None,
        "human_preference_probability": None,
        "score_summary": None,
        "evidence_sufficiency": None,
        "blocker_class": None,
        "blocker_confidence": None,
        "reason": "",
    }
```

`build_log_record` の返り値に追加(`"resolution"` の前):

```python
        "evidence_sufficiency": output.get("evidence_sufficiency"),
        "blocker_class": output.get("blocker_class"),
```

`main()`: argparse に2つ追加(`--human-preference` の後):

```python
    parser.add_argument("--sufficiency", type=float, default=DEFAULT_SUFFICIENCY)
    parser.add_argument(
        "--blocker-confidence", type=float, default=DEFAULT_BLOCKER_CONFIDENCE
    )
```

thresholds dict に2キー追加:

```python
    thresholds = {
        "auto_select": args.auto_select,
        "review": args.review,
        "min_gap": args.min_gap,
        "human_preference": args.human_preference,
        "sufficiency": args.sufficiency,
        "blocker_confidence": args.blocker_confidence,
    }
```

- [ ] **Step 4: テストが通ることを確認**

Run: `python3 -m pytest tests/test_decide.py -v && python3 -m pytest`
Expected: 全 PASS(全体 160+ 件。SKILL.md テスト等も影響ないはず)

- [ ] **Step 5: Commit**

```bash
git add skills/autarch/scripts/decide.py tests/test_decide.py
git commit -m "feat: gate auto-selection on evidence sufficiency with one revision round

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 3: SKILL.md — Step 8 の出力一覧追記と Step 11 の分岐書き換え

**Files:**
- Modify: `skills/autarch/SKILL.md`(Step 8・Step 11 のみ。他ステップ・frontmatter 不変)
- Test: `tests/test_skill_md.py`

**Interfaces:**
- Consumes: Task 2 の rule 値 `evidence_insufficient` / `investigation_exhausted` とフィールド `blocker_class`
- Produces: agent が従う調査ループ手順(Task 9 の full-flow 再実行で行使される)

- [ ] **Step 1: 失敗テストを書く**

`tests/test_skill_md.py` の `TestSkillMarkdown` に追記:

```python
    def test_step8_documents_new_resolution_fields(self):
        text = _read()
        assert "evidence_sufficiency" in text
        assert "blocker_class" in text
        assert "blocker_confidence" in text

    def test_ask_user_dispatches_on_blocker_class(self):
        text = _read()
        assert "evidence_insufficient" in text
        assert "investigation_exhausted" in text
        assert "material_bias" in text

    def test_investigation_loop_instructions(self):
        text = _read()
        assert "investigate once" in text
        assert '"revision"' in text
        assert "exactly one more time" in text
        assert "external documentation" in text
        assert "Never invent facts" in text
        assert "material_fix" in text
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `python3 -m pytest tests/test_skill_md.py -v`
Expected: FAIL(新フィールド名・ループ指示がまだ無い)

- [ ] **Step 3: 実装**

`skills/autarch/SKILL.md`。

Step 8 の1文を置換(フィールド一覧に3つ追加):

```markdown
stdout contains exactly one JSON object with: `decision`, `rule`,
`selected_option`, `confidence`, `probability`, `probabilities`,
`human_preference_probability`, `score_summary`, `evidence_sufficiency`,
`blocker_class`, `blocker_confidence`, `reason`, `detail`, `model`.
```

Step 11 全体(見出しから Step 12 見出しの直前まで)を次の内容で置換。JWT 例は現行のものをそのまま残す:

````markdown
### Step 11 — ASK_USER

Do NOT repeat the original technical question. Dispatch on `rule` and
`blocker_class`:

**`evidence_insufficient`, blocker `facts_missing`, no `revision` in the
state — investigate once, then re-run.** Check repository configuration,
code, and documentation first; if the repository does not answer the
question, consult external documentation or web search. This whole
investigation is one round. Append each discovered fact to `evidence`
as a string with its source noted in one short phrase (example:
`"the app runs as a single local CLI tool (pyproject.toml, README)"`).
Never invent facts — if nothing is found, continue anyway. Then add to
the state:

```json
"revision": {"round": 1, "action": "investigation",
             "summary": "what you checked and what you found"}
```

and re-run decide.py on the updated state exactly one more time. If
that second run returns `PROVIDER_UNAVAILABLE`, follow Step 12 — do
not call Jev again.

**`evidence_insufficient`, blocker `material_bias`, no `revision` —
rebalance the material in the same single round.** Rewrite the
alternative descriptions with the same structure and comparable level
of detail, neutrally. Set `"revision": {"round": 1, "action":
"material_fix", "summary": "..."}` and re-run decide.py once.

**`investigation_exhausted` — the revision round is spent and the
evidence is still insufficient.** Return to the user without another
decide.py run: list what was confirmed (verified facts with sources)
and what remains unverified, then ask the single deciding question as
below.

**Blocker `user_preference_unknown` or `balanced_tie`, or rule
`human_preference`** — the decision depends on the user's taste,
plans, or a deciding priority. Ask for that preference or priority
directly instead of technical details.

**Any other `rule`** (`low_confidence`, `probability_gap`,
`choice_score_disagreement`) — using `rule`, `score_summary`,
`probabilities`, and your evidence, reduce the decision to the
smallest question only the user can answer — usually one
distinguishing factor. Present the options as a short list with
one-line neutral descriptors, name the deciding factor, and ask only
that. Example:

```text
Autarch could not decide this on technical merit alone.

The difference comes down to one thing: whether this system will
also be used from mobile apps or external APIs in the future.

A. JWT — suited to multiple clients / external APIs
B. Session Cookie — simplest for this same-origin web app

Do you have such a plan, yes or no?
```

Whatever the branch: never select an option yourself when the engine
says ASK_USER.
````

- [ ] **Step 4: テストが通ることを確認**

Run: `python3 -m pytest tests/test_skill_md.py -v`
Expected: 全 PASS(Step 1〜13 の存在検証も含む)

- [ ] **Step 5: Commit**

```bash
git add skills/autarch/SKILL.md tests/test_skill_md.py
git commit -m "docs: add investigation loop dispatch to SKILL.md ASK_USER step

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 4: case_schema.py — loop ケースの検証と位相2 state 構築

**Files:**
- Modify: `evals/case_schema.py`
- Test: `tests/test_case_schema.py`

**Interfaces:**
- Consumes: 既有 `_validate_expectations(exp, alternative_ids)`・`load_cases` の構造・Task 2 の `revision` 制約
- Produces: `BLOCKER_CLASSES`・`LOOP_SITUATION = "loop_resolvable"`・`validate_loop_case(case) -> list[str]`・`load_loop_cases(cases_dir) -> list`・`loop_phase2_state(case) -> dict`(Task 5・6・7 が使用)

- [ ] **Step 1: 失敗テストを書く**

`tests/test_case_schema.py` に追記:

```python
import decide
import pytest


def valid_loop_case():
    return {
        "id": "db_loop_resolvable",
        "topic": "database",
        "situation": "loop_resolvable",
        "state": {
            "goal": "Choose a storage engine",
            "question": "Which storage approach best fits?",
            "known_constraints": [],
            "environment": {},
            "evidence": ["records are short structured notes"],
            "alternatives": [
                {"id": "sqlite", "name": "SQLite",
                 "description": "An embedded single-file database."},
                {"id": "postgres", "name": "PostgreSQL",
                 "description": "A client-server relational database."},
            ],
            "criteria": [],
        },
        "investigation": {
            "injected_evidence": [
                "the app runs as a single local CLI tool with no server component"
            ],
            "phase1": {"rule": "evidence_insufficient",
                       "blocker_class": "facts_missing"},
            "phase2": {
                "acceptable_decisions": ["SELECT_OPTION",
                                         "SELECT_OPTION_WITH_CAUTION"],
                "acceptable_selections": ["sqlite"],
                "forbidden_selections": [],
            },
        },
        "derived_from": None,
    }


class TestValidateLoopCase:
    def test_valid_case_passes(self):
        assert case_schema.validate_loop_case(valid_loop_case()) == []

    def test_situation_must_be_loop_resolvable(self):
        case = valid_loop_case()
        case["situation"] = "info_missing"
        assert any("situation" in e for e in case_schema.validate_loop_case(case))

    def test_state_must_not_include_revision(self):
        case = valid_loop_case()
        case["state"]["revision"] = {"round": 1, "action": "investigation",
                                     "summary": "pre-run"}
        assert any("revision" in e for e in case_schema.validate_loop_case(case))

    def test_phase1_rule_must_be_evidence_insufficient(self):
        case = valid_loop_case()
        case["investigation"]["phase1"]["rule"] = "low_confidence"
        assert any("phase1" in e for e in case_schema.validate_loop_case(case))

    def test_phase1_blocker_must_be_known(self):
        case = valid_loop_case()
        case["investigation"]["phase1"]["blocker_class"] = "mood_unknown"
        assert any("phase1" in e for e in case_schema.validate_loop_case(case))

    def test_phase2_must_include_a_selection_decision(self):
        case = valid_loop_case()
        case["investigation"]["phase2"] = {
            "acceptable_decisions": ["ASK_USER"],
            "acceptable_selections": [],
            "forbidden_selections": [],
        }
        assert any("phase2.acceptable_decisions" in e
                   for e in case_schema.validate_loop_case(case))

    def test_phase2_selections_reference_unknown_ids_rejected(self):
        case = valid_loop_case()
        case["investigation"]["phase2"]["acceptable_selections"] = ["redis"]
        assert any("unknown alternative ids" in e
                   for e in case_schema.validate_loop_case(case))

    def test_injected_evidence_must_be_non_empty_strings(self):
        case = valid_loop_case()
        case["investigation"]["injected_evidence"] = ["  "]
        assert any("injected_evidence" in e
                   for e in case_schema.validate_loop_case(case))

    def test_derived_from_must_be_null(self):
        case = valid_loop_case()
        case["derived_from"] = {"base": "db_constraint_clear",
                                "perturbation": "reorder"}
        assert any("derived_from" in e
                   for e in case_schema.validate_loop_case(case))


class TestLoadLoopCases:
    def test_loads_valid_directory(self, tmp_path):
        (tmp_path / "a.json").write_text(json.dumps(valid_loop_case()),
                                         encoding="utf-8")
        cases = case_schema.load_loop_cases(tmp_path)
        assert [c["id"] for c in cases] == ["db_loop_resolvable"]

    def test_invalid_file_raises(self, tmp_path):
        case = valid_loop_case()
        case["investigation"].pop("phase2")
        (tmp_path / "a.json").write_text(json.dumps(case), encoding="utf-8")
        with pytest.raises(case_schema.CaseError):
            case_schema.load_loop_cases(tmp_path)

    def test_duplicate_ids_raise(self, tmp_path):
        payload = json.dumps(valid_loop_case())
        (tmp_path / "a.json").write_text(payload, encoding="utf-8")
        (tmp_path / "b.json").write_text(payload, encoding="utf-8")
        with pytest.raises(case_schema.CaseError):
            case_schema.load_loop_cases(tmp_path)


class TestLoopPhase2State:
    def test_appends_evidence_and_sets_revision(self):
        case = valid_loop_case()
        snapshot = json.loads(json.dumps(case))
        state = case_schema.loop_phase2_state(case)
        assert state["evidence"] == (
            case["state"]["evidence"]
            + case["investigation"]["injected_evidence"]
        )
        assert state["revision"] == {
            "round": 1,
            "action": "investigation",
            "summary": "injected by eval runner",
        }
        assert case == snapshot  # input not mutated

    def test_phase2_state_passes_engine_validation(self):
        state = case_schema.loop_phase2_state(valid_loop_case())
        assert decide.validate_state(state) == []
```

(既存 `test_case_schema.py` が `import json` `import case_schema` 済みであることを確認。未 import のものは追記する。)

- [ ] **Step 2: テストが失敗することを確認**

Run: `python3 -m pytest tests/test_case_schema.py -v`
Expected: FAIL(`validate_loop_case` が未定義)

- [ ] **Step 3: 実装**

`evals/case_schema.py`。先頭 import に `copy` を追加:

```python
import copy
import json
from pathlib import Path
```

`PERTURBED_TOPICS` の後に定数を追加:

```python
LOOP_SITUATION = "loop_resolvable"
BLOCKER_CLASSES = (
    "user_preference_unknown",
    "facts_missing",
    "material_bias",
    "balanced_tie",
)
```

`validate_scenario_expectations` の後に3関数を追加:

```python
def validate_loop_case(case):
    """Validate one two-phase loop case. Returns violations (empty = valid)."""
    if not isinstance(case, dict):
        return ["case must be a JSON object"]
    errors = []
    if not isinstance(case.get("id"), str) or not case["id"]:
        errors.append("id must be a non-empty string")
    if case.get("topic") not in TOPICS:
        errors.append("topic must be one of " + str(TOPICS))
    if case.get("situation") != LOOP_SITUATION:
        errors.append("situation must be " + LOOP_SITUATION)
    state = case.get("state")
    if not isinstance(state, dict):
        errors.append("state must be an object")
        state = {}
    if state.get("revision") is not None:
        errors.append("loop case state must not include revision")
    alternatives = state.get("alternatives")
    alternative_ids = (
        [a.get("id") for a in alternatives if isinstance(a, dict)]
        if isinstance(alternatives, list) else []
    )
    investigation = case.get("investigation")
    if not isinstance(investigation, dict):
        errors.append("investigation must be an object")
    else:
        injected = investigation.get("injected_evidence")
        if (not isinstance(injected, list) or not injected
                or not all(isinstance(item, str) and item.strip()
                           for item in injected)):
            errors.append(
                "injected_evidence must be a non-empty list of non-empty strings"
            )
        phase1 = investigation.get("phase1")
        if (not isinstance(phase1, dict)
                or phase1.get("rule") != "evidence_insufficient"
                or phase1.get("blocker_class") not in BLOCKER_CLASSES):
            errors.append(
                'phase1 must be {"rule": "evidence_insufficient", '
                '"blocker_class": one of ' + str(BLOCKER_CLASSES) + "}"
            )
        phase2 = investigation.get("phase2")
        if not isinstance(phase2, dict):
            errors.append("phase2 must be an object")
        else:
            errors.extend(_validate_expectations(phase2, alternative_ids))
            decisions = phase2.get("acceptable_decisions")
            if isinstance(decisions, list) and not (
                    set(decisions)
                    & {"SELECT_OPTION", "SELECT_OPTION_WITH_CAUTION"}
            ):
                errors.append(
                    "phase2.acceptable_decisions must include a selection decision"
                )
    if case.get("derived_from") is not None:
        errors.append("derived_from must be null for loop cases")
    return errors


def load_loop_cases(cases_dir):
    """Load and validate every loop case file in cases_dir (sorted by filename)."""
    cases = []
    violations = []
    for path in sorted(Path(cases_dir).glob("*.json")):
        try:
            case = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise CaseError(
                f"{path.name}: cannot load ({type(error).__name__})"
            ) from None
        errors = validate_loop_case(case)
        if errors:
            violations.append(f"{path.name}: " + "; ".join(errors))
        cases.append(case)
    if violations:
        raise CaseError(
            "invalid loop case files:\n  - " + "\n  - ".join(violations)
        )
    ids = [case.get("id") for case in cases]
    if len(ids) != len(set(ids)):
        raise CaseError("duplicate loop case ids: " + str(sorted(ids)))
    return cases


def loop_phase2_state(case):
    """The post-investigation state: injected evidence plus a spent revision."""
    state = copy.deepcopy(case["state"])
    state["evidence"] = list(state.get("evidence", [])) + list(
        case["investigation"]["injected_evidence"]
    )
    state["revision"] = {
        "round": 1,
        "action": "investigation",
        "summary": "injected by eval runner",
    }
    return state
```

- [ ] **Step 4: テストが通ることを確認**

Run: `python3 -m pytest tests/test_case_schema.py -v`
Expected: 全 PASS

- [ ] **Step 5: Commit**

```bash
git add evals/case_schema.py tests/test_case_schema.py
git commit -m "feat: add two-phase loop case schema and phase-2 state builder

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 5: cases_loop/ — 2段階ケース3件とメタテスト

**Files:**
- Create: `evals/cases_loop/db_loop_resolvable.json`
- Create: `evals/cases_loop/auth_loop_resolvable.json`
- Create: `evals/cases_loop/deploy_loop_resolvable.json`
- Test: `tests/test_eval_loop_cases.py`

**Interfaces:**
- Consumes: Task 4 の `load_loop_cases`・`loop_phase2_state`
- Produces: loop ケース3件(Task 6 の runner と Task 9 の再実行が使用)。位相1は薄い state で `rule=evidence_insufficient` + `blocker_class=facts_missing`、位相2は注入後に正解候補が選ばれることを期待する

- [ ] **Step 1: 失敗テストを書く**

`tests/test_eval_loop_cases.py` を新規作成:

```python
"""Meta-tests for the real loop case files in evals/cases_loop/."""

from pathlib import Path

import case_schema
import decide

REPO_ROOT = Path(__file__).resolve().parent.parent
LOOP_CASES_DIR = REPO_ROOT / "evals" / "cases_loop"
BASE_CASES_DIR = REPO_ROOT / "evals" / "cases"


def all_loop_cases():
    return case_schema.load_loop_cases(LOOP_CASES_DIR)


def test_all_loop_case_files_are_individually_valid():
    all_loop_cases()  # load_loop_cases raises CaseError on any invalid file


def test_loop_states_pass_engine_validation():
    for case in all_loop_cases():
        assert decide.validate_state(case["state"]) == [], case["id"]


def test_phase2_states_pass_engine_validation():
    for case in all_loop_cases():
        assert decide.validate_state(
            case_schema.loop_phase2_state(case)
        ) == [], case["id"]


def test_three_cases_with_distinct_topics():
    cases = all_loop_cases()
    assert len(cases) == 3
    assert {case["topic"] for case in cases} == {
        "database", "authentication", "deployment"
    }


def test_ids_do_not_collide_with_base_cases():
    base_ids = {case["id"] for case in case_schema.load_cases(BASE_CASES_DIR)}
    loop_ids = {case["id"] for case in all_loop_cases()}
    assert base_ids.isdisjoint(loop_ids)


def test_phase1_expects_facts_missing():
    for case in all_loop_cases():
        phase1 = case["investigation"]["phase1"]
        assert phase1["rule"] == "evidence_insufficient", case["id"]
        assert phase1["blocker_class"] == "facts_missing", case["id"]
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `python3 -m pytest tests/test_eval_loop_cases.py -v`
Expected: FAIL(`evals/cases_loop/` が存在せず load でエラー)

- [ ] **Step 3: ケースファイル3件を作成**

`evals/cases_loop/db_loop_resolvable.json`(db_info_missing の alternatives・criteria を再利用し、決め手の配置事実を欠かせた state):

```json
{
  "id": "db_loop_resolvable",
  "topic": "database",
  "situation": "loop_resolvable",
  "state": {
    "goal": "Choose a storage engine for the notes product",
    "question": "Which storage approach best fits the notes product?",
    "known_constraints": ["data must survive process restarts"],
    "environment": {"language": "python"},
    "evidence": [
      "records are short structured notes",
      "the team is comfortable with SQL"
    ],
    "alternatives": [
      {
        "id": "sqlite",
        "name": "SQLite",
        "description": "An embedded relational database stored in a single file, suited to local and single-host use.",
        "advantages": ["no server required", "single-file backups"],
        "disadvantages": ["limited concurrent write scaling"],
        "assumptions": []
      },
      {
        "id": "postgres",
        "name": "PostgreSQL",
        "description": "A client-server relational database that serves many concurrent clients.",
        "advantages": ["concurrent access", "mature operations tooling"],
        "disadvantages": ["requires running and operating a server"],
        "assumptions": []
      },
      {
        "id": "json_files",
        "name": "JSON files",
        "description": "Each note stored as one JSON file in a directory.",
        "advantages": ["no engine dependency", "trivially inspectable"],
        "disadvantages": ["manual consistency handling", "weaker querying"],
        "assumptions": []
      }
    ],
    "criteria": [
      {
        "id": "requirement_fit",
        "name": "Requirement fit",
        "weight": 0.6,
        "rubric": ["Poor fit", "Acceptable fit", "Good fit", "Excellent fit"]
      },
      {
        "id": "operational_burden",
        "name": "Operational burden",
        "weight": 0.4,
        "rubric": ["High burden", "Moderate burden", "Low burden"]
      }
    ]
  },
  "investigation": {
    "injected_evidence": [
      "the app runs as a single local CLI tool with no server component"
    ],
    "phase1": {"rule": "evidence_insufficient", "blocker_class": "facts_missing"},
    "phase2": {
      "acceptable_decisions": ["SELECT_OPTION", "SELECT_OPTION_WITH_CAUTION"],
      "acceptable_selections": ["sqlite"],
      "forbidden_selections": []
    }
  },
  "derived_from": null
}
```

`evals/cases_loop/auth_loop_resolvable.json`(auth_constraint_clear から same-origin を確立する evidence・constraints を抜いた薄い state):

```json
{
  "id": "auth_loop_resolvable",
  "topic": "authentication",
  "situation": "loop_resolvable",
  "state": {
    "goal": "Choose the authentication state strategy for the web app",
    "question": "Which authentication state strategy best fits this web app?",
    "known_constraints": [],
    "environment": {},
    "evidence": ["the app has a sign-in flow used by its own users"],
    "alternatives": [
      {
        "id": "session_cookie",
        "name": "Session cookie",
        "description": "Server-side session state keyed by a signed cookie sent by the browser.",
        "advantages": ["simple with the existing framework", "natural for same-origin browsers"],
        "disadvantages": ["needs session storage on the server"],
        "assumptions": []
      },
      {
        "id": "jwt_stateless",
        "name": "Stateless JWT",
        "description": "Cryptographic tokens carrying claims, validated without server-side session state.",
        "advantages": ["no server-side session store", "portable to other client types"],
        "disadvantages": ["token revocation is harder", "more moving parts than cookies"],
        "assumptions": []
      },
      {
        "id": "external_idp",
        "name": "External identity provider",
        "description": "Delegate sign-in to a hosted identity service and consume its tokens.",
        "advantages": ["outsources credential handling", "ready-made login UI"],
        "disadvantages": ["adds an external runtime dependency", "more setup for an internal app"],
        "assumptions": []
      }
    ],
    "criteria": [
      {
        "id": "requirement_fit",
        "name": "Requirement fit",
        "weight": 0.6,
        "rubric": ["Poor fit", "Acceptable fit", "Good fit", "Excellent fit"]
      },
      {
        "id": "implementation_cost",
        "name": "Implementation cost",
        "weight": 0.4,
        "rubric": ["High cost", "Moderate cost", "Low cost"]
      }
    ]
  },
  "investigation": {
    "injected_evidence": [
      "the app is served from one origin by its own web server",
      "the framework provides signed-cookie session support",
      "no mobile or third-party clients exist"
    ],
    "phase1": {"rule": "evidence_insufficient", "blocker_class": "facts_missing"},
    "phase2": {
      "acceptable_decisions": ["SELECT_OPTION", "SELECT_OPTION_WITH_CAUTION"],
      "acceptable_selections": ["session_cookie"],
      "forbidden_selections": []
    }
  },
  "derived_from": null
}
```

`evals/cases_loop/deploy_loop_resolvable.json`(deploy_constraint_clear から静的性・無料枠の確立を欠かせた state):

```json
{
  "id": "deploy_loop_resolvable",
  "topic": "deployment",
  "situation": "loop_resolvable",
  "state": {
    "goal": "Choose hosting for the documentation site",
    "question": "Where should the documentation site be hosted?",
    "known_constraints": ["must stay within free hosting tiers"],
    "environment": {},
    "evidence": ["the content is written as markdown sources"],
    "alternatives": [
      {
        "id": "static_host",
        "name": "Static site host",
        "description": "Serve the generated files from a hosting product built for static sites.",
        "advantages": ["free tier fits", "no servers to run"],
        "disadvantages": ["static content only"],
        "assumptions": []
      },
      {
        "id": "vps_self_host",
        "name": "Self-hosted VPS",
        "description": "Run a small virtual server and serve the files from it.",
        "advantages": ["full control of the environment"],
        "disadvantages": ["server upkeep for static files", "paid server"],
        "assumptions": []
      },
      {
        "id": "paas_container",
        "name": "Container platform",
        "description": "Package and deploy the site as a container to a managed platform.",
        "advantages": ["familiar deploy pipeline"],
        "disadvantages": ["runtime not needed for static files", "usually beyond free tiers"],
        "assumptions": []
      }
    ],
    "criteria": [
      {
        "id": "requirement_fit",
        "name": "Requirement fit",
        "weight": 0.6,
        "rubric": ["Poor fit", "Acceptable fit", "Good fit", "Excellent fit"]
      },
      {
        "id": "running_cost",
        "name": "Running cost",
        "weight": 0.4,
        "rubric": ["High cost", "Moderate cost", "Low cost"]
      }
    ]
  },
  "investigation": {
    "injected_evidence": [
      "the site generator outputs static HTML",
      "no dynamic endpoints exist"
    ],
    "phase1": {"rule": "evidence_insufficient", "blocker_class": "facts_missing"},
    "phase2": {
      "acceptable_decisions": ["SELECT_OPTION", "SELECT_OPTION_WITH_CAUTION"],
      "acceptable_selections": ["static_host"],
      "forbidden_selections": []
    }
  },
  "derived_from": null
}
```

- [ ] **Step 4: テストが通ることを確認**

Run: `python3 -m pytest tests/test_eval_loop_cases.py tests/test_case_schema.py -v`
Expected: 全 PASS

- [ ] **Step 5: Commit**

```bash
git add evals/cases_loop tests/test_eval_loop_cases.py
git commit -m "test: add three two-phase loop cases for the investigation loop

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 6: run_fixed_state.py — loop ケースの2段階実行

**Files:**
- Modify: `evals/run_fixed_state.py`(`run_once`・リトライ抽出・`main`)
- Test: `tests/test_run_fixed_state.py`

**Interfaces:**
- Consumes: Task 4 の `load_loop_cases`・`loop_phase2_state`。Task 2 の `--sufficiency` / `--blocker-confidence` フラグ
- Produces: loop 記録(`case_kind: "loop"`・`phase: 1|2` 付きの jsonl レコード)。`environment.json` の `thresholds.sufficiency` / `thresholds.blocker_confidence`・`loop_cases`(Task 7 が使用)。`run_with_retry(case, args, state_dir, state=None, phase=None)`

- [ ] **Step 1: 失敗テストを書く**

`tests/test_run_fixed_state.py` に追記:

```python
LOOP_STUB = '''#!/usr/bin/env python3
import json
import sys
from pathlib import Path

state_path = Path(sys.argv[sys.argv.index("--state-file") + 1])
state = json.loads(state_path.read_text(encoding="utf-8"))
if "revision" in state:
    print(json.dumps({
        "decision": "SELECT_OPTION", "rule": "confidence",
        "selected_option": state["alternatives"][0]["id"],
        "confidence": 0.9,
        "detail": f"evidence={len(state.get('evidence', []))} revision=True"}))
else:
    print(json.dumps({
        "decision": "ASK_USER", "rule": "evidence_insufficient",
        "blocker_class": "facts_missing", "blocker_confidence": 0.9,
        "evidence_sufficiency": 0.2,
        "detail": f"evidence={len(state.get('evidence', []))} revision=False"}))
'''


def write_loop_case(path):
    case = {
        "id": "db_loop_resolvable",
        "topic": "database",
        "situation": "loop_resolvable",
        "state": {
            "goal": "Pick storage", "question": "Which storage fits?",
            "known_constraints": [], "environment": {},
            "evidence": ["one thin fact"],
            "alternatives": [
                {"id": "alpha", "name": "Alpha",
                 "description": "First option.", "advantages": ["a"],
                 "disadvantages": ["d"], "assumptions": []},
                {"id": "beta", "name": "Beta",
                 "description": "Second option.", "advantages": ["a"],
                 "disadvantages": ["d"], "assumptions": []},
            ],
            "criteria": [],
        },
        "investigation": {
            "injected_evidence": ["the app runs as a single local CLI tool"],
            "phase1": {"rule": "evidence_insufficient",
                       "blocker_class": "facts_missing"},
            "phase2": {"acceptable_decisions": ["SELECT_OPTION"],
                       "acceptable_selections": ["alpha"],
                       "forbidden_selections": []},
        },
        "derived_from": None,
    }
    path.write_text(json.dumps(case), encoding="utf-8")


@pytest.fixture
def loop_stub(tmp_path):
    path = tmp_path / "loop_stub_decide.py"
    path.write_text(LOOP_STUB, encoding="utf-8")
    return str(path)


@pytest.fixture
def loop_cases_dir(tmp_path):
    directory = tmp_path / "loop_cases"
    directory.mkdir()
    write_loop_case(directory / "db_loop_resolvable.json")
    return directory


def test_loop_cases_run_two_phases(tmp_path, loop_stub, cases_dir,
                                   loop_cases_dir, monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    out_dir = tmp_path / "out"
    exit_code = run_fixed_state.main([
        "--cases-dir", str(cases_dir), "--loop-cases-dir", str(loop_cases_dir),
        "--decide-script", loop_stub, "--runs", "1",
        "--out-dir", str(out_dir), "--allow-partial-set", "--interval", "0",
    ])
    assert exit_code == 0
    records = [
        json.loads(line)
        for line in (out_dir / "fixed_state_runs.jsonl")
        .read_text().strip().splitlines()
    ]
    assert len(records) == 4  # 2 base + 2 phases of the loop case
    base_records = [r for r in records if r.get("case_kind") != "loop"]
    assert len(base_records) == 2
    for record in base_records:
        assert "case_kind" not in record
        assert "phase" not in record
    phase1, phase2 = [r for r in records if r.get("case_kind") == "loop"]
    assert phase1["phase"] == 1
    assert phase1["resolution"]["rule"] == "evidence_insufficient"
    assert phase1["classification"] == "asked"
    assert phase2["phase"] == 2
    assert phase2["resolution"]["decision"] == "SELECT_OPTION"
    # The phase-2 state carried the injected evidence and the revision.
    assert "revision=True" in phase2["resolution"]["detail"]
    assert "evidence=2" in phase2["resolution"]["detail"]
    environment = json.loads((out_dir / "environment.json").read_text())
    assert environment["thresholds"]["sufficiency"] == 0.6
    assert environment["thresholds"]["blocker_confidence"] == 0.5
    assert environment["loop_cases"] == ["db_loop_resolvable"]
    assert environment["total_api_calls"] == 4  # runs * (2 base + 2 phases)


def test_dry_run_counts_loop_phases(tmp_path, loop_stub, cases_dir,
                                    loop_cases_dir, capsys):
    exit_code = run_fixed_state.main([
        "--cases-dir", str(cases_dir), "--loop-cases-dir", str(loop_cases_dir),
        "--decide-script", loop_stub, "--runs", "2", "--dry-run",
        "--allow-partial-set",
    ])
    plan = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert plan["loop_cases"] == ["db_loop_resolvable"]
    assert plan["total_api_calls"] == 2 * (2 + 2)
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `python3 -m pytest tests/test_run_fixed_state.py -v`
Expected: FAIL(`--loop-cases-dir` が unrecognized argument)

- [ ] **Step 3: 実装**

`evals/run_fixed_state.py`。

`run_once` を拡張(state 上書きと phase・新フラグ):

```python
def run_once(case, args, state_dir, state=None, phase=None):
    effective_state = case["state"] if state is None else state
    suffix = "" if phase is None else f".phase{phase}"
    state_file = Path(state_dir) / f"{case['id']}{suffix}.json"
    state_file.write_text(
        json.dumps(effective_state, ensure_ascii=False), encoding="utf-8"
    )
    command = [
        sys.executable, str(args.decide_script),
        "--state-file", str(state_file),
        "--model", args.model,
        "--auto-select", str(args.auto_select),
        "--review", str(args.review),
        "--min-gap", str(args.min_gap),
        "--human-preference", str(args.human_preference),
        "--sufficiency", str(args.sufficiency),
        "--blocker-confidence", str(args.blocker_confidence),
    ]
    started = time.perf_counter()
    completed = subprocess.run(
        command, capture_output=True, text=True, timeout=args.timeout
    )
    latency_ms = round((time.perf_counter() - started) * 1000)
    try:
        resolution = json.loads(completed.stdout)
    except json.JSONDecodeError:
        resolution = {
            "decision": "PROVIDER_UNAVAILABLE",
            "rule": "provider_error",
            "detail": f"unparseable decide.py stdout (exit {completed.returncode})",
        }
    record = {
        "case_id": case["id"],
        "run_index": None,
        "attempt": None,
        "resolution": resolution,
        "latency_ms": latency_ms,
        "exit_code": completed.returncode,
        "recorded_at": runner_common.utc_now(),
    }
    if phase is not None:
        record["case_kind"] = "loop"
        record["phase"] = phase
    return record


def run_with_retry(case, args, state_dir, state=None, phase=None):
    """Run one decide.py call with the runner's transport-retry policy."""
    for attempt in range(1, 4):
        record = run_once(case, args, state_dir, state=state, phase=phase)
        record["attempt"] = attempt
        record["classification"] = judging.classify_run(record["resolution"])
        detail = record["resolution"].get("detail")
        retryable = (
            record["classification"] == "unavailable"
            and is_retryable(detail)
            and attempt < 3
        )
        if not retryable:
            break
        time.sleep(args.retry_backoff ** attempt)
    return record
```

argparse に追加(`--human-preference` の後):

```python
    parser.add_argument("--sufficiency", type=float, default=0.60)
    parser.add_argument("--blocker-confidence", type=float, default=0.50)
    parser.add_argument("--loop-cases-dir", default=None,
                        help="directory of two-phase loop cases to run additionally")
```

`--cases` 絞り込みの後に loop ケースの読み込みを追加:

```python
    loop_cases = []
    if args.loop_cases_dir:
        try:
            loop_cases = case_schema.load_loop_cases(args.loop_cases_dir)
        except case_schema.CaseError as error:
            print(f"error: {error}", file=sys.stderr)
            return 2
```

dry-run 出力を変更:

```python
    if args.dry_run:
        print(json.dumps({
            "runs_per_case": args.runs,
            "cases": [case["id"] for case in cases],
            "loop_cases": [case["id"] for case in loop_cases],
            "total_api_calls": args.runs * (len(cases) + 2 * len(loop_cases)),
        }, indent=2))
        return 0
```

実行ループを `run_with_retry` を使う形に書き換え、loop ループを追加:

```python
    with tempfile.TemporaryDirectory() as state_dir:
        for case in cases:
            for run_index in range(1, args.runs + 1):
                record = run_with_retry(case, args, state_dir)
                record["run_index"] = run_index
                runner_common.append_jsonl(runs_path, record)
                print(
                    f"{case['id']} run {run_index} attempt {record['attempt']}: "
                    f"{record['resolution'].get('decision')}",
                    file=sys.stderr,
                )
                time.sleep(args.interval)
        for case in loop_cases:
            for run_index in range(1, args.runs + 1):
                for phase in (1, 2):
                    state = (
                        case["state"] if phase == 1
                        else case_schema.loop_phase2_state(case)
                    )
                    record = run_with_retry(
                        case, args, state_dir, state=state, phase=phase
                    )
                    record["run_index"] = run_index
                    runner_common.append_jsonl(runs_path, record)
                    print(
                        f"{case['id']} run {run_index} phase {phase}: "
                        f"{record['resolution'].get('decision')}",
                        file=sys.stderr,
                    )
                    time.sleep(args.interval)
```

environment dict の `thresholds` に2キー追加、`total_api_calls` を更新、loop ケース一覧を追記:

```python
    environment = {
        "runner": "run_fixed_state.py",
        "model": args.model,
        "thresholds": {
            "auto_select": args.auto_select,
            "review": args.review,
            "min_gap": args.min_gap,
            "human_preference": args.human_preference,
            "sufficiency": args.sufficiency,
            "blocker_confidence": args.blocker_confidence,
        },
        "decide_script": str(args.decide_script),
        "runs_per_case": args.runs,
        "started_at": started_at,
        "finished_at": runner_common.utc_now(),
        "total_api_calls": args.runs * (len(cases) + 2 * len(loop_cases)),
    }
    if loop_cases:
        environment["loop_cases"] = [case["id"] for case in loop_cases]
```

- [ ] **Step 4: テストが通ることを確認**

Run: `python3 -m pytest tests/test_run_fixed_state.py -v && python3 -m pytest`
Expected: 全 PASS(既存の retry・dry-run テストも `run_with_retry` 抽出後も同じ挙動)

- [ ] **Step 5: Commit**

```bash
git add evals/run_fixed_state.py tests/test_run_fixed_state.py
git commit -m "feat: run two-phase loop cases in the fixed-state runner

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 7: report_baseline.py — loop 集計と baseline 比較

**Files:**
- Modify: `evals/report_baseline.py`
- Test: `tests/test_report_baseline.py`

**Interfaces:**
- Consumes: Task 4 の `load_loop_cases`。Task 6 の loop 記録形式(`case_kind` / `phase`)。`judging.py` は**読み出しのみ**(変更禁止)
- Produces: `baseline.json` の `loop_cases` セクション(`overall`: pass/fail/unavailable/loop_pass_rate + `per_case`)と `comparison` セクション。`SUMMARY.md` の「loop ケース」「baseline との比較」節。CLI `--loop-cases-dir` / `--compare-to`

- [ ] **Step 1: 失敗テストを書く**

`tests/test_report_baseline.py` に追記:

```python
LOOP_CASE = {
    "id": "db_loop_resolvable",
    "topic": "database",
    "situation": "loop_resolvable",
    "state": {
        "goal": "Pick storage", "question": "Which storage fits?",
        "known_constraints": [], "environment": {}, "evidence": ["e"],
        "alternatives": [mini_alternative("alpha"), mini_alternative("beta")],
        "criteria": [],
    },
    "investigation": {
        "injected_evidence": ["the app runs locally"],
        "phase1": {"rule": "evidence_insufficient",
                   "blocker_class": "facts_missing"},
        "phase2": {"acceptable_decisions": ["SELECT_OPTION"],
                   "acceptable_selections": ["alpha"],
                   "forbidden_selections": []},
    },
    "derived_from": None,
}


def loop_rec(run_index, phase, decision, rule, selected=None, blocker=None,
             classification=None):
    return {
        "case_id": "db_loop_resolvable", "run_index": run_index,
        "attempt": 1, "case_kind": "loop", "phase": phase,
        "resolution": {"decision": decision, "rule": rule,
                       "selected_option": selected, "blocker_class": blocker},
        "classification": classification or (
            "completed" if decision.startswith("SELECT") else "asked"),
        "latency_ms": 100, "exit_code": 0,
        "recorded_at": "2026-10-01T00:00:00Z",
    }


LOOP_RUNS = [
    loop_rec(1, 1, "ASK_USER", "evidence_insufficient",
             blocker="facts_missing"),
    loop_rec(1, 2, "SELECT_OPTION", "confidence", selected="alpha"),
    loop_rec(2, 1, "ASK_USER", "evidence_insufficient",
             blocker="facts_missing"),
    loop_rec(2, 2, "SELECT_OPTION", "confidence", selected="beta"),  # wrong pick
    loop_rec(3, 1, "ASK_USER", "evidence_insufficient",
             blocker="facts_missing"),
    loop_rec(3, 2, "PROVIDER_UNAVAILABLE", "provider_error",
             classification="unavailable"),
]


def prepare_with_loop(tmp_path):
    cases_dir, baseline_dir = prepare(tmp_path)
    loop_dir = tmp_path / "loop_cases"
    loop_dir.mkdir()
    (loop_dir / "a.json").write_text(json.dumps(LOOP_CASE), encoding="utf-8")
    with (baseline_dir / "fixed_state_runs.jsonl").open("a", encoding="utf-8") as handle:
        for record in LOOP_RUNS:
            handle.write(json.dumps(record) + "\n")
    return cases_dir, baseline_dir, loop_dir


def test_loop_metrics_and_exclusion_from_base_metrics(tmp_path):
    cases_dir, baseline_dir, loop_dir = prepare_with_loop(tmp_path)
    exit_code = report_baseline.main([
        "--baseline-dir", str(baseline_dir), "--cases-dir", str(cases_dir),
        "--loop-cases-dir", str(loop_dir),
    ])
    assert exit_code == 0
    baseline = json.loads(
        (baseline_dir / "baseline.json").read_text(encoding="utf-8")
    )
    # Loop records must not pollute the base-case metrics.
    assert baseline["fixed_state"]["overall"]["counts"]["judged"] == 6
    loop = baseline["loop_cases"]
    assert loop["overall"] == {
        "pass": 1, "fail": 1, "unavailable": 1, "loop_pass_rate": 0.5,
    }
    summary = (baseline_dir / "SUMMARY.md").read_text(encoding="utf-8")
    assert "loop ケース" in summary
    assert "db_loop_resolvable" in summary


def test_compare_to_produces_delta_table(tmp_path):
    cases_dir, baseline_dir, _ = prepare_with_loop(tmp_path)
    previous_path = tmp_path / "previous-baseline.json"
    previous_path.write_text(json.dumps({
        "fixed_state": {
            "overall": {"unsafe_auto_selection_rate": 0.5,
                        "appropriate_ask_rate": 0.5,
                        "completion_rate": 0.5,
                        "correct_selection_rate": 0.5},
            "perturbation_stability": {
                "evidence_removed": {"pass_rate": 0.0},
            },
        },
    }), encoding="utf-8")
    exit_code = report_baseline.main([
        "--baseline-dir", str(baseline_dir), "--cases-dir", str(cases_dir),
        "--compare-to", str(previous_path),
    ])
    assert exit_code == 0
    baseline = json.loads(
        (baseline_dir / "baseline.json").read_text(encoding="utf-8")
    )
    rows = {row["metric"]: row for row in baseline["comparison"]}
    unsafe = rows["Unsafe Auto-selection Rate"]
    assert unsafe["baseline"] == 0.5
    assert unsafe["current"] == round(1 / 6, 4)
    assert unsafe["delta"] == round(round(1 / 6, 4) - 0.5, 4)
    assert rows["perturbation pass rate: evidence_removed"]["baseline"] == 0.0
    summary = (baseline_dir / "SUMMARY.md").read_text(encoding="utf-8")
    assert "baseline との比較" in summary
    assert "evidence_removed" in summary


def test_compare_to_missing_file_exits_2(tmp_path, capsys):
    cases_dir, baseline_dir = prepare(tmp_path)
    exit_code = report_baseline.main([
        "--baseline-dir", str(baseline_dir), "--cases-dir", str(cases_dir),
        "--compare-to", str(tmp_path / "nope.json"),
    ])
    assert exit_code == 2
    assert "cannot read comparison baseline" in capsys.readouterr().err
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `python3 -m pytest tests/test_report_baseline.py -v`
Expected: FAIL(`--loop-cases-dir` / `--compare-to` が unrecognized)

- [ ] **Step 3: 実装**

`evals/report_baseline.py`。

`load_jsonl` の後にヘルパーと loop 集計を追加:

```python
def _ratio(numerator, denominator):
    return round(numerator / denominator, 4) if denominator else None


def _phase_label(record):
    if record is None:
        return "missing"
    resolution = record["resolution"]
    return f"{resolution.get('decision')}/{resolution.get('rule')}"


def _loop_verdict(case, phase_records):
    if any(
        record is None or record["classification"] == "unavailable"
        for record in phase_records.values()
    ):
        return "unavailable"
    expectations = case["investigation"]
    res1 = phase_records[1]["resolution"]
    phase1 = expectations["phase1"]
    phase1_ok = (
        res1.get("decision") == "ASK_USER"
        and res1.get("rule") == phase1["rule"]
        and res1.get("blocker_class") == phase1["blocker_class"]
    )
    res2 = phase_records[2]["resolution"]
    phase2 = expectations["phase2"]
    phase2_ok = res2.get("decision") in phase2.get("acceptable_decisions", [])
    if phase2_ok and res2.get("decision") in (
        "SELECT_OPTION", "SELECT_OPTION_WITH_CAUTION"
    ):
        phase2_ok = (
            res2.get("selected_option")
            in phase2.get("acceptable_selections", [])
        )
    return "pass" if phase1_ok and phase2_ok else "fail"


def loop_metrics(cases, runs):
    """Aggregate two-phase loop runs. Loop pass = phase1 AND phase2 ok."""
    loop_records = [run for run in runs if run.get("case_kind") == "loop"]
    per_case = []
    counts = {"pass": 0, "fail": 0, "unavailable": 0}
    for case in cases:
        entries = []
        run_indexes = sorted({
            run["run_index"] for run in loop_records
            if run["case_id"] == case["id"]
        })
        for run_index in run_indexes:
            phase_records = {}
            for phase in (1, 2):
                candidates = [
                    run for run in loop_records
                    if run["case_id"] == case["id"]
                    and run["run_index"] == run_index
                    and run.get("phase") == phase
                ]
                phase_records[phase] = candidates[-1] if candidates else None
            verdict = _loop_verdict(case, phase_records)
            counts[verdict] += 1
            entries.append({
                "run_index": run_index,
                "phase1": _phase_label(phase_records[1]),
                "phase2": _phase_label(phase_records[2]),
                "verdict": verdict,
            })
        per_case.append({
            "case_id": case["id"],
            "topic": case["topic"],
            "runs": entries,
        })
    return {
        "overall": {
            **counts,
            "loop_pass_rate": _ratio(counts["pass"],
                                     counts["pass"] + counts["fail"]),
        },
        "per_case": per_case,
    }


def comparison_rows(current, previous):
    """Comparable metric rows (base track) between two baseline documents."""
    rows = []
    cur_fixed = current["fixed_state"]["overall"]
    prev_fixed = (previous.get("fixed_state") or {}).get("overall") or {}
    for label, key in METRIC_LABELS:
        rows.append({
            "metric": label,
            "baseline": prev_fixed.get(key),
            "current": cur_fixed.get(key),
        })
    cur_pert = current["fixed_state"].get("perturbation_stability") or {}
    prev_pert = (
        (previous.get("fixed_state") or {}).get("perturbation_stability") or {}
    )
    for perturbation in sorted(cur_pert):
        rows.append({
            "metric": f"perturbation pass rate: {perturbation}",
            "baseline": (prev_pert.get(perturbation) or {}).get("pass_rate"),
            "current": cur_pert[perturbation].get("pass_rate"),
        })
    for row in rows:
        if (isinstance(row["baseline"], (int, float))
                and isinstance(row["current"], (int, float))):
            row["delta"] = round(row["current"] - row["baseline"], 4)
        else:
            row["delta"] = None
    return rows
```

`compute` を変更(シグネチャに `loop_cases=None` を追加。冒頭で base/loop を分離し、既存の `fixed_runs` 参照を `base_runs` に置き換える):

```python
def compute(cases, fixed_runs, full_runs, environment, loop_cases=None):
    base_runs = [run for run in fixed_runs if run.get("case_kind") != "loop"]
    per_case = []
```

(関数の中盤 — `entries` 構築の `for run in fixed_runs if ...` は `base_runs` に、返り値は次の形に:)

```python
    result = {
        "generated_at": runner_common.utc_now(),
        "environment": environment,
        "fixed_state": {
            "overall": judging.fixed_state_metrics(cases, base_runs),
            "by_run_index": judging.aggregate_by_run_index(cases, base_runs),
            "perturbation_stability": judging.perturbation_stability(
                cases, base_runs, auto_select
            ),
            "per_case": per_case,
        },
        "full_flow": {
            "per_scenario": full_runs,
            "rates": {
                key: scenario_rate(key)
                for key in ("coverage", "forbidden_avoided", "decision_ok",
                            "state_valid")
            },
        },
    }
    if loop_cases:
        result["loop_cases"] = loop_metrics(loop_cases, fixed_runs)
    return result
```

(元の `fixed_runs` は loop 集計だけが使う。既存テスト `test_render_summary_marks_na_for_missing_rates` は `compute` を位置引数4つで呼ぶ — `loop_cases` は末尾のキーワード引数なので影響しない)

`render_summary`: ケース別結果テーブルの後に loop 節、full-flow の後に比較節を追加:

```python
    if "loop_cases" in baseline:
        loop = baseline["loop_cases"]
        overall = loop["overall"]
        lines += [
            "",
            "## loop ケース(2段階)",
            "",
            f"pass {overall['pass']} / fail {overall['fail']}"
            f"(unavailable {overall['unavailable']} は分母から除外)。",
            "",
            "| case | run | phase1 | phase2 | 判定 |",
            "|---|---|---|---|---|",
        ]
        for case in loop["per_case"]:
            for run in case["runs"]:
                lines.append(
                    f"| {case['case_id']} | {run['run_index']} | "
                    f"{run['phase1']} | {run['phase2']} | {run['verdict']} |"
                )
```

(full-flow 節の後:)

```python
    if "comparison" in baseline:
        lines += [
            "",
            "## baseline との比較",
            "",
            "| 指標 | baseline | 今回 | 差分 |",
            "|---|---|---|---|",
        ]
        for row in baseline["comparison"]:
            lines.append(
                f"| {row['metric']} | {_fmt(row['baseline'])} | "
                f"{_fmt(row['current'])} | {_fmt(row['delta'])} |"
            )
```

`main()`: argparse に追加、loop ケース読み込み、compute 呼び出しと比較の差し込み:

```python
    parser.add_argument("--loop-cases-dir", default=None)
    parser.add_argument("--compare-to", default=None,
                        help="path to a previous baseline.json for comparison")
```

```python
    loop_cases = None
    if args.loop_cases_dir:
        try:
            loop_cases = case_schema.load_loop_cases(args.loop_cases_dir)
        except case_schema.CaseError as error:
            print(f"error: {error}", file=sys.stderr)
            return 2
```

```python
    baseline = compute(cases, fixed_runs, full_runs, environment,
                       loop_cases=loop_cases)
    if args.compare_to:
        try:
            previous = json.loads(
                Path(args.compare_to).read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as error:
            print(
                f"error: cannot read comparison baseline "
                f"({type(error).__name__})",
                file=sys.stderr,
            )
            return 2
        baseline["comparison"] = comparison_rows(baseline, previous)
```

- [ ] **Step 4: テストが通ることを確認**

Run: `python3 -m pytest tests/test_report_baseline.py -v && python3 -m pytest`
Expected: 全 PASS。既存 `test_report_end_to_end` 等も無変更で締めること

- [ ] **Step 5: Commit**

```bash
git add evals/report_baseline.py tests/test_report_baseline.py
git commit -m "feat: aggregate loop cases and compare against a previous baseline

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 8: test_live.py — 新質問形式の live 確認

**Files:**
- Modify: `tests/test_live.py`

**Interfaces:**
- Consumes: Task 1・2 の decide.py。`AUTARCH_LIVE=1` + `TYPESAFE_API_KEY` でのみ実行(現行流儀)
- Produces: 「Jev が新質問(noul + 4選択肢 choice)を受け付ける」ことの実確認(spec §7・§9 進め方1)。Task 9 の再実行に入る前提条件

- [ ] **Step 1: 失敗テストを書く**

`tests/test_live.py` に追記:

```python
THIN_STATE = {
    "goal": "Pick a task runner for a small build",
    "question": "Which task runner fits this repository?",
    "known_constraints": [],
    "environment": {},
    "evidence": [],
    "alternatives": [
        {
            "id": "shell_script",
            "name": "Shell script",
            "description": "One plain bash script that runs the build steps.",
            "advantages": [],
            "disadvantages": [],
            "assumptions": [],
        },
        {
            "id": "make",
            "name": "Make",
            "description": "Classic makefile-driven build orchestration.",
            "advantages": [],
            "disadvantages": [],
            "assumptions": [],
        },
    ],
    "criteria": [],
}


def test_live_new_questions_accepted(tmp_path, capsys):
    state_file = tmp_path / "thin.json"
    state_file.write_text(json.dumps(THIN_STATE), encoding="utf-8")
    exit_code = decide.main([f"--state-file={state_file}"])
    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    # PROVIDER_UNAVAILABLE here means Jev rejected the new question shapes.
    assert output["decision"] in {
        "SELECT_OPTION",
        "SELECT_OPTION_WITH_CAUTION",
        "ASK_USER",
    }
    assert isinstance(output["evidence_sufficiency"], (int, float))
    if output["rule"] in ("evidence_insufficient", "investigation_exhausted"):
        assert output["blocker_class"] in decide.BLOCKER_CLASSES
        assert isinstance(output["blocker_confidence"], (int, float))
```

- [ ] **Step 2: 通常テスト(オフライン)で skip されることを確認**

Run: `python3 -m pytest tests/test_live.py -v`
Expected: SKIP(環境変数なし)。コードの構文エラーがないことは `python3 -c "import ast; ast.parse(open('tests/test_live.py').read())"` でも確認できる

- [ ] **Step 3: live 実行(オーナーの承認と API キーが必要)**

Run: `AUTARCH_LIVE=1 TYPESAFE_API_KEY=<key> python3 -m pytest tests/test_live.py -v`
Expected: 2件 PASS。`PROVIDER_UNAVAILABLE` で失敗する場合は Jev が新形式を拒否している — 質問の instructions/選択肢の調整が必要。spec §7 に従い、調整してから Task 9 に進む

- [ ] **Step 4: Commit**

```bash
git add tests/test_live.py
git commit -m "test: live check that Jev accepts the new question shapes

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 9: 再実行・比較・記録(実行タスク)

**Files:**
- Create: `evals/results/extension-info-gap-<today>/`(実行記録一式)
- Modify: `STATE.md`(進行状況の更新)

**Interfaces:**
- Consumes: Task 1〜8 のすべて。`TYPESAFE_API_KEY`・`claude` CLI・実行費用(Jev 87呼び出し + agent 5回)
- Produces: baseline との比較を含む実行記録。STATE.md の更新

- [ ] **Step 1: 全テストが緑であることを確認**

Run: `python3 -m pytest`
Expected: 全 PASS(live 系2件は skip)

- [ ] **Step 2: オーナーに実行の承認を得る**

Jev 69回(固定 state 23ケース×3)+ 18回(loop 3ケース×3×2位相)+ full-flow agent 5回(1シナリオ2〜4分)の費用がかかる。承認を得てから先へ進む。day ディレクトリ名の `<today>` は実行日の ISO 日付(例: `2026-10-02`)に置き換える。同日再実行時は `-2` を付ける

- [ ] **Step 3: live 形式確認を先に実行**

Run: `AUTARCH_LIVE=1 TYPESAFE_API_KEY=<key> python3 -m pytest tests/test_live.py -v`
Expected: 2件 PASS(失敗したら Task 8 Step 3 の扱い)

- [ ] **Step 4: 固定 state + loop ケースを実行**

Run:
```bash
python3 evals/run_fixed_state.py \
  --out-dir evals/results/extension-info-gap-<today> \
  --loop-cases-dir evals/cases_loop
```
Expected: exit 0。`fixed_state_runs.jsonl` に 69 + 18 = 87 レコード(通常69 + loop 18)

- [ ] **Step 5: full-flow を実行**

Run:
```bash
python3 evals/run_full_flow.py \
  --agent-model sonnet \
  --out-dir evals/results/extension-info-gap-<today>
```
Expected: exit 0。5シナリオの記録。agent model は baseline と同じ sonnet(比較可能性)

- [ ] **Step 6: 集計と比較レポートを生成**

Run:
```bash
python3 evals/report_baseline.py \
  --baseline-dir evals/results/extension-info-gap-<today> \
  --loop-cases-dir evals/cases_loop \
  --compare-to evals/results/baseline-2026-10-01/baseline.json
```
Expected: exit 0。`baseline.json`(loop_cases・comparison を含む)と `SUMMARY.md` が生成される

- [ ] **Step 7: 結果を確認する**

spec §6.2 の確認項目を SUMMARY.md で見る:

- 3目標指標(Appropriate Ask Rate・evidence_removed pass・Unsafe Auto-selection Rate)が baseline(53.33% / 0/6 / 20.29%)から改善しているか
- 回帰監視: reorder / detail_asymmetry / violating_candidate が 6/6 を維持しているか。completion_rate の低下が info_missing・evidence_removed 系ケースに限定されているか(per_case テーブルで確認)
- loop_pass_rate と、失敗した場合はどの位相で失敗したか
- full-flow の dependency シナリオ: 回収した `autarch-state.json` に `revision` があるか・agent 出力が確認済み事実と未確認事項を並べているか(機械判定外の人間確認)

数値に問題がある場合は STATE.md の方針どおり閾値は変えず、結果と考察を notes.md に残す

- [ ] **Step 8: notes.md を書き、STATE.md を更新**

`evals/results/extension-info-gap-<today>/notes.md`(手書き留保。再生成でも残る):

- full-flow は baseline と同じ制限付きツール構成(外部調査なし)で実行した旨
- 実行日時・agent model・特記事項(再実行の有無など)

`STATE.md`: 「現在地」「改修の経緯」をこの拡張の結果で更新し、ネクストアクションを次の拡張(必須条件の判定)に進める

- [ ] **Step 9: Commit**

```bash
git add evals/results/extension-info-gap-<today> STATE.md
git commit -m "test: record extension run and compare against baseline

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

## Self-Review 結果

- **Spec coverage:** §4.1→Task 1、§4.2→Task 1、§4.3→Task 2、§4.4→Task 2、§4.5→Task 2・4、§4.6→Task 2(redact テスト)、§5→Task 3、§6.1→Task 4・5・6・7、§6.2→Task 6・7・9、§7→Task 1(parse 拒否)・8、§8→各タスクの TDD、§9→Task 9。過不足なし
- **Placeholder scan:** なし(すべてのコードステップに実際のコードが伴う)
- **Type consistency:** `run_with_retry(case, args, state_dir, state=None, phase=None)`(Task 6 定義・Task 6 内で使用)。`loop_phase2_state(case)`(Task 4 定義・Task 6 使用)。`compute(cases, fixed_runs, full_runs, environment, loop_cases=None)`(Task 7)。`comparison_rows(current, previous)`(Task 7 定義・使用)。閾値キー `sufficiency` / `blocker_confidence` は Task 2・6・7 で同一
- **Review Focus:** 5項目すべてに対応タスクのテストを割り当て済み(上記)
