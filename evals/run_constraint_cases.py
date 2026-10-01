#!/usr/bin/env python3
"""Run the independent hard-constraint evaluation track."""

import argparse
import json
import os
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

EVALS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(EVALS_DIR))

import constraint_cases
import run_fixed_state
import runner_common


def _positive(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("runs must be positive")
    return number


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases-dir", default=str(EVALS_DIR / "cases_constraints"))
    parser.add_argument("--out-dir")
    parser.add_argument("--runs", type=_positive, default=3)
    parser.add_argument("--decide-script", default=str(run_fixed_state.DEFAULT_DECIDE))
    parser.add_argument("--model", default="jev-latest")
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--retry-backoff", type=float, default=2.0)
    for name, default in (("auto-select", 0.85), ("review", 0.60), ("min-gap", 0.15),
                          ("human-preference", 0.70), ("sufficiency", 0.60),
                          ("blocker-confidence", 0.50)):
        parser.add_argument(f"--{name}", type=constraint_cases.decide._threshold_argument,
                            default=default)
    parser.add_argument("--gate-order", choices=("human_first", "evidence_first"),
                        default="human_first")
    parser.add_argument("--capture-evaluation", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        cases = constraint_cases.load_constraint_cases(Path(args.cases_dir))
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    total = args.runs * sum(len(c["phases"]) for c in cases)
    if args.dry_run:
        print(json.dumps({"cases": [c["id"] for c in cases],
                          "runs_per_case": args.runs, "total_decide_calls": total}, indent=2))
        return 0
    if not os.environ.get("TYPESAFE_API_KEY", "").strip():
        print("error: TYPESAFE_API_KEY is not set", file=sys.stderr)
        return 2
    out_dir = (Path(args.out_dir) if args.out_dir else
               runner_common.next_baseline_dir(EVALS_DIR / "results", "constraints-" + date.today().isoformat()))
    if out_dir.is_dir() and any(out_dir.iterdir()):
        print(f"error: {out_dir} is not empty; choose a fresh out-dir", file=sys.stderr)
        return 2
    out_dir.mkdir(parents=True, exist_ok=True)
    runs_path = out_dir / "constraint_runs.jsonl"
    started = runner_common.utc_now()
    records = []
    with tempfile.TemporaryDirectory() as state_dir:
        for case in cases:
            for index in range(1, args.runs + 1):
                for phase in case["phases"]:
                    number = phase["phase"]
                    state = case["state"] if number == 1 else constraint_cases.constraint_phase2_state(case)
                    record = run_fixed_state.run_with_retry(case, args, state_dir, state=state, phase=number)
                    # Shared run_once labels any phased run as loop; this track is independent.
                    record.update(case_kind="constraints", phase=number, case_id=case["id"], run_index=index)
                    runner_common.append_jsonl(runs_path, record)
                    records.append(record)
                    print(f"{case['id']} run {index} phase {number}: "
                          f"{record['resolution'].get('decision')}", file=sys.stderr)
                    time.sleep(args.interval)
    summary = constraint_cases.constraint_metrics(cases, records)
    (out_dir / "constraint_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    environment = {
        "runner": "run_constraint_cases.py", "case_kind": "constraints",
        "cases": [c["id"] for c in cases], "model": args.model,
        "gate_order": args.gate_order, "capture_evaluation": args.capture_evaluation,
        "thresholds": {name: getattr(args, name) for name in (
            "auto_select", "review", "min_gap", "human_preference", "sufficiency", "blocker_confidence")},
        "decide_script": str(args.decide_script), "runs_per_case": args.runs,
        "started_at": started, "finished_at": runner_common.utc_now(),
        "total_decide_calls": total,
    }
    (out_dir / "environment.json").write_text(json.dumps(environment, indent=2), encoding="utf-8")
    print(str(out_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
