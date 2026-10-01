"""Independent constraint-track schema, verdicts, and runner integration."""

import copy
import importlib
import json
from pathlib import Path

import pytest

import decide

CASES = Path(__file__).resolve().parents[1] / "evals" / "cases_constraints"


def module(name="constraint_cases"):
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError:
        pytest.fail(f"{name} is not implemented")


def fixture_case(two_phases=False):
    state = {
        "goal": "Select an embedded store", "question": "Which store fits?",
        "known_constraints": ["No separate database server"],
        "environment": {"language": "Python"}, "evidence": ["SQLite is embedded"],
        "alternatives": [
            {"id": "sqlite", "name": "SQLite", "description": "Embedded SQL"},
            {"id": "json", "name": "JSON", "description": "Local JSON files"},
            {"id": "postgres", "name": "PostgreSQL", "description": "Client/server SQL"},
        ], "criteria": [],
        "evidence_records": [{"id": "doc", "fact": "SQLite has no separate server",
            "source": "https://www.sqlite.org/serverless.html",
            "checked_at": "2026-10-01T00:00:00Z", "kind": "verified"}],
        "hard_constraints": [{"id": "embedded", "description": "No server",
            "assessments": {option: {"status": status, "evidence_ids": ["doc"]}
                for option, status in [("sqlite", "met"), ("json", "met"),
                                       ("postgres", "violated")]}}],
    }
    exp = {"decision": "SELECT_OPTION", "rule": "confidence",
        "eligible_option_ids": ["sqlite", "json"], "excluded_option_ids": ["postgres"],
        "unknown_assessments": [], "selected_option": "sqlite"}
    case = {"id": "sample", "topic": "database", "state": state,
            "phases": [{"phase": 1, "expectations": exp}]}
    if two_phases:
        case["phase2"] = {"evidence_records": copy.deepcopy(state["evidence_records"]),
            "hard_constraints": copy.deepcopy(state["hard_constraints"]),
            "revision": {"round": 1, "action": "investigation", "summary": "Checked docs"}}
        state["hard_constraints"][0]["assessments"]["json"] = {
            "status": "unknown", "evidence_ids": []}
        case["phases"][0]["expectations"] = {
            **exp, "decision": "ASK_USER", "rule": "constraint_unverified",
            "eligible_option_ids": ["sqlite"], "selected_option": None,
            "unknown_assessments": [{"option_id": "json", "constraint_id": "embedded"}]}
        case["phases"].append({"phase": 2, "expectations": exp})
    return case


def record(case, phase=1, index=1):
    exp = case["phases"][phase - 1]["expectations"]
    resolution = {key: exp[key] for key in ("decision", "rule", "selected_option")}
    resolution["constraint_check"] = {"mode": "structured",
        "eligible_option_ids": exp["eligible_option_ids"],
        "excluded_options": [{"option_id": option} for option in exp["excluded_option_ids"]],
        "unknown_assessments": exp["unknown_assessments"]}
    return {"case_id": case["id"], "case_kind": "constraints", "phase": phase,
            "run_index": index, "resolution": resolution}


def write_case(tmp_path, case):
    (tmp_path / "case.json").write_text(json.dumps(case), encoding="utf-8")
    return tmp_path


@pytest.mark.parametrize("two_phases", [False, True])
def test_load_and_judge_valid_cases(tmp_path, two_phases):
    api = module()
    case = fixture_case(two_phases)
    assert api.load_constraint_cases(write_case(tmp_path, case)) == [case]
    records = [record(case, p["phase"]) for p in case["phases"]]
    assert api.constraint_verdict(case, records) == "pass"
    records[-1]["resolution"]["rule"] = "unexpected"
    assert api.constraint_verdict(case, records) == "fail"


def test_phase2_replaces_fields_without_changing_original():
    api = module()
    case = fixture_case(True)
    original = copy.deepcopy(case)
    state = api.constraint_phase2_state(case)
    assert state["evidence_records"] == case["phase2"]["evidence_records"]
    assert state["hard_constraints"] == case["phase2"]["hard_constraints"]
    assert state["revision"] == case["phase2"]["revision"]
    assert state["known_constraints"] == case["state"]["known_constraints"]
    assert state["evidence"] == case["state"]["evidence"]
    assert decide.validate_state(state) == []
    state["evidence_records"][0]["fact"] = "changed"
    assert case == original


def test_missing_and_provider_phases_are_not_passed():
    api = module()
    case = fixture_case(True)
    assert api.constraint_verdict(case, []) == "incomplete"
    assert api.constraint_verdict(case, [record(case)]) == "incomplete"
    provider = record(case)
    provider["resolution"] = {"decision": "PROVIDER_UNAVAILABLE", "rule": "provider_error"}
    assert api.constraint_verdict(case, [provider]) == "unavailable"
    assert api.constraint_verdict(case, [provider, record(case, 2)]) == "unavailable"


@pytest.mark.parametrize("field,value", [
    ("decision", "ASK_USER"), ("rule", "different"),
    ("selected_option", "postgres"), ("eligible_option_ids", ["sqlite"]),
    ("excluded_option_ids", []),
    ("unknown_assessments", [{"option_id": "json", "constraint_id": "embedded"}]),
])
def test_verdict_compares_each_expected_field(field, value):
    api = module()
    case = fixture_case()
    run = record(case)
    if field == "excluded_option_ids":
        run["resolution"]["constraint_check"]["excluded_options"] = value
    elif field in ("eligible_option_ids", "unknown_assessments"):
        run["resolution"]["constraint_check"][field] = value
    else:
        run["resolution"][field] = value
    assert api.constraint_verdict(case, [run]) == "fail"


@pytest.mark.parametrize("mutation", ["duplicate_phase", "unknown_case", "unknown_phase", "mixed_index"])
def test_ambiguous_records_are_rejected(mutation):
    api = module()
    case = fixture_case(True)
    records = [record(case), record(case, 2)]
    if mutation == "duplicate_phase":
        records.append(record(case))
    elif mutation == "unknown_case":
        records[0]["case_id"] = "missing"
    elif mutation == "unknown_phase":
        records[0]["phase"] = 3
    else:
        records[1]["run_index"] = 2
    with pytest.raises(ValueError):
        api.constraint_verdict(case, records)


def test_metrics_count_all_cases_and_missing_runs():
    api = module()
    first, second = fixture_case(True), fixture_case()
    second["id"] = "other"
    runs = [record(first), record(first, 2), record(second), record(first, index=2)]
    runs[2]["resolution"]["rule"] = "wrong"
    metrics = api.constraint_metrics([first, second], runs)
    assert metrics["counts"] == {"pass": 1, "fail": 1, "unavailable": 0, "incomplete": 2}
    assert metrics["pass_rate"] == 0.5
    assert api.constraint_metrics([first, second], [])["counts"]["incomplete"] == 2
    assert api.constraint_metrics([first], [])["pass_rate"] is None
    runs[0]["resolution"] = {"decision": "PROVIDER_UNAVAILABLE"}
    assert api.constraint_metrics([first, second], runs)["counts"]["unavailable"] == 1
    with pytest.raises(ValueError):
        api.constraint_metrics([first], [record(second)])


@pytest.mark.parametrize("mutation", ["invalid_state", "invalid_flag", "overlap", "unknown_id",
    "selected_excluded", "ask_selected", "wrong_preflight", "phase_missing", "phase_duplicate",
    "phase2_missing", "bad_revision", "phase2_invalid", "invalid_not_expected"])
def test_load_rejects_invalid_or_conflicting_cases(tmp_path, mutation):
    api = module()
    case = fixture_case(True)
    exp = case["phases"][0]["expectations"]
    if mutation == "invalid_state":
        case["state"]["goal"] = ""
    elif mutation == "invalid_flag":
        case["expected_validation_errors"] = "yes"
    elif mutation == "overlap":
        exp["excluded_option_ids"].append("sqlite")
    elif mutation == "unknown_id":
        exp["eligible_option_ids"].append("missing")
    elif mutation == "selected_excluded":
        case["phases"][1]["expectations"]["selected_option"] = "postgres"
    elif mutation == "ask_selected":
        exp["selected_option"] = "sqlite"
    elif mutation == "wrong_preflight":
        exp["rule"] = "investigation_exhausted"
    elif mutation == "phase_missing":
        case["phases"] = [case["phases"][1]]
    elif mutation == "phase_duplicate":
        case["phases"].append(case["phases"][0])
    elif mutation == "phase2_missing":
        del case["phase2"]
    elif mutation == "bad_revision":
        case["phase2"]["revision"]["round"] = 2
    elif mutation == "phase2_invalid":
        case["phase2"]["evidence_records"] = []
    elif mutation == "invalid_not_expected":
        case["expected_validation_errors"] = True
    with pytest.raises(ValueError):
        api.load_constraint_cases(write_case(tmp_path, case))


def test_intentionally_invalid_requires_explicit_flag(tmp_path):
    api = module()
    case = fixture_case()
    case["state"]["evidence_records"][0]["kind"] = "inference"
    case["phases"][0]["expectations"] = {"decision": "INSUFFICIENT_OPTIONS",
        "rule": "invalid_state", "selected_option": None, "eligible_option_ids": [],
        "excluded_option_ids": [], "unknown_assessments": []}
    with pytest.raises(ValueError):
        api.load_constraint_cases(write_case(tmp_path, case))
    case["expected_validation_errors"] = True
    assert api.load_constraint_cases(write_case(tmp_path, case)) == [case]
    run = record(case)
    run["resolution"]["constraint_check"] = None
    assert api.constraint_verdict(case, [run]) == "pass"


def test_bundled_seven_cases_have_checked_evidence_and_valid_states():
    api = module()
    cases = api.load_constraint_cases(CASES)
    assert {c["id"] for c in cases} == {"db_eligible", "env_single", "env_none",
        "env_unknown_resolved", "env_unknown_exhausted", "inference_invalid", "cost_verified"}
    assert sum(len(c["phases"]) for c in cases) == 9
    for case in cases:
        assert bool(decide.validate_state(case["state"])) is case.get("expected_validation_errors", False)
        for evidence in case["state"]["evidence_records"]:
            assert evidence["source"].startswith("https://")
            assert evidence["checked_at"].startswith("2026-10-01T")
        if len(case["phases"]) == 2:
            assert decide.validate_state(api.constraint_phase2_state(case)) == []


def test_runner_dry_run_and_empty_directory(tmp_path, capsys):
    runner = module("run_constraint_cases")
    out = tmp_path / "out"
    assert runner.main(["--dry-run", "--runs", "3", "--out-dir", str(out)]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["total_decide_calls"] == 27
    assert len(plan["cases"]) == 7
    assert not out.exists()
    assert runner.main(["--cases-dir", str(tmp_path), "--dry-run"]) == 2
    assert "no case files" in capsys.readouterr().err


@pytest.mark.parametrize("runs", ["0", "-1"])
def test_runner_rejects_nonpositive_run_counts(runs):
    with pytest.raises(SystemExit) as exc:
        module("run_constraint_cases").main(["--runs", runs, "--dry-run"])
    assert exc.value.code == 2


def test_runner_reuses_retry_and_generates_two_phase_states(tmp_path, monkeypatch):
    runner = module("run_constraint_cases")
    api = module()
    case = fixture_case(True)
    cases_dir = tmp_path / "cases"
    cases_dir.mkdir()
    write_case(cases_dir, case)
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    seen = []
    def spy(case_arg, args, state_dir, state=None, phase=None):
        seen.append((copy.deepcopy(state), phase, vars(args).copy()))
        return {**record(case_arg, phase), "attempt": 1, "latency_ms": 1}
    monkeypatch.setattr(runner.run_fixed_state, "run_with_retry", spy)
    out = tmp_path / "out"
    assert runner.main(["--cases-dir", str(cases_dir), "--out-dir", str(out), "--runs", "2",
        "--interval", "0", "--gate-order", "evidence_first", "--model", "test-model",
        "--auto-select", "0.9", "--review", "0.61", "--min-gap", "0.16",
        "--human-preference", "0.71", "--sufficiency", "0.8",
        "--blocker-confidence", "0.7", "--capture-evaluation"]) == 0
    assert [p for _, p, _ in seen] == [1, 2, 1, 2]
    assert "revision" not in seen[0][0]
    assert seen[1][0] == api.constraint_phase2_state(case)
    assert seen[0][2]["capture_evaluation"] is True
    assert seen[0][2]["gate_order"] == "evidence_first"
    assert seen[0][2]["model"] == "test-model"
    records = [json.loads(line) for line in (out / "constraint_runs.jsonl").read_text().splitlines()]
    assert all(r["case_kind"] == "constraints" for r in records)
    assert [r["run_index"] for r in records] == [1, 1, 2, 2]
    assert not (out / "fixed_state_runs.jsonl").exists()
    summary = json.loads((out / "constraint_summary.json").read_text())
    assert summary["counts"] == {"pass": 2, "fail": 0, "unavailable": 0, "incomplete": 0}
    env = json.loads((out / "environment.json").read_text())
    assert env["gate_order"] == "evidence_first" and env["capture_evaluation"] is True
    assert env["thresholds"] == {"auto_select": 0.9, "review": 0.61, "min_gap": 0.16,
        "human_preference": 0.71, "sufficiency": 0.8, "blocker_confidence": 0.7}


def test_runner_fake_decide_uses_real_preflight_without_provider_calls(tmp_path, monkeypatch):
    runner = module("run_constraint_cases")
    api = module()
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    marker = tmp_path / "provider_calls"
    script = tmp_path / "fake_decide.py"
    scripts = Path(decide.__file__).parent
    script.write_text(f'''import sys, json
from pathlib import Path
sys.path.insert(0, {str(scripts)!r})
import decide
calls = Path({str(marker)!r})
def forbidden(*args):
    calls.write_text("unexpected provider call")
    raise AssertionError("Provider must not be called for preflight stops")
decide.send_request = forbidden
decide.default_log_path = lambda: Path({str(tmp_path / "decide_log.jsonl")!r})
raise SystemExit(decide.main())
''')
    cases_dir = tmp_path / "cases"
    cases_dir.mkdir()
    for case in api.load_constraint_cases(CASES):
        if case["id"] in ("env_single", "env_none", "env_unknown_exhausted", "inference_invalid"):
            (cases_dir / f"{case['id']}.json").write_text(json.dumps(case))
    out = tmp_path / "out"
    assert runner.main(["--cases-dir", str(cases_dir), "--out-dir", str(out), "--runs", "1",
        "--interval", "0", "--decide-script", str(script)]) == 0
    assert not marker.exists()
    assert json.loads((out / "constraint_summary.json").read_text())["counts"]["pass"] == 4
