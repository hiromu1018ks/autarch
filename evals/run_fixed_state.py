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


def run_once(case, args, state_dir):
    state_file = Path(state_dir) / f"{case['id']}.json"
    state_file.write_text(json.dumps(case["state"], ensure_ascii=False), encoding="utf-8")
    command = [
        sys.executable, str(args.decide_script),
        "--state-file", str(state_file),
        "--model", args.model,
        "--auto-select", str(args.auto_select),
        "--review", str(args.review),
        "--min-gap", str(args.min_gap),
        "--human-preference", str(args.human_preference),
    ]
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
    return {
        "case_id": case["id"],
        "run_index": None,
        "attempt": None,
        "resolution": resolution,
        "latency_ms": latency_ms,
        "exit_code": completed.returncode,
        "recorded_at": runner_common.utc_now(),
    }


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
            "total_api_calls": args.runs * len(cases),
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
                for attempt in range(1, 4):
                    record = run_once(case, args, state_dir)
                    record["run_index"] = run_index
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
                runner_common.append_jsonl(runs_path, record)
                print(
                    f"{case['id']} run {run_index} attempt {record['attempt']}: "
                    f"{record['resolution'].get('decision')}",
                    file=sys.stderr,
                )
                time.sleep(args.interval)
    environment = {
        "runner": "run_fixed_state.py",
        "model": args.model,
        "thresholds": {
            "auto_select": args.auto_select,
            "review": args.review,
            "min_gap": args.min_gap,
            "human_preference": args.human_preference,
        },
        "decide_script": str(args.decide_script),
        "runs_per_case": args.runs,
        "started_at": started_at,
        "finished_at": runner_common.utc_now(),
        "total_api_calls": args.runs * len(cases),
    }
    (out_dir / "environment.json").write_text(
        json.dumps(environment, indent=2), encoding="utf-8"
    )
    print(str(out_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
