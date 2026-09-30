#!/usr/bin/env python3
"""Autarch decision engine.

Evaluates a Generic Decision State against Jev (TypeSafe AI System One)
and returns a deterministic resolution. Domain-agnostic by design: this
module knows about decisions, not about any particular field.
"""

import json
import os
import re
import urllib.error
import urllib.request

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
