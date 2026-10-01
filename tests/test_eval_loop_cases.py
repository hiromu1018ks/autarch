"""Meta-tests for the real loop case files in evals/cases_loop/."""

from pathlib import Path

import case_schema
import decide

REPO_ROOT = Path(__file__).resolve().parent.parent
LOOP_CASES_DIR = REPO_ROOT / "evals" / "cases_loop"
BASE_CASES_DIR = REPO_ROOT / "evals" / "cases"


def all_loop_cases():
    return case_schema.load_loop_cases(LOOP_CASES_DIR)


def test_all_loop_case_files_are_individually_valid():
    all_loop_cases()  # load_loop_cases raises CaseError on any invalid file


def test_loop_states_pass_engine_validation():
    for case in all_loop_cases():
        assert decide.validate_state(case["state"]) == [], case["id"]


def test_phase2_states_pass_engine_validation():
    for case in all_loop_cases():
        assert decide.validate_state(
            case_schema.loop_phase2_state(case)
        ) == [], case["id"]


def test_three_cases_with_distinct_topics():
    cases = all_loop_cases()
    assert len(cases) == 3
    assert {case["topic"] for case in cases} == {
        "database", "authentication", "deployment"
    }


def test_ids_do_not_collide_with_base_cases():
    base_ids = {case["id"] for case in case_schema.load_cases(BASE_CASES_DIR)}
    loop_ids = {case["id"] for case in all_loop_cases()}
    assert base_ids.isdisjoint(loop_ids)


def test_phase1_expects_facts_missing():
    for case in all_loop_cases():
        phase1 = case["investigation"]["phase1"]
        assert phase1["rule"] == "evidence_insufficient", case["id"]
        assert phase1["blocker_class"] == "facts_missing", case["id"]
