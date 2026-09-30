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
