#!/usr/bin/env python3
"""Run fixed-state Autarch evaluation cases through decide.py and record raw runs."""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

EVALS_DIR = Path(__file__).resolve().parent
REPO_ROOT = EVALS_DIR.parent
sys.path.insert(0, str(EVALS_DIR))

import case_schema
import judging
import runner_common

DEFAULT_DECIDE = REPO_ROOT / "skills" / "autarch" / "scripts" / "decide.py"


def is_retryable(detail):
    """Transport-class provider failures that are worth retrying."""
    if not isinstance(detail, str):
        return False
    return detail.startswith("transport failure") or detail.startswith("HTTP 5")


def run_once(case, args, state_dir, state=None, phase=None):
    effective_state = case["state"] if state is None else state
    suffix = "" if phase is None else f".phase{phase}"
    state_file = Path(state_dir) / f"{case['id']}{suffix}.json"
    state_file.write_text(
        json.dumps(effective_state, ensure_ascii=False), encoding="utf-8"
    )
    command = [
        sys.executable, str(args.decide_script),
        "--state-file", str(state_file),
        "--model", args.model,
        "--auto-select", str(args.auto_select),
        "--review", str(args.review),
        "--min-gap", str(args.min_gap),
        "--human-preference", str(args.human_preference),
        "--sufficiency", str(args.sufficiency),
        "--blocker-confidence", str(args.blocker_confidence),
        "--gate-order", args.gate_order,
    ]
    if args.capture_evaluation:
        command.append("--capture-evaluation")
    started = time.perf_counter()
    completed = subprocess.run(
        command, capture_output=True, text=True, timeout=args.timeout
    )
    latency_ms = round((time.perf_counter() - started) * 1000)
    try:
        resolution = json.loads(completed.stdout)
    except json.JSONDecodeError:
        resolution = {
            "decision": "PROVIDER_UNAVAILABLE",
            "rule": "provider_error",
            "detail": f"unparseable decide.py stdout (exit {completed.returncode})",
        }
    record = {
        "case_id": case["id"],
        "run_index": None,
        "attempt": None,
        "resolution": resolution,
        "latency_ms": latency_ms,
        "exit_code": completed.returncode,
        "recorded_at": runner_common.utc_now(),
    }
    if phase is not None:
        record["case_kind"] = "loop"
        record["phase"] = phase
    return record


def run_with_retry(case, args, state_dir, state=None, phase=None):
    """Run one decide.py call with the runner's transport-retry policy."""
    for attempt in range(1, 4):
        record = run_once(case, args, state_dir, state=state, phase=phase)
        record["attempt"] = attempt
        record["classification"] = judging.classify_run(record["resolution"])
        detail = record["resolution"].get("detail")
        retryable = (
            record["classification"] == "unavailable"
            and is_retryable(detail)
            and attempt < 3
        )
        if not retryable:
            break
        time.sleep(args.retry_backoff ** attempt)
    return record


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="run_fixed_state.py",
        description="Run fixed-state eval cases through decide.py.",
    )
    parser.add_argument("--cases-dir", default=str(EVALS_DIR / "cases"))
    parser.add_argument("--out-dir")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--model", default="jev-latest")
    parser.add_argument("--cases", help="comma-separated case ids to run")
    parser.add_argument("--decide-script", default=str(DEFAULT_DECIDE))
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--retry-backoff", type=float, default=2.0)
    parser.add_argument("--auto-select", type=float, default=0.85)
    parser.add_argument("--review", type=float, default=0.60)
    parser.add_argument("--min-gap", type=float, default=0.15)
    parser.add_argument("--human-preference", type=float, default=0.70)
    parser.add_argument("--sufficiency", type=float, default=0.60)
    parser.add_argument("--blocker-confidence", type=float, default=0.50)
    parser.add_argument("--gate-order", choices=("human_first", "evidence_first"),
                        default="human_first")
    parser.add_argument("--capture-evaluation", action="store_true")
    parser.add_argument("--loop-cases-dir", default=None,
                        help="directory of two-phase loop cases to run additionally")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-partial-set", action="store_true")
    args = parser.parse_args(argv)

    try:
        cases = case_schema.load_cases(args.cases_dir)
    except case_schema.CaseError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.cases:
        wanted = {name.strip() for name in args.cases.split(",")}
        unknown = wanted - {case["id"] for case in cases}
        if unknown:
            print(f"error: unknown case ids: {', '.join(sorted(unknown))}", file=sys.stderr)
            return 2
        cases = [case for case in cases if case["id"] in wanted]
    loop_cases = []
    if args.loop_cases_dir:
        loop_dir = Path(args.loop_cases_dir)
        if not loop_dir.is_dir() or not list(loop_dir.glob("*.json")):
            print(
                f"error: --loop-cases-dir {args.loop_cases_dir} has no case files",
                file=sys.stderr,
            )
            return 2
        try:
            loop_cases = case_schema.load_loop_cases(args.loop_cases_dir)
        except case_schema.CaseError as error:
            print(f"error: {error}", file=sys.stderr)
            return 2
    if not args.allow_partial_set:
        violations = case_schema.validate_case_set(cases)
        if violations:
            print("error: incomplete or inconsistent case set:", file=sys.stderr)
            for violation in violations:
                print(f"  - {violation}", file=sys.stderr)
            return 2
    if args.dry_run:
        print(json.dumps({
            "runs_per_case": args.runs,
            "cases": [case["id"] for case in cases],
            "loop_cases": [case["id"] for case in loop_cases],
            "total_api_calls": args.runs * (len(cases) + 2 * len(loop_cases)),
        }, indent=2))
        return 0
    if not os.environ.get("TYPESAFE_API_KEY", "").strip():
        print("error: TYPESAFE_API_KEY is not set", file=sys.stderr)
        return 2

    out_dir = (
        Path(args.out_dir) if args.out_dir
        else runner_common.next_baseline_dir(
            EVALS_DIR / "results", date.today().isoformat()
        )
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    runs_path = out_dir / "fixed_state_runs.jsonl"
    started_at = runner_common.utc_now()
    print(f"writing runs to {runs_path}", file=sys.stderr)
    with tempfile.TemporaryDirectory() as state_dir:
        for case in cases:
            for run_index in range(1, args.runs + 1):
                record = run_with_retry(case, args, state_dir)
                record["run_index"] = run_index
                runner_common.append_jsonl(runs_path, record)
                print(
                    f"{case['id']} run {run_index} attempt {record['attempt']}: "
                    f"{record['resolution'].get('decision')}",
                    file=sys.stderr,
                )
                time.sleep(args.interval)
        for case in loop_cases:
            for run_index in range(1, args.runs + 1):
                for phase in (1, 2):
                    state = (
                        case["state"] if phase == 1
                        else case_schema.loop_phase2_state(case)
                    )
                    record = run_with_retry(
                        case, args, state_dir, state=state, phase=phase
                    )
                    record["run_index"] = run_index
                    runner_common.append_jsonl(runs_path, record)
                    print(
                        f"{case['id']} run {run_index} phase {phase}: "
                        f"{record['resolution'].get('decision')}",
                        file=sys.stderr,
                    )
                    time.sleep(args.interval)
    environment = {
        "runner": "run_fixed_state.py",
        "model": args.model,
        "gate_order": args.gate_order,
        "capture_evaluation": args.capture_evaluation,
        "thresholds": {
            "auto_select": args.auto_select,
            "review": args.review,
            "min_gap": args.min_gap,
            "human_preference": args.human_preference,
            "sufficiency": args.sufficiency,
            "blocker_confidence": args.blocker_confidence,
        },
        "decide_script": str(args.decide_script),
        "runs_per_case": args.runs,
        "started_at": started_at,
        "finished_at": runner_common.utc_now(),
        "total_api_calls": args.runs * (len(cases) + 2 * len(loop_cases)),
    }
    if loop_cases:
        environment["loop_cases"] = [case["id"] for case in loop_cases]
    (out_dir / "environment.json").write_text(
        json.dumps(environment, indent=2), encoding="utf-8"
    )
    print(str(out_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
