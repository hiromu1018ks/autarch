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
