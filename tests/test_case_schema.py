import json

import pytest

import case_schema
import decide


def make_alternative(option_id):
    return {
        "id": option_id,
        "name": option_id.replace("_", " ").title(),
        "description": f"One-sentence description of {option_id}.",
        "advantages": ["advantage"],
        "disadvantages": ["disadvantage"],
        "assumptions": [],
    }


def make_state(alternatives=None, evidence=None):
    return {
        "goal": "Pick an approach",
        "question": "Which approach fits best?",
        "known_constraints": ["works offline"],
        "environment": {"os": "linux"},
        "evidence": evidence if evidence is not None else ["the app runs locally"],
        "alternatives": alternatives or [make_alternative("alpha"), make_alternative("beta")],
        "criteria": [
            {
                "id": "fit",
                "name": "Requirement fit",
                "weight": 0.6,
                "rubric": ["Poor fit", "Acceptable fit", "Good fit"],
            },
            {
                "id": "burden",
                "name": "Operational burden",
                "weight": 0.4,
                "rubric": ["High burden", "Low burden"],
            },
        ],
    }


def make_case(case_id="db_constraint_clear", topic="database",
              situation="constraint_clear", derived_from=None,
              alternatives=None, evidence=None, expectations=None):
    if expectations is None:
        ask_only = situation != "constraint_clear"
        expectations = {
            "acceptable_decisions": (
                ["ASK_USER"] if ask_only else ["SELECT_OPTION", "SELECT_OPTION_WITH_CAUTION"]
            ),
            "acceptable_selections": [] if ask_only else ["alpha"],
            "forbidden_selections": [],
            "requires_human_preference": ask_only,
        }
    return {
        "id": case_id,
        "topic": topic,
        "situation": situation,
        "state": make_state(alternatives, evidence),
        "expectations": expectations,
        "derived_from": derived_from,
    }


def test_valid_case_has_no_violations():
    assert case_schema.validate_case(make_case()) == []


def test_situation_and_topic_are_enforced():
    assert any("situation" in e for e in case_schema.validate_case(make_case(situation="wild")))
    assert any("topic" in e for e in case_schema.validate_case(make_case(topic="travel")))


def test_ask_case_allows_empty_selections():
    case = make_case(situation="info_missing")
    assert case_schema.validate_case(case) == []


def test_selection_must_reference_existing_alternative_ids():
    case = make_case()
    case["expectations"]["acceptable_selections"] = ["ghost"]
    assert any("acceptable_selections" in e for e in case_schema.validate_case(case))


def test_derived_from_shape_is_checked():
    bad = make_case(derived_from={"base": "db_constraint_clear", "perturbation": "nonsense"})
    assert any("derived_from" in e for e in case_schema.validate_case(bad))


def test_scenario_expectations_validation():
    good = {
        "situation": "constraint_clear",
        "required_alternatives": [["sqlite"], ["postgres", "postgresql"]],
        "forbidden_alternatives": [["managed"]],
        "acceptable_decisions": ["SELECT_OPTION", "SELECT_OPTION_WITH_CAUTION"],
        "acceptable_selections": [["sqlite"]],
        "requires_human_preference": False,
    }
    assert case_schema.validate_scenario_expectations(good) == []
    bad = dict(good, required_alternatives=[["sqlite"], []])
    assert any("required_alternatives" in e
               for e in case_schema.validate_scenario_expectations(bad))


def test_load_cases_reports_every_bad_file(tmp_path):
    (tmp_path / "good.json").write_text(json.dumps(make_case()), encoding="utf-8")
    (tmp_path / "bad.json").write_text("{not json", encoding="utf-8")
    try:
        case_schema.load_cases(tmp_path)
        raise AssertionError("expected CaseError")
    except case_schema.CaseError as error:
        assert "bad.json" in str(error)


def build_full_set():
    cases = [
        make_case(f"{topic}_{situation}", topic, situation)
        for topic in case_schema.TOPICS
        for situation in case_schema.SITUATIONS
    ]
    for topic in ("database", "authentication"):
        base = next(c for c in cases if c["id"] == f"{topic}_constraint_clear")
        base_alts = [dict(a) for a in base["state"]["alternatives"]]
        cases.append(make_case(
            f"{topic}_reorder", topic, "constraint_clear",
            derived_from={"base": base["id"], "perturbation": "reorder"},
            alternatives=[dict(a) for a in reversed(base_alts)],
        ))
        detailed = [dict(a) for a in base_alts]
        detailed[0]["description"] += " Extra detail sentence."
        cases.append(make_case(
            f"{topic}_detail_asymmetry", topic, "constraint_clear",
            derived_from={"base": base["id"], "perturbation": "detail_asymmetry"},
            alternatives=detailed,
        ))
        cases.append(make_case(
            f"{topic}_evidence_removed", topic, "constraint_clear",
            derived_from={"base": base["id"], "perturbation": "evidence_removed"},
            evidence=[],
        ))
        violating = [dict(a) for a in base_alts] + [make_alternative("gamma")]
        case = make_case(
            f"{topic}_violating_candidate", topic, "constraint_clear",
            derived_from={"base": base["id"], "perturbation": "violating_candidate"},
            alternatives=violating,
        )
        case["expectations"]["forbidden_selections"] = ["gamma"]
        cases.append(case)
    return cases


def test_validate_case_set_accepts_complete_set():
    assert case_schema.validate_case_set(build_full_set()) == []


def test_validate_case_set_rejects_missing_base_case():
    cases = [c for c in build_full_set() if c["id"] != "deployment_preference_needed"]
    assert any("missing base cases" in e for e in case_schema.validate_case_set(cases))


def test_validate_case_set_rejects_missing_derived_case():
    cases = [c for c in build_full_set()
             if c["id"] != "authentication_violating_candidate"]
    assert any("derived cases" in e for e in case_schema.validate_case_set(cases))


def test_validate_case_set_rejects_non_permuted_reorder():
    cases = build_full_set()
    base = next(c for c in cases if c["id"] == "database_constraint_clear")
    for case in cases:
        if case["id"] == "database_reorder":
            case["state"]["alternatives"] = [dict(a) for a in base["state"]["alternatives"]]
    assert any("reorder" in e for e in case_schema.validate_case_set(cases))


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

    def test_phase2_unhashable_decision_entries_return_errors_not_crash(self):
        case = valid_loop_case()
        case["investigation"]["phase2"]["acceptable_decisions"] = [{"a": 1}]
        errors = case_schema.validate_loop_case(case)
        assert any("phase2" in e or "acceptable_decisions" in e
                   for e in errors)

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
