#!/usr/bin/env python3
"""Run full-flow Autarch evaluation scenarios with a headless agent."""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

EVALS_DIR = Path(__file__).resolve().parent
REPO_ROOT = EVALS_DIR.parent
sys.path.insert(0, str(EVALS_DIR))
sys.path.insert(0, str(REPO_ROOT / "skills" / "autarch" / "scripts"))

import case_schema
import decide
import judging
import runner_common

SKILLS_DIR = REPO_ROOT / "skills" / "autarch"


def prepare_workdir(scenario_dir: Path, work_root: Path) -> Path:
    """Copy the fixture and link the skill so /autarch resolves inside it."""
    workdir = work_root / scenario_dir.name
    shutil.copytree(scenario_dir / "fixture", workdir)
    skills = workdir / ".claude" / "skills"
    skills.mkdir(parents=True, exist_ok=True)
    os.symlink(SKILLS_DIR, skills / "autarch")
    return workdir


def _load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def run_scenario(scenario_dir: Path, args, out_dir: Path) -> dict:
    expectations = _load_json(scenario_dir / "expectations.json")
    errors = case_schema.validate_scenario_expectations(expectations or {})
    prompt = (scenario_dir / "prompt.md").read_text(encoding="utf-8")
    started = time.perf_counter()
    with tempfile.TemporaryDirectory() as tmp:
        workdir = prepare_workdir(scenario_dir, Path(tmp))
        command = [
            args.claude_bin, "-p",
            "--model", args.agent_model,
            "--permission-mode", "acceptEdits",
            "--allowedTools", "Bash(python3:*)",
            prompt,
        ]
        completed = subprocess.run(
            command, capture_output=True, text=True,
            timeout=args.timeout, cwd=workdir,
        )
        duration_s = round(time.perf_counter() - started, 1)
        state = _load_json(workdir / "autarch-state.json")
        resolution = _load_json(workdir / "autarch-resolution.json")
        scenario_out = out_dir / "full_flow" / scenario_dir.name
        scenario_out.mkdir(parents=True, exist_ok=True)
        for name in ("autarch-state.json", "autarch-resolution.json"):
            source = workdir / name
            if source.exists():
                shutil.copy(source, scenario_out / name)
        (scenario_out / "agent_output.md").write_text(
            completed.stdout or "", encoding="utf-8"
        )
    record = {
        "scenario": scenario_dir.name,
        "situation": (expectations or {}).get("situation"),
        "status": "ok",
        "reason": None,
        "verdict": None,
        "agent_model": args.agent_model,
        "claude_exit_code": completed.returncode,
        "duration_s": duration_s,
        "recorded_at": runner_common.utc_now(),
    }
    if errors:
        record["status"] = "failed"
        record["reason"] = "invalid expectations: " + "; ".join(errors)
    elif state is None or resolution is None:
        missing = [
            name for name, value in
            (("autarch-state.json", state), ("autarch-resolution.json", resolution))
            if value is None
        ]
        record["status"] = "failed"
        record["reason"] = "missing artifacts: " + ", ".join(missing)
    else:
        record["verdict"] = judging.judge_full_flow(
            state, decide.validate_state(state), resolution, expectations
        )
    return record


def _record_environment(out_dir: Path, agent_model: str) -> None:
    path = out_dir / "environment.json"
    environment = _load_json(path) or {}
    environment["full_flow_agent_model"] = agent_model
    environment["full_flow_finished_at"] = runner_common.utc_now()
    path.write_text(json.dumps(environment, indent=2), encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="run_full_flow.py",
        description="Run full-flow eval scenarios with a headless agent.",
    )
    parser.add_argument("--scenarios-dir", default=str(EVALS_DIR / "scenarios"))
    parser.add_argument("--out-dir")
    parser.add_argument("--scenario", help="run a single scenario by directory name")
    parser.add_argument("--agent-model", required=True)
    parser.add_argument("--claude-bin", default="claude")
    parser.add_argument("--timeout", type=float, default=3600.0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    scenarios_root = Path(args.scenarios_dir)
    scenario_dirs = sorted(p for p in scenarios_root.iterdir() if p.is_dir())
    if args.scenario:
        scenario_dirs = [p for p in scenario_dirs if p.name == args.scenario]
        if not scenario_dirs:
            print(f"error: unknown scenario {args.scenario}", file=sys.stderr)
            return 2
    if not scenario_dirs:
        print("error: no scenarios found", file=sys.stderr)
        return 2
    if args.dry_run:
        print(json.dumps({
            "agent_model": args.agent_model,
            "scenarios": [p.name for p in scenario_dirs],
            "agent_runs": len(scenario_dirs),
        }, indent=2))
        return 0
    out_dir = (
        Path(args.out_dir) if args.out_dir
        else runner_common.next_baseline_dir(
            EVALS_DIR / "results", date.today().isoformat()
        )
    )
    runs_path = out_dir / "full_flow_runs.jsonl"
    if runs_path.exists():
        print(f"error: {runs_path} already exists; use a fresh baseline dir",
              file=sys.stderr)
        return 2
    out_dir.mkdir(parents=True, exist_ok=True)
    for scenario_dir in scenario_dirs:
        record = run_scenario(scenario_dir, args, out_dir)
        runner_common.append_jsonl(runs_path, record)
        print(
            f"{record['scenario']}: {record['status']}"
            + (f" ({record['reason']})" if record["reason"] else ""),
            file=sys.stderr,
        )
    _record_environment(out_dir, args.agent_model)
    print(str(out_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
