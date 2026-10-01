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


LOOP_CASE = {
    "id": "db_loop_resolvable",
    "topic": "database",
    "situation": "loop_resolvable",
    "state": {
        "goal": "Pick storage", "question": "Which storage fits?",
        "known_constraints": [], "environment": {}, "evidence": ["e"],
        "alternatives": [mini_alternative("alpha"), mini_alternative("beta")],
        "criteria": [],
    },
    "investigation": {
        "injected_evidence": ["the app runs locally"],
        "phase1": {"rule": "evidence_insufficient",
                   "blocker_class": "facts_missing"},
        "phase2": {"acceptable_decisions": ["SELECT_OPTION"],
                   "acceptable_selections": ["alpha"],
                   "forbidden_selections": []},
    },
    "derived_from": None,
}


def loop_rec(run_index, phase, decision, rule, selected=None, blocker=None,
             classification=None):
    return {
        "case_id": "db_loop_resolvable", "run_index": run_index,
        "attempt": 1, "case_kind": "loop", "phase": phase,
        "resolution": {"decision": decision, "rule": rule,
                       "selected_option": selected, "blocker_class": blocker},
        "classification": classification or (
            "completed" if decision.startswith("SELECT") else "asked"),
        "latency_ms": 100, "exit_code": 0,
        "recorded_at": "2026-10-01T00:00:00Z",
    }


LOOP_RUNS = [
    loop_rec(1, 1, "ASK_USER", "evidence_insufficient",
             blocker="facts_missing"),
    loop_rec(1, 2, "SELECT_OPTION", "confidence", selected="alpha"),
    loop_rec(2, 1, "ASK_USER", "evidence_insufficient",
             blocker="facts_missing"),
    loop_rec(2, 2, "SELECT_OPTION", "confidence", selected="beta"),  # wrong pick
    loop_rec(3, 1, "ASK_USER", "evidence_insufficient",
             blocker="facts_missing"),
    loop_rec(3, 2, "PROVIDER_UNAVAILABLE", "provider_error",
             classification="unavailable"),
]


def prepare_with_loop(tmp_path):
    cases_dir, baseline_dir = prepare(tmp_path)
    loop_dir = tmp_path / "loop_cases"
    loop_dir.mkdir()
    (loop_dir / "a.json").write_text(json.dumps(LOOP_CASE), encoding="utf-8")
    runs_path = baseline_dir / "fixed_state_runs.jsonl"
    # prepare() writes the jsonl without a trailing newline; start a new line
    # before appending the loop records.
    prefix = "" if runs_path.read_text(encoding="utf-8").endswith("\n") else "\n"
    with runs_path.open("a", encoding="utf-8") as handle:
        handle.write(prefix + "\n".join(json.dumps(r) for r in LOOP_RUNS) + "\n")
    return cases_dir, baseline_dir, loop_dir


def test_loop_metrics_and_exclusion_from_base_metrics(tmp_path):
    cases_dir, baseline_dir, loop_dir = prepare_with_loop(tmp_path)
    exit_code = report_baseline.main([
        "--baseline-dir", str(baseline_dir), "--cases-dir", str(cases_dir),
        "--loop-cases-dir", str(loop_dir),
    ])
    assert exit_code == 0
    baseline = json.loads(
        (baseline_dir / "baseline.json").read_text(encoding="utf-8")
    )
    # Loop records must not pollute the base-case metrics.
    assert baseline["fixed_state"]["overall"]["counts"]["judged"] == 6
    loop = baseline["loop_cases"]
    assert loop["overall"] == {
        "pass": 1, "fail": 1, "unavailable": 1, "loop_pass_rate": 0.5,
    }
    summary = (baseline_dir / "SUMMARY.md").read_text(encoding="utf-8")
    assert "loop ケース" in summary
    assert "db_loop_resolvable" in summary


def test_compare_to_produces_delta_table(tmp_path):
    cases_dir, baseline_dir, _ = prepare_with_loop(tmp_path)
    previous_path = tmp_path / "previous-baseline.json"
    previous_path.write_text(json.dumps({
        "fixed_state": {
            "overall": {"unsafe_auto_selection_rate": 0.5,
                        "appropriate_ask_rate": 0.5,
                        "completion_rate": 0.5,
                        "correct_selection_rate": 0.5},
            "perturbation_stability": {
                "evidence_removed": {"pass_rate": 0.0},
            },
        },
    }), encoding="utf-8")
    exit_code = report_baseline.main([
        "--baseline-dir", str(baseline_dir), "--cases-dir", str(cases_dir),
        "--compare-to", str(previous_path),
    ])
    assert exit_code == 0
    baseline = json.loads(
        (baseline_dir / "baseline.json").read_text(encoding="utf-8")
    )
    rows = {row["metric"]: row for row in baseline["comparison"]}
    unsafe = rows["Unsafe Auto-selection Rate"]
    assert unsafe["baseline"] == 0.5
    assert unsafe["current"] == round(1 / 6, 4)
    assert unsafe["delta"] == round(round(1 / 6, 4) - 0.5, 4)
    assert rows["perturbation pass rate: evidence_removed"]["baseline"] == 0.0
    summary = (baseline_dir / "SUMMARY.md").read_text(encoding="utf-8")
    assert "baseline との比較" in summary
    assert "evidence_removed" in summary


def test_missing_loop_cases_dir_exits_2(tmp_path, capsys):
    cases_dir, baseline_dir = prepare(tmp_path)
    exit_code = report_baseline.main([
        "--baseline-dir", str(baseline_dir), "--cases-dir", str(cases_dir),
        "--loop-cases-dir", str(tmp_path / "nonexistent"),
    ])
    assert exit_code == 2
    assert "has no case files" in capsys.readouterr().err


def test_compare_to_non_object_json_exits_2(tmp_path, capsys):
    cases_dir, baseline_dir = prepare(tmp_path)
    previous_path = tmp_path / "previous-baseline.json"
    previous_path.write_text("[]", encoding="utf-8")
    exit_code = report_baseline.main([
        "--baseline-dir", str(baseline_dir), "--cases-dir", str(cases_dir),
        "--compare-to", str(previous_path),
    ])
    assert exit_code == 2
    assert "comparison baseline must be a JSON object" in capsys.readouterr().err


def test_compare_to_missing_file_exits_2(tmp_path, capsys):
    cases_dir, baseline_dir = prepare(tmp_path)
    exit_code = report_baseline.main([
        "--baseline-dir", str(baseline_dir), "--cases-dir", str(cases_dir),
        "--compare-to", str(tmp_path / "nope.json"),
    ])
    assert exit_code == 2
    assert "cannot read comparison baseline" in capsys.readouterr().err
