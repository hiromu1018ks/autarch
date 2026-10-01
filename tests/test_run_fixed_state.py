import json

import pytest

import run_fixed_state

STUB = '''#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

state_path = Path(sys.argv[sys.argv.index("--state-file") + 1])
state = json.loads(state_path.read_text(encoding="utf-8"))
counter_path = state_path.with_suffix(".count")
calls = int(counter_path.read_text()) + 1 if counter_path.exists() else 1
counter_path.write_text(str(calls), encoding="utf-8")
if os.environ.get("STUB_MODE") == "fail_first" and calls == 1:
    print(json.dumps({"decision": "PROVIDER_UNAVAILABLE", "rule": "provider_error",
                      "detail": "transport failure: ConnectionError"}))
    sys.exit(0)
print(json.dumps({"decision": "SELECT_OPTION", "rule": "confidence",
                  "selected_option": state["alternatives"][0]["id"], "confidence": 0.9}))
'''


def write_case(path, case_id, situation, first_selection):
    case = {
        "id": case_id,
        "topic": "database",
        "situation": situation,
        "state": {
            "goal": "Pick an approach",
            "question": "Which approach fits best?",
            "known_constraints": ["works offline"],
            "environment": {},
            "evidence": ["the app runs locally"],
            "alternatives": [
                {"id": first_selection, "name": first_selection.title(),
                 "description": "First option.", "advantages": ["a"],
                 "disadvantages": ["d"], "assumptions": []},
                {"id": "beta", "name": "Beta", "description": "Second option.",
                 "advantages": ["a"], "disadvantages": ["d"], "assumptions": []},
            ],
            "criteria": [],
        },
        "expectations": (
            {"acceptable_decisions": ["ASK_USER"], "acceptable_selections": [],
             "forbidden_selections": []}
            if situation != "constraint_clear" else
            {"acceptable_decisions": ["SELECT_OPTION", "SELECT_OPTION_WITH_CAUTION"],
             "acceptable_selections": [first_selection], "forbidden_selections": []}
        ),
        "derived_from": None,
    }
    path.write_text(json.dumps(case), encoding="utf-8")


@pytest.fixture
def stub_decide(tmp_path):
    path = tmp_path / "stub_decide.py"
    path.write_text(STUB, encoding="utf-8")
    return str(path)


@pytest.fixture
def cases_dir(tmp_path):
    directory = tmp_path / "cases"
    directory.mkdir()
    write_case(directory / "db_constraint_clear.json",
               "db_constraint_clear", "constraint_clear", "alpha")
    write_case(directory / "db_info_missing.json",
               "db_info_missing", "info_missing", "alpha")
    return directory


def test_dry_run_prints_plan_and_creates_nothing(tmp_path, stub_decide,
                                                 cases_dir, capsys):
    exit_code = run_fixed_state.main([
        "--cases-dir", str(cases_dir),
        "--decide-script", stub_decide, "--runs", "2", "--dry-run",
        "--allow-partial-set",
    ])
    plan = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert plan["total_api_calls"] == 4
    assert plan["cases"] == ["db_constraint_clear", "db_info_missing"]
    assert not (tmp_path / "results").exists()


def test_runs_record_every_run_and_environment(tmp_path, stub_decide,
                                               cases_dir, monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    monkeypatch.setenv("STUB_MODE", "ok")
    out_dir = tmp_path / "out"
    exit_code = run_fixed_state.main([
        "--cases-dir", str(cases_dir), "--decide-script", stub_decide,
        "--runs", "2", "--out-dir", str(out_dir),
        "--allow-partial-set", "--interval", "0",
    ])
    assert exit_code == 0
    lines = (out_dir / "fixed_state_runs.jsonl").read_text().strip().splitlines()
    assert len(lines) == 4
    record = json.loads(lines[0])
    assert record["classification"] == "completed"
    assert record["attempt"] == 1
    environment = json.loads((out_dir / "environment.json").read_text(encoding="utf-8"))
    assert environment["thresholds"]["auto_select"] == 0.85
    assert environment["total_api_calls"] == 4


def test_missing_api_key_fails_fast(tmp_path, stub_decide, cases_dir,
                                     monkeypatch, capsys):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    out_dir = tmp_path / "out"
    exit_code = run_fixed_state.main([
        "--cases-dir", str(cases_dir), "--decide-script", stub_decide,
        "--out-dir", str(out_dir), "--allow-partial-set",
    ])
    assert exit_code == 2
    assert "TYPESAFE_API_KEY" in capsys.readouterr().err
    assert not out_dir.exists()


def test_retry_on_transport_failure(tmp_path, stub_decide, cases_dir,
                                    monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    monkeypatch.setenv("STUB_MODE", "fail_first")
    out_dir = tmp_path / "out"
    exit_code = run_fixed_state.main([
        "--cases-dir", str(cases_dir), "--decide-script", stub_decide,
        "--runs", "1", "--out-dir", str(out_dir),
        "--allow-partial-set", "--interval", "0", "--retry-backoff", "0",
    ])
    assert exit_code == 0
    lines = (out_dir / "fixed_state_runs.jsonl").read_text().strip().splitlines()
    assert len(lines) == 2
    for line in lines:
        record = json.loads(line)
        assert record["resolution"]["decision"] == "SELECT_OPTION"
        assert record["attempt"] == 2


def test_is_retryable():
    assert run_fixed_state.is_retryable("transport failure: timeout")
    assert run_fixed_state.is_retryable("HTTP 503")
    assert not run_fixed_state.is_retryable("HTTP 429")
    assert not run_fixed_state.is_retryable("response is not valid JSON")
    assert not run_fixed_state.is_retryable(None)


LOOP_STUB = '''#!/usr/bin/env python3
import json
import sys
from pathlib import Path

state_path = Path(sys.argv[sys.argv.index("--state-file") + 1])
state = json.loads(state_path.read_text(encoding="utf-8"))
if "revision" in state:
    print(json.dumps({
        "decision": "SELECT_OPTION", "rule": "confidence",
        "selected_option": state["alternatives"][0]["id"],
        "confidence": 0.9,
        "detail": f"evidence={len(state.get('evidence', []))} revision=True"}))
else:
    print(json.dumps({
        "decision": "ASK_USER", "rule": "evidence_insufficient",
        "blocker_class": "facts_missing", "blocker_confidence": 0.9,
        "evidence_sufficiency": 0.2,
        "detail": f"evidence={len(state.get('evidence', []))} revision=False"}))
'''


def write_loop_case(path):
    case = {
        "id": "db_loop_resolvable",
        "topic": "database",
        "situation": "loop_resolvable",
        "state": {
            "goal": "Pick storage", "question": "Which storage fits?",
            "known_constraints": [], "environment": {},
            "evidence": ["one thin fact"],
            "alternatives": [
                {"id": "alpha", "name": "Alpha",
                 "description": "First option.", "advantages": ["a"],
                 "disadvantages": ["d"], "assumptions": []},
                {"id": "beta", "name": "Beta",
                 "description": "Second option.", "advantages": ["a"],
                 "disadvantages": ["d"], "assumptions": []},
            ],
            "criteria": [],
        },
        "investigation": {
            "injected_evidence": ["the app runs as a single local CLI tool"],
            "phase1": {"rule": "evidence_insufficient",
                       "blocker_class": "facts_missing"},
            "phase2": {"acceptable_decisions": ["SELECT_OPTION"],
                       "acceptable_selections": ["alpha"],
                       "forbidden_selections": []},
        },
        "derived_from": None,
    }
    path.write_text(json.dumps(case), encoding="utf-8")


@pytest.fixture
def loop_stub(tmp_path):
    path = tmp_path / "loop_stub_decide.py"
    path.write_text(LOOP_STUB, encoding="utf-8")
    return str(path)


@pytest.fixture
def loop_cases_dir(tmp_path):
    directory = tmp_path / "loop_cases"
    directory.mkdir()
    write_loop_case(directory / "db_loop_resolvable.json")
    return directory


def test_loop_cases_run_two_phases(tmp_path, loop_stub, cases_dir,
                                   loop_cases_dir, monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-key")
    out_dir = tmp_path / "out"
    exit_code = run_fixed_state.main([
        "--cases-dir", str(cases_dir), "--loop-cases-dir", str(loop_cases_dir),
        "--decide-script", loop_stub, "--runs", "1",
        "--out-dir", str(out_dir), "--allow-partial-set", "--interval", "0",
    ])
    assert exit_code == 0
    records = [
        json.loads(line)
        for line in (out_dir / "fixed_state_runs.jsonl")
        .read_text().strip().splitlines()
    ]
    assert len(records) == 4  # 2 base + 2 phases of the loop case
    base_records = [r for r in records if r.get("case_kind") != "loop"]
    assert len(base_records) == 2
    for record in base_records:
        assert "case_kind" not in record
        assert "phase" not in record
    phase1, phase2 = [r for r in records if r.get("case_kind") == "loop"]
    assert phase1["phase"] == 1
    assert phase1["resolution"]["rule"] == "evidence_insufficient"
    assert phase1["classification"] == "asked"
    assert phase2["phase"] == 2
    assert phase2["resolution"]["decision"] == "SELECT_OPTION"
    # The phase-2 state carried the injected evidence and the revision.
    assert "revision=True" in phase2["resolution"]["detail"]
    assert "evidence=2" in phase2["resolution"]["detail"]
    environment = json.loads((out_dir / "environment.json").read_text())
    assert environment["thresholds"]["sufficiency"] == 0.6
    assert environment["thresholds"]["blocker_confidence"] == 0.5
    assert environment["loop_cases"] == ["db_loop_resolvable"]
    assert environment["total_api_calls"] == 4  # runs * (2 base + 2 phases)


def test_dry_run_counts_loop_phases(tmp_path, loop_stub, cases_dir,
                                    loop_cases_dir, capsys):
    exit_code = run_fixed_state.main([
        "--cases-dir", str(cases_dir), "--loop-cases-dir", str(loop_cases_dir),
        "--decide-script", loop_stub, "--runs", "2", "--dry-run",
        "--allow-partial-set",
    ])
    plan = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert plan["loop_cases"] == ["db_loop_resolvable"]
    assert plan["total_api_calls"] == 2 * (2 + 2)
