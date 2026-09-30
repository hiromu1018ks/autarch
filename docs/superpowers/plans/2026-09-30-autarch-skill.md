# Autarch Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the `/autarch` decision skill: a `SKILL.md` plus a stdlib-only `decide.py` that evaluates a Generic Decision State with Jev (TypeSafe AI) Noul/Score/Choice questions and returns a deterministic resolution.

**Architecture:** `decide.py` is a single domain-agnostic script. The agent (guided by SKILL.md) captures the question, generates neutral alternatives and criteria, and writes the state JSON; `decide.py` validates it, redacts secrets, calls the Jev API with one mixed-question request, validates the response, applies the deterministic resolution policy (provider error → human-preference gate → choice/score consistency → probability gap → confidence), prints exactly one resolution JSON to stdout, and appends a sanitized decision log.

**Tech Stack:** Python 3.10+ (stdlib only at runtime), pytest (dev/test only), TypeSafe AI System One API (`POST /v1/systemone`).

**Spec:** `docs/superpowers/specs/2026-09-30-autarch-skill-implementation-design.md`

## Global Constraints

- Runtime dependencies: Python 3.10+, **stdlib only** — `decide.py` must not import third-party packages. Development/test dependency: `pytest` only.
- Jev API: `POST {--endpoint}/v1/systemone` (default endpoint `https://api.typesafe.ai`), header `Authorization: Bearer $TYPESAFE_API_KEY`. The API key is read **only** from the environment variable `TYPESAFE_API_KEY`.
- One request, no retry. Timeout via `--timeout` (default 30 seconds). Any transport or response-validation failure → `PROVIDER_UNAVAILABLE`.
- Default thresholds: `--auto-select 0.85`, `--review 0.60`, `--min-gap 0.15`, `--human-preference 0.70`, `--model jev-latest`.
- Exit codes: `0` = a resolution JSON was printed to stdout (all five decision states, including `PROVIDER_UNAVAILABLE` and `INSUFFICIENT_OPTIONS`); `2` = CLI usage error, missing state file, or malformed input JSON (diagnostic on stderr, stdout empty); `1` = unexpected internal error (traceback on stderr, stdout empty).
- stdout carries exactly one machine-readable JSON object and nothing else. stderr carries only the redaction count, diagnostics, and warnings — never a secret value. Secret values never appear in stdout, stderr, the decision log, or exception text. The full state is never logged.
- `decide.py` must contain no coding-specific vocabulary (`package.json`, `sqlite`, `postgres`, `jwt`, `repository`, `database`, `authentication` must not appear in its source).
- `SKILL.md` frontmatter is exactly: `name: autarch`, `description: Resolve a decision by generating alternatives and evaluating them with Jev.`, `disable-model-invocation: true`.
- id rules (alternatives and criteria): match `^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$`, no `__`, unique within their collection. Alternatives: 2–5 items. Criteria: 0–8 items, rubric ≥ 2 levels, weight ≥ 0 (default 1.0).
- Decision log: `~/.autarch/decisions.jsonl`, one JSON line per decision, `sanitized_question` redacted and capped at 500 characters. Log write failure must not affect the resolution.
- All commits end with `Co-Authored-By: Claude Code <noreply@anthropic.com>`.

## Review Focus

The five input classes most likely to bite, each pinned to a test in the owning task:

1. **Booleans where numbers are expected** (`weight: true`, `confidence: true`) — Python's `bool` is an `int` subclass, so a naive `isinstance(x, (int, float))` accepts them. They must be rejected as non-numeric. → Task 3 test `test_weight_boolean_is_rejected`, Task 6 tests use a shared `_is_number` that excludes bool.
2. **CJK / unicode state text** — Japanese question, evidence, and descriptions must survive request building and stdout JSON round-trip. → Task 4 test `test_request_builder_handles_cjk`, Task 9 test `test_main_cjk_end_to_end`.
3. **Empty criteria list `[]`** — must behave exactly like omitted criteria: no score questions, consistency check skipped, `score_summary` null. → Task 7 test `test_resolve_without_criteria_skips_consistency`.
4. **Decision-log write failure** (unwritable `~/.autarch`) — must not corrupt stdout JSON or the exit code; warning to stderr only. → Task 8 test `test_append_log_failure_warns_only`, Task 9 test `test_main_survives_log_failure`.
5. **Choice probabilities that do not sum to 1** — only per-value range (0..1) and full-alternative coverage are validated; no sum check, so a non-summing distribution must be accepted. → Task 6 test `test_parse_answers_accepts_probabilities_that_do_not_sum_to_one`.

---

### Task 1: Scaffolding and module constants

**Files:**
- Create: `skills/autarch/scripts/decide.py`
- Create: `tests/conftest.py`
- Create: `tests/test_decide.py`
- Create: `.gitignore`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: importable module `decide` with constants: `REDACTED`, `SENSITIVE_KEY_TERMS`, `STRING_PATTERNS` (tuple of compiled regex), `PATTERN_EXEMPT_KEYS`, `ID_PATTERN`, `NOUL_INSTRUCTIONS`, `CHOICE_INSTRUCTIONS`, `DEFAULT_MODEL`, `DEFAULT_ENDPOINT`, `DEFAULT_AUTO_SELECT`, `DEFAULT_REVIEW`, `DEFAULT_MIN_GAP`, `DEFAULT_HUMAN_PREFERENCE`, `DEFAULT_TIMEOUT`, `QUESTION_LOG_LIMIT`. `tests/conftest.py` puts `skills/autarch/scripts` on `sys.path` so every test can `import decide`.

- [ ] **Step 1: Write the failing test**

`tests/conftest.py`:

```python
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "skills" / "autarch" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
```

`tests/test_decide.py`:

```python
import decide


def test_module_exposes_constants():
    assert decide.REDACTED == "[REDACTED]"
    assert "password" in decide.SENSITIVE_KEY_TERMS
    assert "credentials" in decide.SENSITIVE_KEY_TERMS
    assert len(decide.STRING_PATTERNS) >= 7
    assert decide.PATTERN_EXEMPT_KEYS == frozenset({"id"})
    assert decide.NOUL_INSTRUCTIONS.startswith("Does resolving this decision require")
    assert decide.CHOICE_INSTRUCTIONS == (
        "Select the option that best satisfies the goal and constraints."
    )
    assert decide.DEFAULT_MODEL == "jev-latest"
    assert decide.DEFAULT_ENDPOINT == "https://api.typesafe.ai"
    assert decide.DEFAULT_AUTO_SELECT == 0.85
    assert decide.DEFAULT_REVIEW == 0.60
    assert decide.DEFAULT_MIN_GAP == 0.15
    assert decide.DEFAULT_HUMAN_PREFERENCE == 0.70
    assert decide.DEFAULT_TIMEOUT == 30
    assert decide.QUESTION_LOG_LIMIT == 500
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_decide.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'decide'`

- [ ] **Step 3: Write minimal implementation**

`skills/autarch/scripts/decide.py`:

```python
#!/usr/bin/env python3
"""Autarch decision engine.

Evaluates a Generic Decision State against Jev (TypeSafe AI System One)
and returns a deterministic resolution. Domain-agnostic by design: this
module knows about decisions, not about any particular field.
"""

import re

REDACTED = "[REDACTED]"

SENSITIVE_KEY_TERMS = (
    "password",
    "passwd",
    "token",
    "access_token",
    "refresh_token",
    "api_key",
    "apikey",
    "secret",
    "private_key",
    "authorization",
    "credential",
    "credentials",
)

STRING_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{8,}"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"Bearer [A-Za-z0-9._~+/=-]{15,}"),
    re.compile(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"
    ),
    re.compile(r"(?i)(password|passwd|token|api_key|secret)\s*[=:]\s*\S+"),
)

PATTERN_EXEMPT_KEYS = frozenset({"id"})

ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

NOUL_INSTRUCTIONS = (
    "Does resolving this decision require the user's personal preference, "
    "business intent, subjective taste, or value judgment?"
)
CHOICE_INSTRUCTIONS = (
    "Select the option that best satisfies the goal and constraints."
)

DEFAULT_MODEL = "jev-latest"
DEFAULT_ENDPOINT = "https://api.typesafe.ai"
DEFAULT_AUTO_SELECT = 0.85
DEFAULT_REVIEW = 0.60
DEFAULT_MIN_GAP = 0.15
DEFAULT_HUMAN_PREFERENCE = 0.70
DEFAULT_TIMEOUT = 30

QUESTION_LOG_LIMIT = 500
```

`.gitignore`:

```text
__pycache__/
.pytest_cache/
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_decide.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add .gitignore skills/autarch/scripts/decide.py tests/conftest.py tests/test_decide.py
git commit -m "feat: scaffold autarch decide module with constants

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 2: Secret redaction and text sanitization

**Files:**
- Modify: `skills/autarch/scripts/decide.py`
- Test: `tests/test_decide.py`

**Interfaces:**
- Consumes: `REDACTED`, `SENSITIVE_KEY_TERMS`, `STRING_PATTERNS`, `PATTERN_EXEMPT_KEYS` from Task 1.
- Produces: `redact(obj) -> tuple[object, int]` (recursively redacted copy plus replacement count) and `sanitize_text(text: str, limit: int = QUESTION_LOG_LIMIT) -> str` (pattern-redacted, truncated). Both are pure; later tasks call `redact(state)` before request building and `sanitize_text(question)` when logging.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_decide.py`:

```python
import copy


def _sample_state():
    return {
        "goal": "g",
        "question": "q",
        "known_constraints": [],
        "environment": {},
        "evidence": [],
        "alternatives": [
            {"id": "option_a", "name": "A", "description": "d"},
            {"id": "option_b", "name": "B", "description": "d"},
        ],
    }


class TestKeyBasedRedaction:
    def test_sensitive_key_value_replaced(self):
        state = _sample_state()
        state["environment"] = {"db_password": "hunter2"}
        redacted, count = decide.redact(state)
        assert redacted["environment"]["db_password"] == "[REDACTED]"
        assert count == 1

    def test_apikey_normalized_key_replaced(self):
        state = _sample_state()
        state["environment"] = {"apiKey": "abc123", "API-KEY": "xyz"}
        redacted, count = decide.redact(state)
        assert redacted["environment"]["apiKey"] == "[REDACTED]"
        assert redacted["environment"]["API-KEY"] == "[REDACTED]"
        assert count == 2

    def test_nested_and_array_values(self):
        state = _sample_state()
        state["environment"] = {
            "services": [
                {"credentials": {"user": "u", "secret": "s"}},
                {"name": "ok"},
            ]
        }
        redacted, count = decide.redact(state)
        services = redacted["environment"]["services"]
        assert services[0]["credentials"] == "[REDACTED]"
        assert services[1]["name"] == "ok"
        assert count == 1

    def test_non_sensitive_keys_untouched(self):
        state = _sample_state()
        redacted, count = decide.redact(state)
        assert redacted == state
        assert count == 0

    def test_input_not_mutated(self):
        state = _sample_state()
        state["environment"] = {"password": "hunter2"}
        snapshot = copy.deepcopy(state)
        decide.redact(state)
        assert state == snapshot


class TestStringPatternRedaction:
    def test_openai_style_key(self):
        state = _sample_state()
        state["evidence"] = ["uses key sk-abcdef1234567890 for the client"]
        redacted, count = decide.redact(state)
        assert "sk-abcdef1234567890" not in redacted["evidence"][0]
        assert "[REDACTED]" in redacted["evidence"][0]
        assert count == 1

    def test_github_and_aws_tokens(self):
        state = _sample_state()
        state["evidence"] = [
            "ghp_" + "a" * 30,
            "github_pat_" + "b" * 30,
            "AKIA" + "1" * 16,
        ]
        redacted, count = decide.redact(state)
        assert all("[REDACTED]" in item for item in redacted["evidence"])
        assert count == 3

    def test_bearer_header(self):
        state = _sample_state()
        state["evidence"] = ["Authorization: Bearer abc123def456ghi789xyz"]
        redacted, count = decide.redact(state)
        assert "abc123def456ghi789xyz" not in redacted["evidence"][0]
        assert count == 1

    def test_private_key_block(self):
        state = _sample_state()
        state["evidence"] = [
            "-----BEGIN RSA PRIVATE KEY-----\nMIIE...\n-----END RSA PRIVATE KEY-----"
        ]
        redacted, count = decide.redact(state)
        assert "MIIE" not in redacted["evidence"][0]
        assert count == 1

    def test_key_value_forms(self):
        state = _sample_state()
        state["evidence"] = ["password=hunter2", "token: abc123", "api_key=xyz789"]
        redacted, count = decide.redact(state)
        assert redacted["evidence"][0] == "[REDACTED]"
        assert redacted["evidence"][1] == "[REDACTED]"
        assert redacted["evidence"][2] == "[REDACTED]"
        assert count == 3

    def test_id_values_exempt_from_string_patterns(self):
        state = _sample_state()
        state["alternatives"][0]["id"] = "sk-abcdefgh1234"
        redacted, count = decide.redact(state)
        assert redacted["alternatives"][0]["id"] == "sk-abcdefgh1234"
        assert count == 0


class TestSanitizeText:
    def test_redacts_and_truncates(self):
        text = "uses sk-abcdef1234567890 and " + "x" * 600
        sanitized = decide.sanitize_text(text)
        assert "sk-abcdef1234567890" not in sanitized
        assert len(sanitized) == decide.QUESTION_LOG_LIMIT

    def test_clean_text_untouched_up_to_limit(self):
        text = "plain question"
        assert decide.sanitize_text(text) == "plain question"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_decide.py -v`
Expected: FAIL with `AttributeError: module 'decide' has no attribute 'redact'` (or `sanitize_text`)

- [ ] **Step 3: Write minimal implementation**

Add to `skills/autarch/scripts/decide.py` (after the constants):

```python
def _normalize_key(key: str) -> str:
    return re.sub(r"[-\s]+", "_", key.strip().lower())


def _is_sensitive_key(key: str) -> bool:
    normalized = _normalize_key(key)
    return any(term in normalized for term in SENSITIVE_KEY_TERMS)


def _redact_string(text: str) -> tuple[str, int]:
    count = 0
    for pattern in STRING_PATTERNS:
        text, replaced = pattern.subn(REDACTED, text)
        count += replaced
    return text, count


def redact(obj):
    """Recursively redact sensitive keys and secret-looking strings.

    Returns (new_object, replacement_count). The input is not mutated.
    Values under keys named "id" skip string-pattern redaction so that
    alternative/criterion ids stay stable for request building and
    response matching.
    """
    count = 0

    def walk(value, key):
        nonlocal count
        if isinstance(value, dict):
            redacted = {}
            for item_key, item_value in value.items():
                if _is_sensitive_key(str(item_key)):
                    redacted[item_key] = REDACTED
                    count += 1
                else:
                    redacted[item_key] = walk(item_value, str(item_key))
            return redacted
        if isinstance(value, list):
            return [walk(item, key) for item in value]
        if isinstance(value, str) and key not in PATTERN_EXEMPT_KEYS:
            text, replaced = _redact_string(value)
            count += replaced
            return text
        return value

    return walk(obj, None), count


def sanitize_text(text: str, limit: int = QUESTION_LOG_LIMIT) -> str:
    """Redact secret patterns from free text and cap its length."""
    redacted, _ = _redact_string(text)
    return redacted[:limit]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_decide.py -v`
Expected: PASS (all tests pass)

- [ ] **Step 5: Commit**

```bash
git add skills/autarch/scripts/decide.py tests/test_decide.py
git commit -m "feat: add recursive secret redaction and text sanitization

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 3: Input validation

**Files:**
- Modify: `skills/autarch/scripts/decide.py`
- Test: `tests/test_decide.py`

**Interfaces:**
- Consumes: `ID_PATTERN` from Task 1.
- Produces: `validate_state(state) -> list[str]` — a list of violation descriptions (empty list = valid). Violation strings contain field names and positions only, never values. Also produces `_is_number(value) -> bool` (True for int/float excluding bool), reused by Task 6.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_decide.py`:

```python
def _valid_state():
    return {
        "goal": "Choose the storage strategy",
        "question": "Which storage option best fits the project?",
        "known_constraints": ["local only"],
        "environment": {"os": "linux"},
        "evidence": ["single user"],
        "alternatives": [
            {
                "id": "option_a",
                "name": "Option A",
                "description": "First candidate.",
                "advantages": ["simple"],
                "disadvantages": ["limited"],
                "assumptions": [],
            },
            {
                "id": "option_b",
                "name": "Option B",
                "description": "Second candidate.",
                "advantages": ["scalable"],
                "disadvantages": ["heavier"],
                "assumptions": [],
            },
        ],
        "criteria": [
            {
                "id": "fit",
                "name": "Requirement fit",
                "weight": 1.0,
                "rubric": ["Poor fit", "Acceptable fit", "Excellent fit"],
            }
        ],
    }


class TestValidateState:
    def test_valid_state_passes(self):
        assert decide.validate_state(_valid_state()) == []

    def test_state_must_be_object(self):
        assert decide.validate_state([1, 2]) == ["state must be a JSON object"]

    def test_goal_and_question_required(self):
        state = _valid_state()
        state["goal"] = ""
        del state["question"]
        errors = decide.validate_state(state)
        assert any(e.startswith("goal") for e in errors)
        assert any(e.startswith("question") for e in errors)

    def test_alternative_count_bounds(self):
        for count, ok in ((0, False), (1, False), (2, True), (5, True), (6, False)):
            state = _valid_state()
            base = {"id": f"option_{i}", "name": "N", "description": "D"}
            state["alternatives"] = [dict(base, id=f"option_{i}") for i in range(count)]
            errors = decide.validate_state(state)
            if ok:
                assert errors == []
            else:
                assert any("2 to 5" in e for e in errors)

    def test_alternatives_must_be_array(self):
        state = _valid_state()
        state["alternatives"] = "nope"
        errors = decide.validate_state(state)
        assert any("alternatives must be an array" in e for e in errors)

    def test_duplicate_option_ids_rejected(self):
        state = _valid_state()
        state["alternatives"][1]["id"] = state["alternatives"][0]["id"]
        errors = decide.validate_state(state)
        assert any("duplicate id" in e for e in errors)

    def test_empty_and_invalid_option_ids_rejected(self):
        state = _valid_state()
        state["alternatives"][0]["id"] = ""
        state["alternatives"][1]["id"] = "bad id with spaces"
        errors = decide.validate_state(state)
        assert any("id must be a non-empty string" in e for e in errors)
        assert any("id does not match" in e for e in errors)

    def test_double_underscore_in_id_rejected(self):
        state = _valid_state()
        state["alternatives"][0]["id"] = "bad__id"
        errors = decide.validate_state(state)
        assert any("must not contain '__'" in e for e in errors)

    def test_name_and_description_required(self):
        state = _valid_state()
        del state["alternatives"][0]["name"]
        state["alternatives"][1]["description"] = ""
        errors = decide.validate_state(state)
        assert any("name must be a non-empty string" in e for e in errors)
        assert any("description must be a non-empty string" in e for e in errors)

    def test_empty_criteria_list_is_valid(self):
        state = _valid_state()
        state["criteria"] = []
        assert decide.validate_state(state) == []

    def test_criteria_omitted_is_valid(self):
        state = _valid_state()
        del state["criteria"]
        assert decide.validate_state(state) == []

    def test_criteria_max_eight(self):
        state = _valid_state()
        state["criteria"] = [
            {"id": f"c{i}", "name": f"C{i}", "rubric": ["low", "high"]}
            for i in range(9)
        ]
        errors = decide.validate_state(state)
        assert any("at most 8" in e for e in errors)

    def test_criterion_schema_errors(self):
        state = _valid_state()
        state["criteria"] = [
            {"id": "c", "name": "C", "weight": -1, "rubric": ["only one level"]}
        ]
        errors = decide.validate_state(state)
        assert any("weight must be a number >= 0" in e for e in errors)
        assert any("at least 2 levels" in e for e in errors)

    def test_weight_boolean_is_rejected(self):
        state = _valid_state()
        state["criteria"][0]["weight"] = True
        errors = decide.validate_state(state)
        assert any("weight must be a number >= 0" in e for e in errors)

    def test_criterion_duplicate_and_invalid_ids(self):
        state = _valid_state()
        state["criteria"] = [
            {"id": "c", "name": "C1", "rubric": ["low", "high"]},
            {"id": "c", "name": "C2", "rubric": ["low", "high"]},
        ]
        errors = decide.validate_state(state)
        assert any("duplicate id" in e for e in errors)

    def test_error_messages_never_contain_values(self):
        state = _valid_state()
        state["alternatives"][0]["id"] = "SECRETLOOKINGID sk-abcdefgh1234"
        errors = decide.validate_state(state)
        assert all("SECRETLOOKINGID" not in e for e in errors)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_decide.py -v`
Expected: FAIL with `AttributeError: module 'decide' has no attribute 'validate_state'`

- [ ] **Step 3: Write minimal implementation**

Add to `skills/autarch/scripts/decide.py`:

```python
def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _validate_id(value, errors: list[str], label: str) -> None:
    if not isinstance(value, str) or not value:
        errors.append(f"{label}: id must be a non-empty string")
        return
    if not ID_PATTERN.match(value):
        errors.append(f"{label}: id does not match the required pattern")
    if "__" in value:
        errors.append(f"{label}: id must not contain '__'")


def validate_state(state) -> list[str]:
    """Validate a decision state. Returns a list of violations (empty = valid)."""
    errors: list[str] = []
    if not isinstance(state, dict):
        return ["state must be a JSON object"]

    for field in ("goal", "question"):
        value = state.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{field} must be a non-empty string")

    alternatives = state.get("alternatives")
    if not isinstance(alternatives, list):
        errors.append("alternatives must be an array")
        alternatives = []
    if not 2 <= len(alternatives) <= 5:
        errors.append(
            f"alternatives must contain 2 to 5 items (found {len(alternatives)})"
        )

    seen_ids: set[str] = set()
    for index, alternative in enumerate(alternatives):
        label = f"alternatives[{index}]"
        if not isinstance(alternative, dict):
            errors.append(f"{label} must be an object")
            continue
        option_id = alternative.get("id")
        _validate_id(option_id, errors, label)
        if isinstance(option_id, str) and option_id:
            if option_id in seen_ids:
                errors.append(f"{label}: duplicate id")
            seen_ids.add(option_id)
        for field in ("name", "description"):
            value = alternative.get(field)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"{label}: {field} must be a non-empty string")

    criteria = state.get("criteria")
    if criteria is not None:
        if not isinstance(criteria, list):
            errors.append("criteria must be an array")
            criteria = []
        if len(criteria) > 8:
            errors.append(
                f"criteria must contain at most 8 items (found {len(criteria)})"
            )
        seen_criteria: set[str] = set()
        for index, criterion in enumerate(criteria):
            label = f"criteria[{index}]"
            if not isinstance(criterion, dict):
                errors.append(f"{label} must be an object")
                continue
            criterion_id = criterion.get("id")
            _validate_id(criterion_id, errors, label)
            if isinstance(criterion_id, str) and criterion_id:
                if criterion_id in seen_criteria:
                    errors.append(f"{label}: duplicate id")
                seen_criteria.add(criterion_id)
            name = criterion.get("name")
            if not isinstance(name, str) or not name.strip():
                errors.append(f"{label}: name must be a non-empty string")
            weight = criterion.get("weight", 1.0)
            if not _is_number(weight) or weight < 0:
                errors.append(f"{label}: weight must be a number >= 0")
            rubric = criterion.get("rubric")
            if not isinstance(rubric, list) or len(rubric) < 2:
                errors.append(
                    f"{label}: rubric must be an array with at least 2 levels"
                )
            elif not all(
                isinstance(level, str) and level.strip() for level in rubric
            ):
                errors.append(f"{label}: rubric levels must be non-empty strings")

    return errors
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_decide.py -v`
Expected: PASS (all tests pass)

- [ ] **Step 5: Commit**

```bash
git add skills/autarch/scripts/decide.py tests/test_decide.py
git commit -m "feat: add decision state input validation

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 4: Jev request builder

**Files:**
- Modify: `skills/autarch/scripts/decide.py`
- Test: `tests/test_decide.py`

**Interfaces:**
- Consumes: `NOUL_INSTRUCTIONS`, `CHOICE_INSTRUCTIONS` from Task 1.
- Produces: `build_request(state: dict, model: str) -> dict` — the exact JSON payload for `POST /v1/systemone`. Takes the **already-redacted** state; it does not redact again. Question names: `requires_human_preference` (noul), `best_option` (choice), `score__<criterion.id>__<alternative.id>` (score).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_decide.py`:

```python
class TestBuildRequest:
    def test_payload_shape(self):
        state = _valid_state()
        payload = decide.build_request(state, "jev-test")
        assert payload["model"] == "jev-test"
        assert payload["state"] is state  # state object passed as-is
        questions = payload["questions"]
        assert set(questions) == {
            "requires_human_preference",
            "best_option",
            "score__fit__option_a",
            "score__fit__option_b",
        }

    def test_noul_question(self):
        payload = decide.build_request(_valid_state(), "m")
        noul = payload["questions"]["requires_human_preference"]
        assert noul == {
            "type": "noul",
            "instructions": decide.NOUL_INSTRUCTIONS,
        }

    def test_choice_question(self):
        payload = decide.build_request(_valid_state(), "m")
        choice = payload["questions"]["best_option"]
        assert choice["type"] == "choice"
        assert choice["instructions"] == decide.CHOICE_INSTRUCTIONS
        assert choice["criteria"] == {
            "option_a": "Option A: First candidate.",
            "option_b": "Option B: Second candidate.",
        }

    def test_score_questions_use_rubric_order(self):
        state = _valid_state()
        state["criteria"][0]["rubric"] = ["worst", "ok", "best"]
        payload = decide.build_request(state, "m")
        score = payload["questions"]["score__fit__option_a"]
        assert score["type"] == "score"
        assert score["instructions"] == (
            "How well does the option 'Option A' satisfy the "
            "'Requirement fit' criterion?"
        )
        assert score["criteria"] == ["worst", "ok", "best"]

    def test_no_criteria_means_no_score_questions(self):
        state = _valid_state()
        state["criteria"] = []
        payload = decide.build_request(state, "m")
        assert set(payload["questions"]) == {
            "requires_human_preference",
            "best_option",
        }

    def test_matrix_covers_all_criteria_times_alternatives(self):
        state = _valid_state()
        state["criteria"] = [
            {"id": f"c{i}", "name": f"C{i}", "rubric": ["low", "high"]}
            for i in range(3)
        ]
        payload = decide.build_request(state, "m")
        score_names = {
            f"score__c{i}__option_{o}" for i in range(3) for o in ("a", "b")
        }
        assert score_names <= set(payload["questions"])
        assert len(payload["questions"]) == 2 + 6

    def test_request_builder_handles_cjk(self):
        state = _valid_state()
        state["question"] = "認証方式はどちらが適切か"
        state["alternatives"][0]["name"] = "案A"
        state["alternatives"][0]["description"] = "同一オリジンのWebアプリ向け。"
        payload = decide.build_request(state, "m")
        assert payload["questions"]["best_option"]["criteria"]["option_a"] == (
            "案A: 同一オリジンのWebアプリ向け。"
        )
        # The payload must serialize to JSON without errors.
        import json as json_module

        json_module.dumps(payload, ensure_ascii=False)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_decide.py -v`
Expected: FAIL with `AttributeError: module 'decide' has no attribute 'build_request'`

- [ ] **Step 3: Write minimal implementation**

Add to `skills/autarch/scripts/decide.py`:

```python
def build_request(state: dict, model: str) -> dict:
    """Build the SystemOne request payload from a redacted state."""
    alternatives = state.get("alternatives", [])
    criteria = state.get("criteria") or []
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
    }
    for criterion in criteria:
        for alternative in alternatives:
            questions[f"score__{criterion['id']}__{alternative['id']}"] = {
                "type": "score",
                "instructions": (
                    f"How well does the option '{alternative['name']}' satisfy "
                    f"the '{criterion['name']}' criterion?"
                ),
                "criteria": list(criterion["rubric"]),
            }
    return {"model": model, "state": state, "questions": questions}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_decide.py -v`
Expected: PASS (all tests pass)

- [ ] **Step 5: Commit**

```bash
git add skills/autarch/scripts/decide.py tests/test_decide.py
git commit -m "feat: build mixed-question Jev SystemOne request payload

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 5: HTTP transport

**Files:**
- Modify: `skills/autarch/scripts/decide.py`
- Test: `tests/test_decide.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `class ProviderError(Exception)` and `send_request(payload: dict, endpoint: str, timeout: float) -> tuple[int, bytes]`. `send_request` POSTs `{endpoint}/v1/systemone` with `Authorization: Bearer $TYPESAFE_API_KEY` (read from the environment at call time) and returns `(http_status, body)`. `urllib.error.HTTPError` is converted to a returned `(error.code, b"")`; other transport failures (`URLError`, `TimeoutError`, any `OSError`) propagate to the caller. Task 6 and Task 9 build on both.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_decide.py`:

```python
import urllib.error


class FakeResponse:
    def __init__(self, body=b"{}", status=200):
        self._body = body
        self.status = status

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


class TestSendRequest:
    def _payload(self):
        return {"model": "m", "state": {}, "questions": {}}

    def test_posts_to_systemone_with_bearer(self, monkeypatch):
        captured = {}

        def fake_urlopen(request, timeout=None):
            captured["url"] = request.full_url
            captured["auth"] = request.get_header("Authorization")
            captured["content_type"] = request.get_header("Content-type")
            captured["timeout"] = timeout
            captured["body"] = request.data
            return FakeResponse(b'{"ok": true}', 200)

        monkeypatch.setattr(decide.urllib.request, "urlopen", fake_urlopen)
        monkeypatch.setenv("TYPESAFE_API_KEY", "test-key-123")
        status, body = decide.send_request(self._payload(), "https://api.example", 12.5)

        assert status == 200
        assert body == b'{"ok": true}'
        assert captured["url"] == "https://api.example/v1/systemone"
        assert captured["auth"] == "Bearer test-key-123"
        assert captured["content_type"] == "application/json"
        assert captured["timeout"] == 12.5
        import json as json_module

        assert json_module.loads(captured["body"]) == self._payload()

    def test_trailing_slash_endpoint_normalized(self, monkeypatch):
        captured = {}

        def fake_urlopen(request, timeout=None):
            captured["url"] = request.full_url
            return FakeResponse(b"{}", 200)

        monkeypatch.setattr(decide.urllib.request, "urlopen", fake_urlopen)
        monkeypatch.setenv("TYPESAFE_API_KEY", "k")
        decide.send_request(self._payload(), "https://api.example/", 5)
        assert captured["url"] == "https://api.example/v1/systemone"

    def test_http_error_returns_status(self, monkeypatch):
        def fake_urlopen(request, timeout=None):
            raise urllib.error.HTTPError(
                request.full_url, 429, "Too Many Requests", None, None
            )

        monkeypatch.setattr(decide.urllib.request, "urlopen", fake_urlopen)
        monkeypatch.setenv("TYPESAFE_API_KEY", "k")
        status, body = decide.send_request(self._payload(), "https://api.example", 5)
        assert status == 429
        assert body == b""

    def test_timeout_propagates_as_oserror(self, monkeypatch):
        def fake_urlopen(request, timeout=None):
            raise TimeoutError("timed out")

        monkeypatch.setattr(decide.urllib.request, "urlopen", fake_urlopen)
        monkeypatch.setenv("TYPESAFE_API_KEY", "k")
        with pytest.raises(OSError):
            decide.send_request(self._payload(), "https://api.example", 5)

    def test_urlerror_propagates(self, monkeypatch):
        def fake_urlopen(request, timeout=None):
            raise urllib.error.URLError("connection refused")

        monkeypatch.setattr(decide.urllib.request, "urlopen", fake_urlopen)
        monkeypatch.setenv("TYPESAFE_API_KEY", "k")
        with pytest.raises(OSError):
            decide.send_request(self._payload(), "https://api.example", 5)


def test_provider_error_is_exception():
    assert issubclass(decide.ProviderError, Exception)
```

Note: these tests reference `pytest`, so add the import at the top of `tests/test_decide.py` in this step:

```python
import pytest
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_decide.py -v`
Expected: FAIL with `AttributeError: module 'decide' has no attribute 'urllib'` / `'send_request'` / `'ProviderError'`

- [ ] **Step 3: Write minimal implementation**

Add to the imports at the top of `skills/autarch/scripts/decide.py` (keep alphabetical order):

```python
import json
import os
import urllib.error
import urllib.request
```

(`re` stays from Task 1; `argparse`, `sys`, `time`, `datetime`, `pathlib` arrive in later tasks.)

Add after the constants:

```python
class ProviderError(Exception):
    """Raised when the evaluation provider cannot deliver a usable response."""


def send_request(payload: dict, endpoint: str, timeout: float) -> tuple[int, bytes]:
    """POST the payload to the SystemOne endpoint.

    Returns (http_status, body). HTTP error statuses come back as
    (error.code, b""); transport failures raise OSError subclasses.
    """
    url = endpoint.rstrip("/") + "/v1/systemone"
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {os.environ.get('TYPESAFE_API_KEY', '')}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, b""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_decide.py -v`
Expected: PASS (all tests pass)

- [ ] **Step 5: Commit**

```bash
git add skills/autarch/scripts/decide.py tests/test_decide.py
git commit -m "feat: add SystemOne HTTP transport with provider error type

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 6: Response parsing and validation

**Files:**
- Modify: `skills/autarch/scripts/decide.py`
- Test: `tests/test_decide.py`

**Interfaces:**
- Consumes: `ProviderError`, `_is_number` from earlier tasks.
- Produces: `parse_answers(body: bytes, state: dict) -> dict`. Returns `{"human_preference": float, "choice": str, "confidence": float, "probabilities": dict[str, float], "scores": dict[str, dict[str, float]]}` where `scores[criterion_id][alternative_id]` is the expected score (raw, not normalized). Raises `ProviderError` on every violation of spec §6 (malformed JSON, missing answers object, missing/mistyped answers, out-of-range values, unknown choice, incomplete probability coverage, choice ≠ max probability, score out of rubric range, rubric-index mismatch). `state` here is the **redacted** state (ids are stable through redaction).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_decide.py` (below the existing helpers):

```python
def make_answers(state, noul=0.1, choice=None, confidence=0.9, probabilities=None):
    """Build a consistent answers dict whose winner is `choice`."""
    choice = choice or state["alternatives"][0]["id"]
    if probabilities is None:
        losers = [a["id"] for a in state["alternatives"] if a["id"] != choice]
        share = 0.15 / len(losers) if losers else 0.0
        probabilities = {a["id"]: (0.85 if a["id"] == choice else share)
                         for a in state["alternatives"]}
    answers = {
        "requires_human_preference": {"type": "noul", "noul": noul},
        "best_option": {
            "type": "choice",
            "choice": choice,
            "confidence": confidence,
            "probabilities": probabilities,
        },
    }
    for criterion in state.get("criteria") or []:
        levels = len(criterion["rubric"])
        for alternative in state["alternatives"]:
            winner = alternative["id"] == choice
            top_level = levels - 1 if winner else 1
            answers[f"score__{criterion['id']}__{alternative['id']}"] = {
                "type": "score",
                "score": float(top_level),
                "confidence": 0.9,
                "probabilities": {
                    str(i): (1.0 if i == top_level else 0.0) for i in range(levels)
                },
            }
    return answers


def answers_body(answers):
    import json as json_module

    return json_module.dumps({"model": "jev-test", "answers": answers}).encode()


class TestParseAnswers:
    def test_happy_path(self):
        state = _valid_state()
        answers = make_answers(state, noul=0.1, choice="option_a", confidence=0.94)
        parsed = decide.parse_answers(answers_body(answers), state)
        assert parsed["human_preference"] == 0.1
        assert parsed["choice"] == "option_a"
        assert parsed["confidence"] == 0.94
        assert parsed["probabilities"]["option_a"] == 0.85
        assert parsed["probabilities"]["option_b"] == 0.15
        assert parsed["scores"]["fit"]["option_a"] == 2.0
        assert parsed["scores"]["fit"]["option_b"] == 1.0

    def test_malformed_json_raises(self):
        with pytest.raises(decide.ProviderError):
            decide.parse_answers(b"not json at all", _valid_state())

    def test_missing_answers_object_raises(self):
        with pytest.raises(decide.ProviderError):
            decide.parse_answers(b'{"model": "m"}', _valid_state())

    def test_missing_noul_answer_raises(self):
        state = _valid_state()
        answers = make_answers(state)
        del answers["requires_human_preference"]
        with pytest.raises(decide.ProviderError):
            decide.parse_answers(answers_body(answers), state)

    def test_wrong_answer_type_raises(self):
        state = _valid_state()
        answers = make_answers(state)
        answers["best_option"]["type"] = "score"
        with pytest.raises(decide.ProviderError):
            decide.parse_answers(answers_body(answers), state)

    def test_noul_out_of_range_raises(self):
        state = _valid_state()
        for bad in (-0.01, 1.01, True):
            answers = make_answers(state, noul=bad)
            with pytest.raises(decide.ProviderError):
                decide.parse_answers(answers_body(answers), state)

    def test_unknown_choice_raises(self):
        state = _valid_state()
        answers = make_answers(state, choice="option_a")
        answers["best_option"]["choice"] = "option_z"
        with pytest.raises(decide.ProviderError):
            decide.parse_answers(answers_body(answers), state)

    def test_confidence_out_of_range_raises(self):
        state = _valid_state()
        for bad in (-0.1, 1.1):
            answers = make_answers(state, confidence=bad)
            with pytest.raises(decide.ProviderError):
                decide.parse_answers(answers_body(answers), state)

    def test_probability_out_of_range_raises(self):
        state = _valid_state()
        answers = make_answers(state, choice="option_a")
        answers["best_option"]["probabilities"]["option_b"] = 1.5
        with pytest.raises(decide.ProviderError):
            decide.parse_answers(answers_body(answers), state)

    def test_missing_probability_key_raises(self):
        state = _valid_state()
        answers = make_answers(state, choice="option_a")
        del answers["best_option"]["probabilities"]["option_b"]
        with pytest.raises(decide.ProviderError):
            decide.parse_answers(answers_body(answers), state)

    def test_choice_not_highest_probability_raises(self):
        state = _valid_state()
        answers = make_answers(state, choice="option_a")
        answers["best_option"]["probabilities"] = {
            "option_a": 0.3,
            "option_b": 0.7,
        }
        with pytest.raises(decide.ProviderError):
            decide.parse_answers(answers_body(answers), state)

    def test_missing_score_answer_raises(self):
        state = _valid_state()
        answers = make_answers(state)
        del answers["score__fit__option_b"]
        with pytest.raises(decide.ProviderError):
            decide.parse_answers(answers_body(answers), state)

    def test_score_out_of_rubric_range_raises(self):
        state = _valid_state()
        answers = make_answers(state)
        answers["score__fit__option_a"]["score"] = 3.0  # rubric has 3 levels (0..2)
        with pytest.raises(decide.ProviderError):
            decide.parse_answers(answers_body(answers), state)

    def test_score_probability_index_mismatch_raises(self):
        state = _valid_state()
        answers = make_answers(state)
        answers["score__fit__option_a"]["probabilities"] = {
            "0": 0.5,
            "1": 0.5,
            "2": 0.0,
            "3": 0.0,
        }
        with pytest.raises(decide.ProviderError):
            decide.parse_answers(answers_body(answers), state)

    def test_score_confidence_out_of_range_raises(self):
        state = _valid_state()
        answers = make_answers(state)
        answers["score__fit__option_a"]["confidence"] = 1.2
        with pytest.raises(decide.ProviderError):
            decide.parse_answers(answers_body(answers), state)

    def test_parse_answers_accepts_probabilities_that_do_not_sum_to_one(self):
        state = _valid_state()
        answers = make_answers(
            state,
            choice="option_a",
            probabilities={"option_a": 0.5, "option_b": 0.1},
        )
        parsed = decide.parse_answers(answers_body(answers), state)
        assert parsed["probabilities"] == {"option_a": 0.5, "option_b": 0.1}

    def test_boolean_confidence_rejected(self):
        state = _valid_state()
        answers = make_answers(state, confidence=True)
        with pytest.raises(decide.ProviderError):
            decide.parse_answers(answers_body(answers), state)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_decide.py -v`
Expected: FAIL with `AttributeError: module 'decide' has no attribute 'parse_answers'`

- [ ] **Step 3: Write minimal implementation**

Add to `skills/autarch/scripts/decide.py`:

```python
def _require_number(value, minimum: float, maximum: float, detail: str) -> float:
    if not _is_number(value) or not minimum <= value <= maximum:
        raise ProviderError(f"{detail} is out of range [{minimum:g}, {maximum:g}]")
    return float(value)


def parse_answers(body: bytes, state: dict) -> dict:
    """Parse and validate a SystemOne response against the redacted state."""
    try:
        document = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProviderError(
            f"response is not valid JSON ({type(error).__name__})"
        ) from None
    answers = document.get("answers") if isinstance(document, dict) else None
    if not isinstance(answers, dict):
        raise ProviderError("response has no answers object")

    alternative_ids = [alternative["id"] for alternative in state["alternatives"]]
    criteria = state.get("criteria") or []

    noul_answer = answers.get("requires_human_preference")
    if not isinstance(noul_answer, dict) or noul_answer.get("type") != "noul":
        raise ProviderError(
            "requires_human_preference answer is missing or has wrong type"
        )
    human_preference = _require_number(
        noul_answer.get("noul"), 0.0, 1.0, "requires_human_preference.noul"
    )

    choice_answer = answers.get("best_option")
    if not isinstance(choice_answer, dict) or choice_answer.get("type") != "choice":
        raise ProviderError("best_option answer is missing or has wrong type")
    selected = choice_answer.get("choice")
    if selected not in alternative_ids:
        raise ProviderError("best_option.choice is not one of the alternative ids")
    confidence = _require_number(
        choice_answer.get("confidence"), 0.0, 1.0, "best_option.confidence"
    )
    raw_probabilities = choice_answer.get("probabilities")
    if (
        not isinstance(raw_probabilities, dict)
        or set(raw_probabilities) != set(alternative_ids)
    ):
        raise ProviderError(
            "best_option.probabilities must cover every alternative id"
        )
    probabilities = {
        alternative_id: _require_number(
            value, 0.0, 1.0, f"best_option.probabilities[{alternative_id}]"
        )
        for alternative_id, value in raw_probabilities.items()
    }
    if probabilities[selected] != max(probabilities.values()):
        raise ProviderError(
            "best_option.choice does not match the highest probability"
        )

    scores: dict[str, dict[str, float]] = {}
    for criterion in criteria:
        for alternative in state["alternatives"]:
            name = f"score__{criterion['id']}__{alternative['id']}"
            answer = answers.get(name)
            if not isinstance(answer, dict) or answer.get("type") != "score":
                raise ProviderError(f"{name} answer is missing or has wrong type")
            max_level = len(criterion["rubric"]) - 1
            score = _require_number(answer.get("score"), 0.0, float(max_level),
                                    f"{name}.score")
            _require_number(answer.get("confidence"), 0.0, 1.0, f"{name}.confidence")
            level_probabilities = answer.get("probabilities")
            expected_keys = {str(index) for index in range(len(criterion["rubric"]))}
            if (
                not isinstance(level_probabilities, dict)
                or set(level_probabilities) != expected_keys
            ):
                raise ProviderError(
                    f"{name}.probabilities must cover rubric levels exactly"
                )
            scores.setdefault(criterion["id"], {})[alternative["id"]] = score

    return {
        "human_preference": human_preference,
        "choice": selected,
        "confidence": confidence,
        "probabilities": probabilities,
        "scores": scores,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_decide.py -v`
Expected: PASS (all tests pass)

- [ ] **Step 5: Commit**

```bash
git add skills/autarch/scripts/decide.py tests/test_decide.py
git commit -m "feat: parse and strictly validate SystemOne responses

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 7: Score summary and resolution engine

**Files:**
- Modify: `skills/autarch/scripts/decide.py`
- Test: `tests/test_decide.py`

**Interfaces:**
- Consumes: nothing new (pure functions over state + parsed output).
- Produces: `compute_score_summary(state: dict, parsed: dict) -> dict` mapping `option_id -> {criterion_id: normalized_expected, "composite": float}` (empty dict when state has no criteria); and `resolve(state: dict, parsed: dict, thresholds: dict) -> dict` where `thresholds = {"auto_select": float, "review": float, "min_gap": float, "human_preference": float}`, returning a resolution dict with keys `decision, rule, selected_option, confidence, probability, probabilities, human_preference_probability, score_summary, reason` (no `detail`/`model` — Task 9 adds those).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_decide.py`:

```python
def _thresholds():
    return {
        "auto_select": 0.85,
        "review": 0.60,
        "min_gap": 0.15,
        "human_preference": 0.70,
    }


class TestComputeScoreSummary:
    def test_normalized_composite(self):
        state = _valid_state()  # rubric: 3 levels -> divide by 2
        parsed_scores = {"fit": {"option_a": 2.0, "option_b": 0.0}}
        parsed = {"scores": parsed_scores}
        summary = decide.compute_score_summary(state, parsed)
        assert summary["option_a"] == {"fit": 1.0, "composite": 1.0}
        assert summary["option_b"] == {"fit": 0.0, "composite": 0.0}

    def test_weighted_composite(self):
        state = _valid_state()
        state["criteria"] = [
            {"id": "c1", "name": "C1", "weight": 3.0, "rubric": ["low", "high"]},
            {"id": "c2", "name": "C2", "weight": 1.0, "rubric": ["low", "high"]},
        ]
        parsed = {"scores": {"c1": {"option_a": 1.0, "option_b": 0.0},
                              "c2": {"option_a": 0.0, "option_b": 1.0}}}
        summary = decide.compute_score_summary(state, parsed)
        assert summary["option_a"]["composite"] == 0.75
        assert summary["option_b"]["composite"] == 0.25

    def test_all_zero_weights_fall_back_to_equal(self):
        state = _valid_state()
        state["criteria"] = [
            {"id": "c1", "name": "C1", "weight": 0, "rubric": ["low", "high"]},
            {"id": "c2", "name": "C2", "weight": 0, "rubric": ["low", "high"]},
        ]
        parsed = {"scores": {"c1": {"option_a": 1.0, "option_b": 0.0},
                              "c2": {"option_a": 0.0, "option_b": 1.0}}}
        summary = decide.compute_score_summary(state, parsed)
        assert summary["option_a"]["composite"] == 0.5
        assert summary["option_b"]["composite"] == 0.5

    def test_no_criteria_returns_empty(self):
        state = _valid_state()
        state["criteria"] = []
        assert decide.compute_score_summary(state, {"scores": {}}) == {}


class TestResolve:
    def _run(self, state=None, **answer_kwargs):
        state = state or _valid_state()
        answers = make_answers(state, **answer_kwargs)
        parsed = decide.parse_answers(answers_body(answers), state)
        return decide.resolve(state, parsed, _thresholds())

    def test_select_option_when_confident(self):
        resolution = self._run(choice="option_a", confidence=0.94)
        assert resolution["decision"] == "SELECT_OPTION"
        assert resolution["rule"] == "confidence"
        assert resolution["selected_option"] == "option_a"
        assert resolution["probability"] == 0.85
        assert resolution["confidence"] == 0.94
        assert resolution["score_summary"] is not None

    def test_caution_band(self):
        resolution = self._run(confidence=0.70)
        assert resolution["decision"] == "SELECT_OPTION_WITH_CAUTION"
        assert resolution["rule"] == "confidence"
        assert resolution["selected_option"] == "option_a"

    def test_ask_user_on_low_confidence(self):
        resolution = self._run(confidence=0.40)
        assert resolution["decision"] == "ASK_USER"
        assert resolution["rule"] == "low_confidence"
        assert resolution["selected_option"] is None

    def test_ask_user_on_probability_gap(self):
        resolution = self._run(
            probabilities={"option_a": 0.55, "option_b": 0.45}
        )
        assert resolution["decision"] == "ASK_USER"
        assert resolution["rule"] == "probability_gap"

    def test_ask_user_on_human_preference(self):
        resolution = self._run(noul=0.9, confidence=0.99)
        assert resolution["decision"] == "ASK_USER"
        assert resolution["rule"] == "human_preference"
        assert resolution["human_preference_probability"] == 0.9

    def test_ask_user_on_choice_score_disagreement(self):
        state = _valid_state()
        answers = make_answers(state, choice="option_a", confidence=0.9)
        # Make option_b the score winner: top rubric level for b only.
        answers["score__fit__option_a"]["score"] = 0.0
        answers["score__fit__option_a"]["probabilities"] = {
            "0": 1.0, "1": 0.0, "2": 0.0
        }
        parsed = decide.parse_answers(answers_body(answers), state)
        resolution = decide.resolve(state, parsed, _thresholds())
        assert resolution["decision"] == "ASK_USER"
        assert resolution["rule"] == "choice_score_disagreement"

    def test_human_preference_beats_high_confidence_choice(self):
        state = _valid_state()
        answers = make_answers(state, noul=0.95, choice="option_a", confidence=0.95)
        parsed = decide.parse_answers(answers_body(answers), state)
        resolution = decide.resolve(state, parsed, _thresholds())
        assert resolution["decision"] == "ASK_USER"
        assert resolution["rule"] == "human_preference"

    def test_resolve_without_criteria_skips_consistency(self):
        state = _valid_state()
        state["criteria"] = []
        answers = make_answers(state, choice="option_a", confidence=0.9)
        parsed = decide.parse_answers(answers_body(answers), state)
        resolution = decide.resolve(state, parsed, _thresholds())
        assert resolution["decision"] == "SELECT_OPTION"
        assert resolution["score_summary"] is None

    def test_composite_tie_is_disagreement(self):
        state = _valid_state()
        state["criteria"] = [
            {"id": "fit", "name": "Fit", "rubric": ["low", "high"]}
        ]
        answers = make_answers(state, choice="option_a", confidence=0.9)
        # Both options score identically -> no unique score winner.
        for option in ("option_a", "option_b"):
            answers["score__fit__" + option]["score"] = 1.0
            answers["score__fit__" + option]["probabilities"] = {
                "0": 0.0, "1": 1.0
            }
        parsed = decide.parse_answers(answers_body(answers), state)
        resolution = decide.resolve(state, parsed, _thresholds())
        assert resolution["decision"] == "ASK_USER"
        assert resolution["rule"] == "choice_score_disagreement"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_decide.py -v`
Expected: FAIL with `AttributeError: module 'decide' has no attribute 'compute_score_summary'`

- [ ] **Step 3: Write minimal implementation**

Add to `skills/autarch/scripts/decide.py`:

```python
def compute_score_summary(state: dict, parsed: dict) -> dict:
    """Compute per-option normalized criterion scores and weighted composite."""
    criteria = state.get("criteria") or []
    if not criteria:
        return {}
    weights = {
        criterion["id"]: criterion.get("weight", 1.0) for criterion in criteria
    }
    total_weight = sum(weights.values())
    if total_weight <= 0:
        weights = {criterion_id: 1.0 for criterion_id in weights}
        total_weight = float(len(weights))
    summary: dict[str, dict] = {}
    for alternative in state["alternatives"]:
        option_id = alternative["id"]
        entry: dict[str, float] = {}
        composite = 0.0
        for criterion in criteria:
            criterion_id = criterion["id"]
            expected = parsed["scores"][criterion_id][option_id]
            normalized = expected / (len(criterion["rubric"]) - 1)
            entry[criterion_id] = round(normalized, 4)
            composite += weights[criterion_id] * normalized
        entry["composite"] = round(composite / total_weight, 4)
        summary[option_id] = entry
    return summary


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
        "reason": "",
    }

    if human_preference >= thresholds["human_preference"]:
        resolution["decision"] = "ASK_USER"
        resolution["rule"] = "human_preference"
        resolution["reason"] = (
            "Jev indicates this decision depends on the user's personal "
            "preference or intent; it must not be auto-selected."
        )
        return resolution

    choice_winner = parsed["choice"]

    if has_criteria:
        composites = {
            option_id: entry["composite"]
            for option_id, entry in score_summary.items()
        }
        best = max(composites.values())
        score_winners = [
            option_id for option_id, value in composites.items() if value == best
        ]
        if len(score_winners) != 1 or score_winners[0] != choice_winner:
            resolution["decision"] = "ASK_USER"
            resolution["rule"] = "choice_score_disagreement"
            resolution["reason"] = (
                "The Choice winner and the weighted Score winner differ; "
                "returning the decision to the user."
            )
            return resolution

    ranked = sorted(probabilities.values(), reverse=True)
    gap = ranked[0] - ranked[1]
    if gap < thresholds["min_gap"]:
        resolution["decision"] = "ASK_USER"
        resolution["rule"] = "probability_gap"
        resolution["reason"] = (
            f"Top two options are close (probability gap {gap:.2f} "
            f"< {thresholds['min_gap']:g}); returning the decision to the user."
        )
        return resolution

    resolution["selected_option"] = choice_winner
    resolution["probability"] = probabilities[choice_winner]
    agreement = (
        f"Choice and Score agree on '{choice_winner}'"
        if has_criteria
        else f"Jev selected '{choice_winner}'"
    )
    if confidence >= thresholds["auto_select"]:
        resolution["decision"] = "SELECT_OPTION"
        resolution["rule"] = "confidence"
        resolution["reason"] = (
            f"{agreement} with confidence {confidence:.2f}."
        )
    elif confidence >= thresholds["review"]:
        resolution["decision"] = "SELECT_OPTION_WITH_CAUTION"
        resolution["rule"] = "confidence"
        resolution["reason"] = (
            f"{agreement}, but confidence {confidence:.2f} is below the "
            "auto-select threshold."
        )
    else:
        resolution["decision"] = "ASK_USER"
        resolution["rule"] = "low_confidence"
        resolution["reason"] = (
            f"Confidence {confidence:.2f} is below the review threshold; "
            "returning the decision to the user."
        )
    return resolution
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_decide.py -v`
Expected: PASS (all tests pass)

- [ ] **Step 5: Commit**

```bash
git add skills/autarch/scripts/decide.py tests/test_decide.py
git commit -m "feat: add weighted score summary and deterministic resolution engine

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 8: Decision logging

**Files:**
- Modify: `skills/autarch/scripts/decide.py`
- Test: `tests/test_decide.py`

**Interfaces:**
- Consumes: `sanitize_text` from Task 2.
- Produces: `default_log_path() -> Path` (`~/.autarch/decisions.jsonl`, resolved at call time so tests can monkeypatch `Path.home`); `append_log(record: dict, log_path: Path | None = None) -> None` (appends one JSON line, creates the directory, prints a stderr warning on `OSError` and never raises); `build_log_record(state: dict, output: dict, latency_ms: int | None) -> dict` with exactly the keys `timestamp, sanitized_question, option_ids, criteria_ids, score_summary, choice_probabilities, choice_confidence, human_preference_probability, resolution, model, latency_ms`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_decide.py`:

```python
class TestLogging:
    def test_default_log_path_under_home(self, tmp_path, monkeypatch):
        import pathlib

        monkeypatch.setattr(pathlib.Path, "home", classmethod(lambda cls: tmp_path))
        assert decide.default_log_path() == tmp_path / ".autarch" / "decisions.jsonl"

    def test_append_log_creates_file_and_appends(self, tmp_path):
        log_path = tmp_path / "nested" / "decisions.jsonl"
        decide.append_log({"resolution": "SELECT_OPTION"}, log_path)
        decide.append_log({"resolution": "ASK_USER"}, log_path)
        lines = log_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2
        import json as json_module

        assert json_module.loads(lines[0])["resolution"] == "SELECT_OPTION"
        assert json_module.loads(lines[1])["resolution"] == "ASK_USER"

    def test_append_log_failure_warns_only(self, tmp_path, capsys):
        # A directory path cannot be opened for append -> OSError.
        decide.append_log({"resolution": "SELECT_OPTION"}, tmp_path)
        captured = capsys.readouterr()
        assert "warning" in captured.err
        assert captured.out == ""

    def test_build_log_record_shape_and_sanitization(self):
        state = _valid_state()
        state["question"] = "which one? password=hunter2 " + "y" * 600
        output = {
            "decision": "SELECT_OPTION",
            "probabilities": {"option_a": 0.85},
            "confidence": 0.9,
            "human_preference_probability": 0.1,
            "score_summary": {"option_a": {"fit": 1.0, "composite": 1.0}},
            "model": "jev-test",
        }
        record = decide.build_log_record(state, output, 812)
        assert set(record) == {
            "timestamp",
            "sanitized_question",
            "option_ids",
            "criteria_ids",
            "score_summary",
            "choice_probabilities",
            "choice_confidence",
            "human_preference_probability",
            "resolution",
            "model",
            "latency_ms",
        }
        # "which one? " (11 chars) + "[REDACTED]" (10) + " " (1) = 22 chars,
        # leaving 478 of the 600 "y" characters within the 500-char cap.
        assert record["sanitized_question"] == "which one? [REDACTED] " + "y" * 478
        assert "hunter2" not in record["sanitized_question"]
        assert record["option_ids"] == ["option_a", "option_b"]
        assert record["criteria_ids"] == ["fit"]
        assert record["latency_ms"] == 812
        assert record["resolution"] == "SELECT_OPTION"
        assert isinstance(record["timestamp"], str)

    def test_build_log_record_tolerates_partial_state(self):
        record = decide.build_log_record({}, {"decision": "PROVIDER_UNAVAILABLE"}, None)
        assert record["option_ids"] == []
        assert record["criteria_ids"] == []
        assert record["latency_ms"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_decide.py -v`
Expected: FAIL with `AttributeError: module 'decide' has no attribute 'append_log'`

- [ ] **Step 3: Write minimal implementation**

Extend the imports of `skills/autarch/scripts/decide.py`:

```python
import sys
from datetime import datetime, timezone
from pathlib import Path
```

Add:

```python
def default_log_path() -> Path:
    return Path.home() / ".autarch" / "decisions.jsonl"


def append_log(record: dict, log_path: Path | None = None) -> None:
    """Append one decision record as a JSON line. Never raises."""
    path = log_path or default_log_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as error:
        print(
            f"warning: could not write decision log: {type(error).__name__}",
            file=sys.stderr,
        )


def build_log_record(state: dict, output: dict, latency_ms: int | None) -> dict:
    question = state.get("question", "") if isinstance(state, dict) else ""
    alternatives = state.get("alternatives") if isinstance(state, dict) else None
    criteria = state.get("criteria") if isinstance(state, dict) else None
    return {
        "timestamp": datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "sanitized_question": sanitize_text(str(question)),
        "option_ids": [
            item.get("id")
            for item in (alternatives or [])
            if isinstance(item, dict)
        ],
        "criteria_ids": [
            item.get("id") for item in (criteria or []) if isinstance(item, dict)
        ],
        "score_summary": output.get("score_summary"),
        "choice_probabilities": output.get("probabilities"),
        "choice_confidence": output.get("confidence"),
        "human_preference_probability": output.get("human_preference_probability"),
        "resolution": output.get("decision"),
        "model": output.get("model"),
        "latency_ms": latency_ms,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_decide.py -v`
Expected: PASS (all tests pass)

- [ ] **Step 5: Commit**

```bash
git add skills/autarch/scripts/decide.py tests/test_decide.py
git commit -m "feat: add sanitized JSONL decision logging

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 9: CLI entry point and end-to-end output contract

**Files:**
- Modify: `skills/autarch/scripts/decide.py`
- Test: `tests/test_decide.py`

**Interfaces:**
- Consumes: every function from Tasks 2–8 (`redact`, `validate_state`, `build_request`, `send_request`, `ProviderError`, `parse_answers`, `resolve`, `append_log`, `build_log_record`) and the Task 1 constants.
- Produces: `main(argv: list[str] | None = None) -> int`, `_empty_resolution(decision: str, rule: str) -> dict`, `_resolution_output(resolution: dict, model: str, detail: str | None = None) -> dict`, and the `if __name__ == "__main__":` guard. Output key order: `decision, rule, selected_option, confidence, probability, probabilities, human_preference_probability, score_summary, reason, detail, model`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_decide.py` (also add these imports at the top of the file):

```python
import subprocess
import sys
from pathlib import Path
```

```python
class TestMain:
    def _write_state(self, tmp_path, state):
        state_file = tmp_path / "state.json"
        state_file.write_text(
            json.dumps(state, ensure_ascii=False), encoding="utf-8"
        )
        return state_file

    def _patch_log(self, monkeypatch, tmp_path):
        log_path = tmp_path / "decisions.jsonl"
        monkeypatch.setattr(decide, "default_log_path", lambda: log_path)
        return log_path

    def _patch_api(self, monkeypatch, answers, status=200):
        body = answers_body(answers) if answers is not None else b"garbage"
        monkeypatch.setattr(
            decide.urllib.request,
            "urlopen",
            lambda request, timeout=None: FakeResponse(body, status),
        )
        monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")

    def test_select_option_end_to_end(self, tmp_path, monkeypatch, capsys):
        state = _valid_state()
        log_path = self._patch_log(monkeypatch, tmp_path)
        self._patch_api(monkeypatch, make_answers(state, choice="option_a",
                                                  confidence=0.94))
        exit_code = decide.main(
            [f"--state-file={self._write_state(tmp_path, state)}"]
        )
        captured = capsys.readouterr()
        assert exit_code == 0
        output = json.loads(captured.out)
        assert output["decision"] == "SELECT_OPTION"
        assert output["selected_option"] == "option_a"
        assert output["detail"] is None
        assert output["model"] == "jev-latest"
        assert "redacted" not in captured.err
        log_lines = log_path.read_text(encoding="utf-8").strip().splitlines()
        assert json.loads(log_lines[0])["resolution"] == "SELECT_OPTION"

    def test_secret_redacted_before_sending(self, tmp_path, monkeypatch, capsys):
        state = _valid_state()
        state["evidence"] = ["uses key sk-abcdef1234567890"]
        sent = {}

        def capture_urlopen(request, timeout=None):
            sent["body"] = request.data.decode("utf-8")
            return FakeResponse(answers_body(make_answers(state)))

        monkeypatch.setattr(decide.urllib.request, "urlopen", capture_urlopen)
        monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
        self._patch_log(monkeypatch, tmp_path)
        decide.main([f"--state-file={self._write_state(tmp_path, state)}"])
        captured = capsys.readouterr()
        assert "redacted: 1 value(s)" in captured.err
        assert "sk-abcdef1234567890" not in sent["body"]
        assert "sk-abcdef1234567890" not in captured.out

    def test_missing_api_key_is_provider_unavailable(
        self, tmp_path, monkeypatch, capsys
    ):
        state = _valid_state()
        monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
        self._patch_log(monkeypatch, tmp_path)
        exit_code = decide.main(
            [f"--state-file={self._write_state(tmp_path, state)}"]
        )
        captured = capsys.readouterr()
        assert exit_code == 0
        output = json.loads(captured.out)
        assert output["decision"] == "PROVIDER_UNAVAILABLE"
        assert output["detail"] == "TYPESAFE_API_KEY is not set"

    @pytest.mark.parametrize("status", [401, 422, 429, 500, 503])
    def test_http_error_is_provider_unavailable(
        self, tmp_path, monkeypatch, capsys, status
    ):
        state = _valid_state()
        self._patch_api(monkeypatch, None, status=status)
        self._patch_log(monkeypatch, tmp_path)
        decide.main([f"--state-file={self._write_state(tmp_path, state)}"])
        output = json.loads(capsys.readouterr().out)
        assert output["decision"] == "PROVIDER_UNAVAILABLE"
        assert output["detail"] == f"HTTP {status}"

    def test_network_error_is_provider_unavailable(
        self, tmp_path, monkeypatch, capsys
    ):
        state = _valid_state()

        def refuse(request, timeout=None):
            raise urllib.error.URLError("connection refused")

        monkeypatch.setattr(decide.urllib.request, "urlopen", refuse)
        monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
        self._patch_log(monkeypatch, tmp_path)
        decide.main([f"--state-file={self._write_state(tmp_path, state)}"])
        output = json.loads(capsys.readouterr().out)
        assert output["decision"] == "PROVIDER_UNAVAILABLE"
        assert output["detail"] == "transport failure: URLError"

    def test_timeout_is_provider_unavailable(self, tmp_path, monkeypatch, capsys):
        state = _valid_state()

        def raise_timeout(request, timeout=None):
            raise TimeoutError("timed out")

        monkeypatch.setattr(decide.urllib.request, "urlopen", raise_timeout)
        monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
        self._patch_log(monkeypatch, tmp_path)
        decide.main([f"--state-file={self._write_state(tmp_path, state)}"])
        output = json.loads(capsys.readouterr().out)
        assert output["decision"] == "PROVIDER_UNAVAILABLE"
        assert output["detail"] == "transport failure: TimeoutError"

    def test_malformed_response_is_provider_unavailable(
        self, tmp_path, monkeypatch, capsys
    ):
        state = _valid_state()
        self._patch_api(monkeypatch, None)
        self._patch_log(monkeypatch, tmp_path)
        decide.main([f"--state-file={self._write_state(tmp_path, state)}"])
        output = json.loads(capsys.readouterr().out)
        assert output["decision"] == "PROVIDER_UNAVAILABLE"

    def test_invalid_state_is_insufficient_options(
        self, tmp_path, monkeypatch, capsys
    ):
        state = _valid_state()
        state["alternatives"] = state["alternatives"][:1]
        self._patch_log(monkeypatch, tmp_path)
        exit_code = decide.main(
            [f"--state-file={self._write_state(tmp_path, state)}"]
        )
        captured = capsys.readouterr()
        assert exit_code == 0
        output = json.loads(captured.out)
        assert output["decision"] == "INSUFFICIENT_OPTIONS"
        assert "2 to 5" in output["detail"]

    def test_missing_state_file_exits_2(self, capsys):
        assert decide.main(["--state-file=/nonexistent/state.json"]) == 2
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "cannot read state file" in captured.err

    def test_malformed_state_json_exits_2(self, tmp_path, capsys):
        state_file = tmp_path / "state.json"
        state_file.write_text("{not json", encoding="utf-8")
        assert decide.main([f"--state-file={state_file}"]) == 2
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "not valid JSON" in captured.err

    def test_missing_required_argument_exits_2(self, capsys):
        with pytest.raises(SystemExit) as excinfo:
            decide.main([])
        assert excinfo.value.code == 2
        assert capsys.readouterr().out == ""

    def test_main_cjk_end_to_end(self, tmp_path, monkeypatch, capsys):
        state = _valid_state()
        state["question"] = "認証方式はどちらが適切か"
        state["alternatives"][0]["name"] = "案A"
        state["alternatives"][0]["description"] = "同一オリジンのWebアプリ向け。"
        sent = {}

        def capture_urlopen(request, timeout=None):
            sent["body"] = request.data.decode("utf-8")
            return FakeResponse(answers_body(make_answers(state)))

        monkeypatch.setattr(decide.urllib.request, "urlopen", capture_urlopen)
        monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
        self._patch_log(monkeypatch, tmp_path)
        exit_code = decide.main(
            [f"--state-file={self._write_state(tmp_path, state)}"]
        )
        captured = capsys.readouterr()
        assert exit_code == 0
        assert "案A" in sent["body"]
        output = json.loads(captured.out)
        assert output["decision"] == "SELECT_OPTION"
        assert output["selected_option"] == "option_a"

    def test_main_survives_log_failure(self, tmp_path, monkeypatch, capsys):
        state = _valid_state()
        self._patch_api(monkeypatch, make_answers(state))
        # A directory path cannot be opened for append.
        monkeypatch.setattr(decide, "default_log_path", lambda: tmp_path)
        exit_code = decide.main(
            [f"--state-file={self._write_state(tmp_path, state)}"]
        )
        captured = capsys.readouterr()
        assert exit_code == 0
        assert "warning" in captured.err
        output = json.loads(captured.out)
        assert output["decision"] == "SELECT_OPTION"


class TestCliContractViaSubprocess:
    def test_missing_state_file_subprocess(self):
        script = Path(decide.__file__)
        result = subprocess.run(
            [sys.executable, str(script), "--state-file", "/nonexistent"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 2
        assert result.stdout == ""


class TestDomainAgnostic:
    def test_no_coding_vocabulary_in_source(self):
        source = Path(decide.__file__).read_text(encoding="utf-8").lower()
        for term in (
            "package.json",
            "sqlite",
            "postgres",
            "jwt",
            "repository",
            "database",
            "authentication",
        ):
            assert term not in source, term
```

Note: the tests use `json` at module level (`json.dumps`, `json.loads`); earlier tasks imported it inside functions. Add `import json` to the top-of-file import block in this step too.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_decide.py -v`
Expected: FAIL with `AttributeError: module 'decide' has no attribute 'main'`

- [ ] **Step 3: Write minimal implementation**

Extend the imports at the top of `skills/autarch/scripts/decide.py`:

```python
import argparse
import time
```

Add at the end of the file:

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
        "reason": "",
    }


def _resolution_output(
    resolution: dict, model: str, detail: str | None = None
) -> dict:
    output = dict(resolution)
    output["detail"] = detail
    output["model"] = model
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="decide.py",
        description="Evaluate a decision state with Jev and print a resolution.",
    )
    parser.add_argument("--state-file", required=True)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--auto-select", type=float, default=DEFAULT_AUTO_SELECT)
    parser.add_argument("--review", type=float, default=DEFAULT_REVIEW)
    parser.add_argument("--min-gap", type=float, default=DEFAULT_MIN_GAP)
    parser.add_argument(
        "--human-preference", type=float, default=DEFAULT_HUMAN_PREFERENCE
    )
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    args = parser.parse_args(argv)

    try:
        raw_state = Path(args.state_file).read_text(encoding="utf-8")
    except OSError as error:
        print(
            f"error: cannot read state file: {type(error).__name__}",
            file=sys.stderr,
        )
        return 2
    try:
        state = json.loads(raw_state)
    except json.JSONDecodeError as error:
        print(
            f"error: state file is not valid JSON: {error.msg}", file=sys.stderr
        )
        return 2

    thresholds = {
        "auto_select": args.auto_select,
        "review": args.review,
        "min_gap": args.min_gap,
        "human_preference": args.human_preference,
    }

    errors = validate_state(state)
    if errors:
        resolution = _empty_resolution("INSUFFICIENT_OPTIONS", "invalid_state")
        output = _resolution_output(resolution, args.model, detail="; ".join(errors))
        print(json.dumps(output, ensure_ascii=False))
        append_log(build_log_record(state, output, None))
        return 0

    latency_ms = None
    try:
        api_key = os.environ.get("TYPESAFE_API_KEY", "").strip()
        if not api_key:
            raise ProviderError("TYPESAFE_API_KEY is not set")
        redacted_state, redaction_count = redact(state)
        if redaction_count:
            print(f"redacted: {redaction_count} value(s)", file=sys.stderr)
        payload = build_request(redacted_state, args.model)
        started = time.perf_counter()
        try:
            status, body = send_request(payload, args.endpoint, args.timeout)
        except OSError as error:
            raise ProviderError(
                f"transport failure: {type(error).__name__}"
            ) from None
        latency_ms = round((time.perf_counter() - started) * 1000)
        if not 200 <= status < 300:
            raise ProviderError(f"HTTP {status}")
        parsed = parse_answers(body, redacted_state)
        resolution = resolve(redacted_state, parsed, thresholds)
    except ProviderError as error:
        empty = _empty_resolution("PROVIDER_UNAVAILABLE", "provider_error")
        output = _resolution_output(empty, args.model, detail=str(error))
        print(json.dumps(output, ensure_ascii=False))
        append_log(build_log_record(state, output, latency_ms))
        return 0

    output = _resolution_output(resolution, args.model)
    print(json.dumps(output, ensure_ascii=False))
    append_log(build_log_record(state, output, latency_ms))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the full suite**

Run: `python3 -m pytest tests/ -v`
Expected: PASS (all tests pass, including subprocess test)

- [ ] **Step 5: Commit**

```bash
git add skills/autarch/scripts/decide.py tests/test_decide.py
git commit -m "feat: wire CLI entry point with deterministic output contract

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 10: SKILL.md

**Files:**
- Create: `skills/autarch/SKILL.md`
- Create: `.claude/skills/autarch` (symlink to `../../skills/autarch`)
- Test: `tests/test_skill_md.py`

**Interfaces:**
- Consumes: `decide.py` from Tasks 1–9 (invoked as a subprocess by the agent).
- Produces: the complete skill document — frontmatter with `disable-model-invocation: true`, Steps 1–13, the neutral-generation and secret-exclusion instructions, the state schema, and the resolution handling rules. The symlink makes `/autarch` discoverable in clones of this repository.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_skill_md.py`:

```python
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL_MD = REPO_ROOT / ".claude" / "skills" / "autarch" / "SKILL.md"


def _read():
    return SKILL_MD.read_text(encoding="utf-8")


def _frontmatter(text):
    assert text.startswith("---\n")
    end = text.index("\n---\n", 4)
    return text[4:end]


class TestSkillMarkdown:
    def test_skill_exists_through_symlink(self):
        assert SKILL_MD.is_file()

    def test_frontmatter_disables_model_invocation(self):
        frontmatter = _frontmatter(_read())
        assert "name: autarch" in frontmatter
        assert "description: Resolve a decision by generating alternatives and evaluating them with Jev." in frontmatter
        assert "disable-model-invocation: true" in frontmatter

    def test_contains_all_thirteen_steps(self):
        text = _read()
        for step in range(1, 14):
            assert f"### Step {step}" in text

    def test_neutral_generation_instruction(self):
        text = _read()
        assert "Generate alternatives neutrally." in text
        assert "comparable level of detail." in text

    def test_secret_exclusion_instruction(self):
        assert "Do not read or include .env files, credential files," in _read()

    def test_probability_is_not_a_score(self):
        assert "NOT scores" in _read()

    def test_ask_user_does_not_repeat_question(self):
        assert "Do NOT repeat the original technical question" in _read()

    def test_decide_py_invocation_documented(self):
        text = _read()
        assert "decide.py" in text
        assert "--state-file" in text
        assert "TYPESAFE_API_KEY" in text
        assert "SELECT_OPTION_WITH_CAUTION" in text
        assert "PROVIDER_UNAVAILABLE" in text
        assert "INSUFFICIENT_OPTIONS" in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_skill_md.py -v`
Expected: FAIL at `test_skill_exists_through_symlink` (`AssertionError` — no skill file yet)

- [ ] **Step 3: Write the skill document**

Create `skills/autarch/SKILL.md`:

````markdown
---
name: autarch
description: Resolve a decision by generating alternatives and evaluating them with Jev.
disable-model-invocation: true
---

# Autarch — structured decision resolution

Autarch converts an unresolved decision into a selected option. You (the
agent) build the decision material; Jev (TypeSafe AI System One) evaluates
it; `decide.py` applies the decision policy deterministically. Run this
skill only when the user explicitly invokes `/autarch`. Never invoke it on
your own initiative.

## Execution flow

### Step 1 — Capture the question

Identify the decision currently blocking progress: the question the agent
asked most recently, the conversation context, and the user's original
goal. If the user passed a question as arguments to `/autarch`, use that
question directly.

### Step 2 — Normalize the decision

Restate the question as one clear decision problem: what is being chosen
and why. Do not name a preferred answer.

Example:

- Original: "JWTとCookieどちらにしますか？"
- Decision problem: "Select the authentication state strategy that best
  matches the current project."

### Step 3 — Generate alternatives (2–5, neutral)

Generate 2 to 5 materially different, feasible options; default to 3. If
the pending question offers two options, add a materially different third
option (including "keep the current approach") when one exists. Exclude
obviously unreasonable options and mere rewordings of another option.

Generate alternatives neutrally.

Do not describe any option as recommended, best, preferred,
safer, simpler, superior, or inferior before Jev evaluation
unless that statement is directly established by evidence.

Describe every alternative using the same structure and
comparable level of detail.

Each alternative uses the same schema:

```json
{
  "id": "machine_readable_id",
  "name": "Display Name",
  "description": "One-sentence description.",
  "advantages": ["..."],
  "disadvantages": ["..."],
  "assumptions": ["..."]
}
```

Rules for `id`: unique within the state, non-empty, at most 64 characters,
only `A-Za-z0-9._-`, must not start with a symbol, must not contain `__`.

### Step 4 — Gather evidence

Collect only the context needed to compare the options (for coding
decisions: repository structure, existing dependencies, configuration,
requirements, constraints).

Do not read or include .env files, credential files,
private keys, authentication tokens, or secret stores
as evidence.

### Step 5 — Generate criteria

Generate the evaluation criteria this decision actually needs (0–8). Each
criterion has an ordered rubric whose levels run from worst to best, with
at least 2 levels. `weight` is optional and defaults to 1.0.

```json
{
  "id": "requirement_fit",
  "name": "Requirement fit",
  "weight": 0.35,
  "rubric": ["Very poor fit", "Poor fit", "Acceptable fit", "Good fit", "Excellent fit"]
}
```

Choose criteria for the decision at hand; do not default to a fixed
coding-specific set.

### Step 6 — Write the state JSON

```bash
STATE_FILE=$(mktemp /tmp/autarch-state-XXXXXX.json)
```

State schema (`goal`, `question`, `alternatives` required; `criteria` may
be empty or omitted):

```json
{
  "goal": "the user's original goal",
  "question": "the normalized decision problem",
  "known_constraints": ["..."],
  "environment": {},
  "evidence": ["..."],
  "alternatives": ["...as defined in Step 3..."],
  "criteria": ["...as defined in Step 5..."]
}
```

### Step 7 — Run decide.py

Run the engine from this skill's directory (`scripts/decide.py` sits next
to this SKILL.md):

```bash
python3 "$SKILL_DIR/scripts/decide.py" --state-file "$STATE_FILE"
```

Requires the `TYPESAFE_API_KEY` environment variable. Optional flags:
`--model jev-latest --auto-select 0.85 --review 0.60 --min-gap 0.15
--human-preference 0.70 --timeout 30 --endpoint https://api.typesafe.ai`.

Exit codes: `0` = a resolution JSON was printed to stdout; `2` = usage
error, missing state file, or malformed JSON; `1` = internal error. For
exit codes other than 0, do not invent a decision — report that Autarch
failed to execute.

### Step 8 — Read the resolution JSON

stdout contains exactly one JSON object with: `decision`, `rule`,
`selected_option`, `confidence`, `probability`, `probabilities`,
`human_preference_probability`, `score_summary`, `reason`, `detail`,
`model`.

`probabilities` are a probability distribution over the alternatives
(they sum to about 1). They are NOT scores — never present them as
"72 points" or similar. Multi-criterion evaluation lives in
`score_summary`.

### Step 9 — SELECT_OPTION

Adopt `selected_option` and continue the original task. Tell the user
briefly which option was chosen, the one-line reason, and the Jev
confidence.

### Step 10 — SELECT_OPTION_WITH_CAUTION

Same as Step 9, but state the uncertainty first in one short sentence
(for example, which assumption the choice depends on).

### Step 11 — ASK_USER

Do NOT repeat the original technical question. Using the resolution
`rule`, `score_summary`, `probabilities`, and your evidence, reduce the
decision to the smallest question only the user can answer — usually one
distinguishing factor. Present the options as a short list with one-line
neutral descriptors, name the deciding factor, and ask only that.
Example:

```text
Autarch could not decide this on technical merit alone.

The difference comes down to one thing: whether this system will
also be used from mobile apps or external APIs in the future.

A. JWT — suited to multiple clients / external APIs
B. Session Cookie — simplest for this same-origin web app

Do you have such a plan, yes or no?
```

If `rule` is `human_preference`, the decision depends on the user's taste
or intent — ask for that preference directly instead of technical details.

### Step 12 — PROVIDER_UNAVAILABLE

State that Jev could not be reached or returned an unusable response (see
`detail`), and that no automatic selection was made. Do not pick an option
yourself unless the user asks you to decide without Autarch.

### Step 13 — INSUFFICIENT_OPTIONS

The state failed validation (see `detail`). Fix the state — usually the
alternatives structure or ids — and run Steps 6–7 again. If materially
different options cannot be constructed, tell the user why the decision
cannot be structured and ask how to proceed.
````

- [ ] **Step 4: Create the symlink and run tests**

```bash
mkdir -p .claude/skills
ln -s ../../skills/autarch .claude/skills/autarch
python3 -m pytest tests/test_skill_md.py -v
```

Expected: PASS (all tests pass)

- [ ] **Step 5: Commit**

```bash
git add skills/autarch/SKILL.md tests/test_skill_md.py .claude/skills/autarch
git commit -m "feat: add autarch SKILL.md with explicit-invocation-only frontmatter

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 11: Live integration test

**Files:**
- Create: `tests/test_live.py`

**Interfaces:**
- Consumes: `decide.main` from Task 9.
- Produces: a live smoke test that is skipped unless `AUTARCH_LIVE=1` and `TYPESAFE_API_KEY` are set. It exercises the real API once with a minimal state (2 alternatives, 1 criterion) and asserts a complete resolution plus a decision-log line.

- [ ] **Step 1: Write the test**

Create `tests/test_live.py`:

```python
"""Live integration tests.

Run explicitly with a real key:

    AUTARCH_LIVE=1 TYPESAFE_API_KEY=... python3 -m pytest tests/test_live.py -v
"""

import json
import os
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = (
    Path(__file__).resolve().parent.parent / "skills" / "autarch" / "scripts"
)
sys.path.insert(0, str(SCRIPTS_DIR))

import decide  # noqa: E402

pytestmark = pytest.mark.skipif(
    os.environ.get("AUTARCH_LIVE") != "1"
    or not os.environ.get("TYPESAFE_API_KEY"),
    reason="set AUTARCH_LIVE=1 and TYPESAFE_API_KEY to run live tests",
)

STATE = {
    "goal": "Pick a note-taking approach for a single local user",
    "question": (
        "Which note-taking approach best fits a local single-user workflow?"
    ),
    "known_constraints": ["works offline"],
    "environment": {"os": "linux"},
    "evidence": ["notes are plain text", "no collaboration needed"],
    "alternatives": [
        {
            "id": "plain_files",
            "name": "Plain files",
            "description": "Notes as plain text files in one folder.",
            "advantages": ["no lock-in"],
            "disadvantages": ["no structure"],
            "assumptions": [],
        },
        {
            "id": "structured_app",
            "name": "Structured app",
            "description": "A dedicated app with linking and search.",
            "advantages": ["search"],
            "disadvantages": ["vendor lock-in"],
            "assumptions": [],
        },
    ],
    "criteria": [
        {
            "id": "fit",
            "name": "Requirement fit",
            "rubric": ["Poor fit", "Acceptable fit", "Excellent fit"],
        }
    ],
}


def test_live_end_to_end(tmp_path, capsys):
    state_file = tmp_path / "state.json"
    state_file.write_text(json.dumps(STATE), encoding="utf-8")
    exit_code = decide.main([f"--state-file={state_file}"])
    captured = capsys.readouterr()
    assert exit_code == 0
    output = json.loads(captured.out)
    assert output["decision"] in {
        "SELECT_OPTION",
        "SELECT_OPTION_WITH_CAUTION",
        "ASK_USER",
    }
    assert output["detail"] is None
    assert output["probabilities"] is not None
    assert output["human_preference_probability"] is not None
```

- [ ] **Step 2: Verify skip behavior and run the full suite**

Run: `python3 -m pytest tests/ -v`
Expected: all `test_decide.py` and `test_skill_md.py` tests PASS; the live test reports `SKIPPED` (no `AUTARCH_LIVE` in the environment).

If a real key is available, optionally verify the live path once:

```bash
AUTARCH_LIVE=1 python3 -m pytest tests/test_live.py -v
```

Expected: PASS against the real API.

- [ ] **Step 3: Commit**

```bash
git add tests/test_live.py
git commit -m "test: add explicit-key live integration test for the Jev provider

Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

## Completion check

After Task 11, run the whole suite one final time and confirm the spec's
§15 matrix is fully covered:

```bash
python3 -m pytest tests/ -v
```

All unit and skill tests pass; the live test is skipped without
`AUTARCH_LIVE=1`. The deliverables are: `skills/autarch/SKILL.md`,
`skills/autarch/scripts/decide.py` (stdlib only), `tests/` (pytest),
and the `.claude/skills/autarch` symlink.
