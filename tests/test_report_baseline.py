import json

import report_baseline


def mini_alternative(option_id):
    return {
        "id": option_id,
        "name": option_id.title(),
        "description": f"The {option_id} option.",
        "advantages": ["a"],
        "disadvantages": ["d"],
        "assumptions": [],
    }


CASE_CLEAR = {
    "id": "db_constraint_clear",
    "topic": "database",
    "situation": "constraint_clear",
    "state": {
        "goal": "Pick storage", "question": "Which storage fits?",
        "known_constraints": [], "environment": {}, "evidence": ["e"],
        "alternatives": [mini_alternative("sqlite"), mini_alternative("postgres")],
        "criteria": [],
    },
    "expectations": {
        "acceptable_decisions": ["SELECT_OPTION", "SELECT_OPTION_WITH_CAUTION"],
        "acceptable_selections": ["sqlite"],
        "forbidden_selections": [],
    },
    "derived_from": None,
}

CASE_ASK = {
    "id": "db_info_missing",
    "topic": "database",
    "situation": "info_missing",
    "state": {
        "goal": "Pick storage", "question": "Which storage fits?",
        "known_constraints": [], "environment": {}, "evidence": ["e"],
        "alternatives": [mini_alternative("sqlite"), mini_alternative("postgres")],
        "criteria": [],
    },
    "expectations": {"acceptable_decisions": ["ASK_USER"],
                     "acceptable_selections": [], "forbidden_selections": []},
    "derived_from": None,
}


def rec(case_id, run_index, decision, selected, confidence):
    return {
        "case_id": case_id,
        "run_index": run_index,
        "attempt": 1,
        "resolution": {"decision": decision, "selected_option": selected,
                       "confidence": confidence},
        "classification": ("completed" if decision.startswith("SELECT") else "asked"),
        "latency_ms": 100,
        "exit_code": 0,
        "recorded_at": "2026-10-01T00:00:00Z",
    }


def prepare(tmp_path):
    cases_dir = tmp_path / "cases"
    cases_dir.mkdir()
    (cases_dir / "a.json").write_text(json.dumps(CASE_CLEAR), encoding="utf-8")
    (cases_dir / "b.json").write_text(json.dumps(CASE_ASK), encoding="utf-8")
    baseline_dir = tmp_path / "baseline"
    baseline_dir.mkdir()
    (baseline_dir / "environment.json").write_text(json.dumps({
        "model": "jev-latest",
        "thresholds": {"auto_select": 0.85, "review": 0.6, "min_gap": 0.15,
                       "human_preference": 0.7},
        "runs_per_case": 3,
        "total_api_calls": 6,
        "started_at": "2026-10-01T00:00:00Z",
        "finished_at": "2026-10-01T01:00:00Z",
    }), encoding="utf-8")
    records = [
        rec("db_constraint_clear", 1, "SELECT_OPTION", "sqlite", 0.9),
        rec("db_constraint_clear", 2, "SELECT_OPTION", "sqlite", 0.88),
        rec("db_constraint_clear", 3, "ASK_USER", None, None),
        rec("db_info_missing", 1, "ASK_USER", None, None),
        rec("db_info_missing", 2, "ASK_USER", None, None),
        rec("db_info_missing", 3, "SELECT_OPTION", "postgres", 0.9),
    ]
    (baseline_dir / "fixed_state_runs.jsonl").write_text(
        "\n".join(json.dumps(r) for r in records), encoding="utf-8"
    )
    (baseline_dir / "full_flow_runs.jsonl").write_text(json.dumps({
        "scenario": "database",
        "status": "ok",
        "verdict": {"coverage": True, "forbidden_avoided": True, "decision_ok": True,
                    "state_valid": True, "selected_group": "sqlite"},
    }), encoding="utf-8")
    return cases_dir, baseline_dir


def test_report_end_to_end(tmp_path, capsys):
    cases_dir, baseline_dir = prepare(tmp_path)
    exit_code = report_baseline.main([
        "--baseline-dir", str(baseline_dir), "--cases-dir", str(cases_dir),
    ])
    assert exit_code == 0
    baseline = json.loads((baseline_dir / "baseline.json").read_text(encoding="utf-8"))
    assert baseline["fixed_state"]["overall"]["unsafe_auto_selection_rate"] == round(1 / 6, 4)
    assert baseline["fixed_state"]["overall"]["counts"]["judged"] == 6
    assert baseline["full_flow"]["rates"]["decision_ok"] == 1.0
    summary = (baseline_dir / "SUMMARY.md").read_text(encoding="utf-8")
    assert "## 固定 state トラック" in summary
    assert "db_constraint_clear" in summary
    assert "| database | True | True | True | True | sqlite |" in summary
    assert "撹乱安定性" in summary


def test_report_preserves_handwritten_notes(tmp_path):
    cases_dir, baseline_dir = prepare(tmp_path)
    (baseline_dir / "notes.md").write_text(
        "- 手書きメモ: full-flow は初回失敗後に再実行した。\n", encoding="utf-8"
    )
    exit_code = report_baseline.main([
        "--baseline-dir", str(baseline_dir), "--cases-dir", str(cases_dir),
    ])
    assert exit_code == 0
    summary = (baseline_dir / "SUMMARY.md").read_text(encoding="utf-8")
    assert "手書きメモ: full-flow は初回失敗後に再実行した。" in summary
    assert "## 留保" in summary


def test_render_summary_marks_na_for_missing_rates():
    baseline = report_baseline.compute(
        [CASE_CLEAR, CASE_ASK], [], [],
        {"thresholds": {"auto_select": 0.85}, "model": "jev-latest"},
    )
    summary = report_baseline.render_summary(baseline)
    assert "N/A" in summary
