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
            base = {"name": "N", "description": "D"}
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
