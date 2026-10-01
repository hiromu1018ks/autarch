import json
import stat

import pytest

import run_full_flow

STUB_CLAUDE = '''#!/usr/bin/env python3
import os
import sys
from pathlib import Path

stdin_text = sys.stdin.read()
capture = os.environ.get("STUB_CAPTURE_DIR")
if capture:
    Path(capture, "stub_stdin.txt").write_text(stdin_text, encoding="utf-8")
canned = os.environ.get("STUB_CANNED_DIR")
if canned:
    for name in ("autarch-state.json", "autarch-resolution.json"):
        target = Path.cwd() / name
        if not target.exists():
            source = Path(canned) / name
            target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
print("stub agent finished")
'''

CANNED_STATE = {
    "goal": "Pick storage",
    "question": "Which storage approach fits the notes CLI?",
    "known_constraints": ["works offline"],
    "environment": {},
    "evidence": ["README says offline single user"],
    "alternatives": [
        {"id": "sqlite", "name": "SQLite",
         "description": "embedded single-file database", "advantages": ["offline"],
         "disadvantages": ["single host"], "assumptions": []},
        {"id": "postgres", "name": "PostgreSQL",
         "description": "client-server database", "advantages": ["concurrent access"],
         "disadvantages": ["server process"], "assumptions": []},
    ],
    "criteria": [],
}

CANNED_RESOLUTION = {
    "decision": "SELECT_OPTION",
    "rule": "confidence",
    "selected_option": "sqlite",
    "confidence": 0.9,
    "probabilities": {"sqlite": 0.9, "postgres": 0.1},
    "human_preference_probability": 0.1,
}

EXPECTATIONS = {
    "situation": "constraint_clear",
    "required_alternatives": [["sqlite"]],
    "forbidden_alternatives": [],
    "acceptable_decisions": ["SELECT_OPTION", "SELECT_OPTION_WITH_CAUTION"],
    "acceptable_selections": [["sqlite"]],
    "requires_human_preference": False,
}

PROMPT = """Decide storage.
1. Run /autarch.
2. Save the state to ./autarch-state.json.
3. Save decide.py stdout to ./autarch-resolution.json.
"""


def make_scenario(root, name, with_expectations=True):
    scenario = root / name
    fixture = scenario / "fixture"
    fixture.mkdir(parents=True)
    (fixture / "README.md").write_text("# sample repo\n", encoding="utf-8")
    (scenario / "prompt.md").write_text(PROMPT, encoding="utf-8")
    if with_expectations:
        (scenario / "expectations.json").write_text(
            json.dumps(EXPECTATIONS), encoding="utf-8"
        )
    return scenario


@pytest.fixture
def stub_claude(tmp_path):
    path = tmp_path / "stub_claude.py"
    path.write_text(STUB_CLAUDE, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return str(path)


@pytest.fixture
def canned_dir(tmp_path):
    directory = tmp_path / "canned"
    directory.mkdir()
    (directory / "autarch-state.json").write_text(
        json.dumps(CANNED_STATE), encoding="utf-8"
    )
    (directory / "autarch-resolution.json").write_text(
        json.dumps(CANNED_RESOLUTION), encoding="utf-8"
    )
    return str(directory)


def test_prepare_workdir_copies_fixture_and_links_skill(tmp_path):
    scenario = make_scenario(tmp_path, "database")
    workdir = run_full_flow.prepare_workdir(scenario, tmp_path / "work")
    assert (workdir / "README.md").exists()
    link = workdir / ".claude" / "skills" / "autarch"
    assert link.is_symlink()
    assert (link / "SKILL.md").exists()


def test_full_flow_run_records_verdict_and_artifacts(
        tmp_path, stub_claude, canned_dir, monkeypatch):
    monkeypatch.setenv("STUB_CANNED_DIR", canned_dir)
    scenarios = tmp_path / "scenarios"
    make_scenario(scenarios, "database")
    out_dir = tmp_path / "out"
    exit_code = run_full_flow.main([
        "--scenarios-dir", str(scenarios), "--out-dir", str(out_dir),
        "--agent-model", "stub-model", "--claude-bin", stub_claude,
    ])
    assert exit_code == 0
    record = json.loads(
        (out_dir / "full_flow_runs.jsonl").read_text().strip()
    )
    assert record["status"] == "ok"
    assert record["agent_model"] == "stub-model"
    assert record["verdict"] == {
        "coverage": True, "forbidden_avoided": True, "decision_ok": True,
        "state_valid": True, "selected_group": "sqlite",
    }
    artifacts = out_dir / "full_flow" / "database"
    assert (artifacts / "autarch-state.json").exists()
    assert (artifacts / "autarch-resolution.json").exists()
    assert (artifacts / "agent_output.md").exists()
    environment = json.loads((out_dir / "environment.json").read_text())
    assert environment["full_flow_agent_model"] == "stub-model"


def test_missing_artifacts_recorded_as_failure(
        tmp_path, stub_claude, monkeypatch):
    monkeypatch.delenv("STUB_CANNED_DIR", raising=False)
    scenarios = tmp_path / "scenarios"
    make_scenario(scenarios, "database")
    make_scenario(scenarios, "deployment")
    out_dir = tmp_path / "out"
    exit_code = run_full_flow.main([
        "--scenarios-dir", str(scenarios), "--out-dir", str(out_dir),
        "--agent-model", "stub-model", "--claude-bin", stub_claude,
    ])
    assert exit_code == 0
    lines = (out_dir / "full_flow_runs.jsonl").read_text().strip().splitlines()
    assert len(lines) == 2
    for line in lines:
        record = json.loads(line)
        assert record["status"] == "failed"
        assert "missing artifacts" in record["reason"]


def test_refuses_to_overwrite_existing_runs(tmp_path, stub_claude, canned_dir,
                                            monkeypatch):
    monkeypatch.setenv("STUB_CANNED_DIR", canned_dir)
    scenarios = tmp_path / "scenarios"
    make_scenario(scenarios, "database")
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "full_flow_runs.jsonl").write_text("{}\n", encoding="utf-8")
    exit_code = run_full_flow.main([
        "--scenarios-dir", str(scenarios), "--out-dir", str(out_dir),
        "--agent-model", "stub-model", "--claude-bin", stub_claude,
    ])
    assert exit_code == 2


def test_prompt_is_passed_via_stdin(tmp_path, stub_claude, canned_dir, monkeypatch):
    monkeypatch.setenv("STUB_CANNED_DIR", canned_dir)
    capture = tmp_path / "capture"
    capture.mkdir()
    monkeypatch.setenv("STUB_CAPTURE_DIR", str(capture))
    scenarios = tmp_path / "scenarios"
    make_scenario(scenarios, "database")
    out_dir = tmp_path / "out"
    exit_code = run_full_flow.main([
        "--scenarios-dir", str(scenarios), "--out-dir", str(out_dir),
        "--agent-model", "stub-model", "--claude-bin", stub_claude,
    ])
    assert exit_code == 0
    # The prompt must reach the agent via stdin, not as a trailing positional
    # argument (variadic flags like --allowedTools swallow positionals).
    assert "Decide storage." in (capture / "stub_stdin.txt").read_text()


def test_provider_unavailable_scenario_is_not_judged(
        tmp_path, stub_claude, monkeypatch):
    canned = tmp_path / "canned"
    canned.mkdir()
    (canned / "autarch-state.json").write_text(
        json.dumps(CANNED_STATE), encoding="utf-8"
    )
    (canned / "autarch-resolution.json").write_text(
        json.dumps({"decision": "PROVIDER_UNAVAILABLE", "rule": "provider_error",
                    "detail": "HTTP 503"}),
        encoding="utf-8",
    )
    monkeypatch.setenv("STUB_CANNED_DIR", str(canned))
    scenarios = tmp_path / "scenarios"
    make_scenario(scenarios, "database")
    out_dir = tmp_path / "out"
    exit_code = run_full_flow.main([
        "--scenarios-dir", str(scenarios), "--out-dir", str(out_dir),
        "--agent-model", "stub-model", "--claude-bin", stub_claude,
    ])
    assert exit_code == 0
    record = json.loads((out_dir / "full_flow_runs.jsonl").read_text().strip())
    assert record["status"] == "unavailable"
    assert record["verdict"] is None
    assert "HTTP 503" in record["reason"]


def test_dry_run_lists_scenarios(tmp_path, stub_claude, capsys):
    scenarios = tmp_path / "scenarios"
    make_scenario(scenarios, "database")
    exit_code = run_full_flow.main([
        "--scenarios-dir", str(scenarios), "--dry-run",
        "--agent-model", "stub-model",
    ])
    plan = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert plan == {"agent_model": "stub-model", "scenarios": ["database"],
                    "agent_runs": 1}
