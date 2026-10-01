from pathlib import Path

import case_schema
import decide

CASES_DIR = Path(__file__).resolve().parent.parent / "evals" / "cases"


def all_cases():
    return case_schema.load_cases(CASES_DIR)


def by_id():
    return {case["id"]: case for case in all_cases()}


def test_all_case_files_are_individually_valid():
    all_cases()  # load_cases raises CaseError on any invalid file


def test_all_states_pass_engine_validation():
    for case in all_cases():
        assert decide.validate_state(case["state"]) == [], case["id"]


def test_database_base_cases():
    cases = by_id()
    assert cases["db_constraint_clear"]["expectations"]["acceptable_selections"] == ["sqlite"]
    assert cases["db_info_missing"]["expectations"]["acceptable_decisions"] == ["ASK_USER"]
    assert cases["db_preference_needed"]["expectations"]["acceptable_decisions"] == ["ASK_USER"]
    assert cases["db_preference_needed"]["expectations"]["requires_human_preference"] is True


def test_db_perturbations_declare_derived_from():
    cases = by_id()
    for perturbation in ("reorder", "detail_asymmetry", "evidence_removed",
                         "violating_candidate"):
        derived = cases[f"db_{perturbation}"]["derived_from"]
        assert derived == {"base": "db_constraint_clear", "perturbation": perturbation}


def test_db_violating_candidate_forbids_added_option():
    perturbed = by_id()["db_violating_candidate"]
    assert perturbed["expectations"]["forbidden_selections"] == ["managed_postgres"]
    added = [a["id"] for a in perturbed["state"]["alternatives"] if a["id"] == "managed_postgres"]
    assert added == ["managed_postgres"]
