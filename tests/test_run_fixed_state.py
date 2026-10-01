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
