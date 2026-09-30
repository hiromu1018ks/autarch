import json
import pytest
import subprocess
import sys
import urllib.error
from pathlib import Path

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

    def test_non_utf8_state_file_exits_2(self, tmp_path, capsys):
        state_file = tmp_path / "state.json"
        state_file.write_bytes(b"\xff\xfe{\x00b\x00a\x00d\x00")
        assert decide.main([f"--state-file={state_file}"]) == 2
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
