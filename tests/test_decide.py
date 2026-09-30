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
