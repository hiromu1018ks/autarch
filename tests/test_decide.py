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
