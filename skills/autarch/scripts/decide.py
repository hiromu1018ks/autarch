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
