#!/usr/bin/env python3
"""Aggregate a baseline directory into baseline.json and a Japanese SUMMARY.md."""

import argparse
import json
import sys
from pathlib import Path

EVALS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(EVALS_DIR))

import case_schema
import judging
import runner_common

METRIC_LABELS = (
    ("Decision Completion Rate", "completion_rate"),
    ("Correct Selection Rate", "correct_selection_rate"),
    ("Unsafe Auto-selection Rate", "unsafe_auto_selection_rate"),
    ("Appropriate Ask Rate", "appropriate_ask_rate"),
)


def load_jsonl(path):
    records = []
    path = Path(path)
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(json.loads(line))
    return records


def _ratio(numerator, denominator):
    return round(numerator / denominator, 4) if denominator else None


def _phase_label(record):
    if record is None:
        return "missing"
    resolution = record["resolution"]
    return f"{resolution.get('decision')}/{resolution.get('rule')}"


def _loop_verdict(case, phase_records):
    if any(
        record is None or record["classification"] == "unavailable"
        for record in phase_records.values()
    ):
        return "unavailable"
    expectations = case["investigation"]
    res1 = phase_records[1]["resolution"]
    phase1 = expectations["phase1"]
    phase1_ok = (
        res1.get("decision") == "ASK_USER"
        and res1.get("rule") == phase1["rule"]
        and res1.get("blocker_class") == phase1["blocker_class"]
    )
    res2 = phase_records[2]["resolution"]
    phase2 = expectations["phase2"]
    phase2_ok = res2.get("decision") in phase2.get("acceptable_decisions", [])
    if phase2_ok and res2.get("decision") in (
        "SELECT_OPTION", "SELECT_OPTION_WITH_CAUTION"
    ):
        phase2_ok = (
            res2.get("selected_option")
            in phase2.get("acceptable_selections", [])
        )
    return "pass" if phase1_ok and phase2_ok else "fail"


def loop_metrics(cases, runs):
    """Aggregate two-phase loop runs. Loop pass = phase1 AND phase2 ok."""
    loop_records = [run for run in runs if run.get("case_kind") == "loop"]
    per_case = []
    counts = {"pass": 0, "fail": 0, "unavailable": 0}
    for case in cases:
        entries = []
        run_indexes = sorted({
            run["run_index"] for run in loop_records
            if run["case_id"] == case["id"]
        })
        for run_index in run_indexes:
            phase_records = {}
            for phase in (1, 2):
                candidates = [
                    run for run in loop_records
                    if run["case_id"] == case["id"]
                    and run["run_index"] == run_index
                    and run.get("phase") == phase
                ]
                phase_records[phase] = candidates[-1] if candidates else None
            verdict = _loop_verdict(case, phase_records)
            counts[verdict] += 1
            entries.append({
                "run_index": run_index,
                "phase1": _phase_label(phase_records[1]),
                "phase2": _phase_label(phase_records[2]),
                "verdict": verdict,
            })
        per_case.append({
            "case_id": case["id"],
            "topic": case["topic"],
            "runs": entries,
        })
    return {
        "overall": {
            **counts,
            "loop_pass_rate": _ratio(counts["pass"],
                                     counts["pass"] + counts["fail"]),
        },
        "per_case": per_case,
    }


def comparison_rows(current, previous):
    """Comparable metric rows (base track) between two baseline documents."""
    rows = []
    cur_fixed = current["fixed_state"]["overall"]
    prev_fixed = (previous.get("fixed_state") or {}).get("overall") or {}
    for label, key in METRIC_LABELS:
        rows.append({
            "metric": label,
            "baseline": prev_fixed.get(key),
            "current": cur_fixed.get(key),
        })
    cur_pert = current["fixed_state"].get("perturbation_stability") or {}
    prev_pert = (
        (previous.get("fixed_state") or {}).get("perturbation_stability") or {}
    )
    for perturbation in sorted(set(cur_pert) | set(prev_pert)):
        rows.append({
            "metric": f"perturbation pass rate: {perturbation}",
            "baseline": (prev_pert.get(perturbation) or {}).get("pass_rate"),
            "current": (cur_pert.get(perturbation) or {}).get("pass_rate"),
        })
    for row in rows:
        if (isinstance(row["baseline"], (int, float))
                and isinstance(row["current"], (int, float))):
            row["delta"] = round(row["current"] - row["baseline"], 4)
        else:
            row["delta"] = None
    return rows


def compute(cases, fixed_runs, full_runs, environment, loop_cases=None):
    base_runs = [run for run in fixed_runs if run.get("case_kind") != "loop"]
    per_case = []
    for case in cases:
        entries = [
            {
                "run_index": run["run_index"],
                "classification": run["classification"],
                "selected_option": run["resolution"].get("selected_option"),
                "confidence": run["resolution"].get("confidence"),
            }
            for run in base_runs if run["case_id"] == case["id"]
        ]
        per_case.append({
            "case_id": case["id"],
            "topic": case["topic"],
            "situation": case["situation"],
            "derived_from": case.get("derived_from"),
            "runs": entries,
        })
    auto_select = (environment.get("thresholds") or {}).get("auto_select", 0.85)
    judged = [s for s in full_runs if s.get("verdict")]

    def scenario_rate(key):
        if not judged:
            return None
        return round(sum(1 for s in judged if s["verdict"].get(key)) / len(judged), 4)

    result = {
        "generated_at": runner_common.utc_now(),
        "environment": environment,
        "fixed_state": {
            "overall": judging.fixed_state_metrics(cases, base_runs),
            "by_run_index": judging.aggregate_by_run_index(cases, base_runs),
            "perturbation_stability": judging.perturbation_stability(
                cases, base_runs, auto_select
            ),
            "per_case": per_case,
        },
        "full_flow": {
            "per_scenario": full_runs,
            "rates": {
                key: scenario_rate(key)
                for key in ("coverage", "forbidden_avoided", "decision_ok", "state_valid")
            },
        },
    }
    if loop_cases:
        result["loop_cases"] = loop_metrics(loop_cases, fixed_runs)
    return result


def _fmt(value):
    return "N/A" if value is None else f"{value:.2%}" if isinstance(value, float) else str(value)


def render_summary(baseline, notes=""):
    """Render SUMMARY.md; `notes` (from the baseline dir's notes.md) is appended
    to the caveats section so hand-written provenance survives regeneration."""
    environment = baseline["environment"]
    fixed = baseline["fixed_state"]
    full = baseline["full_flow"]
    counts = fixed["overall"]["counts"]
    thresholds = environment.get("thresholds") or {}
    if thresholds:
        threshold_line = (
            f"| 閾値 | auto_select={thresholds.get('auto_select')}, "
            f"review={thresholds.get('review')}, min_gap={thresholds.get('min_gap')}, "
            f"human_preference={thresholds.get('human_preference')} |"
        )
    else:
        threshold_line = "| 閾値 | (未記録) |"
    lines = [
        "# Autarch 現行版 baseline",
        "",
        "## 実行環境",
        "",
        "| 項目 | 値 |",
        "|---|---|",
        f"| Jev model | {environment.get('model')} |",
        threshold_line,
        f"| 1ケースあたり実行回数 | {environment.get('runs_per_case')} |",
        f"| Jev 実行回数 | {environment.get('total_api_calls')} |",
        f"| 実行期間 | {environment.get('started_at')} 〜 {environment.get('finished_at')} |",
    ]
    if environment.get("full_flow_agent_model"):
        lines.append(f"| full-flow agent model | {environment['full_flow_agent_model']} |")
    lines += [
        "",
        "## 固定 state トラック",
        "",
        f"judged {counts['judged']} 実行(unavailable {counts['unavailable']} 件・"
        f"invalid {counts['invalid']} 件は分母から除外)。",
        "",
        "| 指標 | 全体 | 平均(run別) | 範囲(run別) |",
        "|---|---|---|---|",
    ]
    for label, key in METRIC_LABELS:
        aggregate = fixed["by_run_index"][key]
        lines.append(
            f"| {label} | {_fmt(fixed['overall'][key])} | {_fmt(aggregate['mean'])} | "
            f"{_fmt(aggregate['min'])}–{_fmt(aggregate['max'])} |"
        )
    lines += [
        "",
        "### 撹乱安定性",
        "",
        "| perturbation | pass | fail | inconclusive | pass率 |",
        "|---|---|---|---|---|",
    ]
    for perturbation, entry in sorted(fixed["perturbation_stability"].items()):
        lines.append(
            f"| {perturbation} | {entry['pass']} | {entry['fail']} | "
            f"{entry['inconclusive']} | {_fmt(entry['pass_rate'])} |"
        )
    lines += [
        "",
        "### ケース別結果",
        "",
        "| case | run | classification | selected | confidence |",
        "|---|---|---|---|---|",
    ]
    for case in fixed["per_case"]:
        for run in case["runs"]:
            lines.append(
                f"| {case['case_id']} | {run['run_index']} | {run['classification']} | "
                f"{run['selected_option']} | {run['confidence']} |"
            )
    if "loop_cases" in baseline:
        loop = baseline["loop_cases"]
        overall = loop["overall"]
        lines += [
            "",
            "## loop ケース(2段階)",
            "",
            f"pass {overall['pass']} / fail {overall['fail']}"
            f"(unavailable {overall['unavailable']} は分母から除外)。",
            "",
            "| case | run | phase1 | phase2 | 判定 |",
            "|---|---|---|---|---|",
        ]
        for case in loop["per_case"]:
            for run in case["runs"]:
                lines.append(
                    f"| {case['case_id']} | {run['run_index']} | "
                    f"{run['phase1']} | {run['phase2']} | {run['verdict']} |"
                )
    lines += [
        "",
        "## full-flow トラック",
        "",
        "| scenario | coverage | forbidden回避 | 判定妥当 | state妥当 | 選択 |",
        "|---|---|---|---|---|---|",
    ]
    for scenario in full["per_scenario"]:
        verdict = scenario.get("verdict")
        if not verdict:
            lines.append(
                f"| {scenario.get('scenario')} | 失敗({scenario.get('reason')}) | | | | |"
            )
            continue
        lines.append(
            f"| {scenario.get('scenario')} | {verdict['coverage']} | "
            f"{verdict['forbidden_avoided']} | {verdict['decision_ok']} | "
            f"{verdict['state_valid']} | {verdict.get('selected_group')} |"
        )
    rates = full["rates"]
    lines += [
        "",
        f"coverage率 {_fmt(rates['coverage'])} / forbidden回避率 "
        f"{_fmt(rates['forbidden_avoided'])} / 判定妥当率 {_fmt(rates['decision_ok'])} / "
        f"state妥当率 {_fmt(rates['state_valid'])}",
    ]
    if "comparison" in baseline:
        lines += [
            "",
            "## baseline との比較",
            "",
            "| 指標 | baseline | 今回 | 差分 |",
            "|---|---|---|---|",
        ]
        for row in baseline["comparison"]:
            lines.append(
                f"| {row['metric']} | {_fmt(row['baseline'])} | "
                f"{_fmt(row['current'])} | {_fmt(row['delta'])} |"
            )
    lines += [
        "",
        "## 留保",
        "",
        "- `evidence_removed` の合格基準(ASK_USER、または正解圏内かつ confidence < "
        "auto_select)は暫定。本 baseline の confidence 分布を見て見直す。",
        "- unavailable / invalid の実行は指標の分母から除外している。",
        "- decide.py の個別実行ログは `~/.autarch/decisions.jsonl` にも記録される。",
    ]
    if notes.strip():
        notes_body = notes.strip()
        if not notes_body.endswith("\n"):
            notes_body += "\n"
        lines.append(notes_body.rstrip())
    lines.append("")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="report_baseline.py",
        description="Aggregate a baseline directory into baseline.json and SUMMARY.md.",
    )
    parser.add_argument("--baseline-dir", required=True)
    parser.add_argument("--cases-dir", default=str(EVALS_DIR / "cases"))
    parser.add_argument("--loop-cases-dir", default=None)
    parser.add_argument("--compare-to", default=None,
                        help="path to a previous baseline.json for comparison")
    args = parser.parse_args(argv)
    baseline_dir = Path(args.baseline_dir)
    try:
        cases = case_schema.load_cases(args.cases_dir)
    except case_schema.CaseError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    loop_cases = None
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
    fixed_runs = load_jsonl(baseline_dir / "fixed_state_runs.jsonl")
    for run in fixed_runs:
        run.setdefault("classification", judging.classify_run(run["resolution"]))
    full_runs = load_jsonl(baseline_dir / "full_flow_runs.jsonl")
    environment = json.loads(
        (baseline_dir / "environment.json").read_text(encoding="utf-8")
    )
    notes_path = baseline_dir / "notes.md"
    notes = notes_path.read_text(encoding="utf-8") if notes_path.exists() else ""
    baseline = compute(cases, fixed_runs, full_runs, environment,
                       loop_cases=loop_cases)
    if args.compare_to:
        try:
            previous = json.loads(
                Path(args.compare_to).read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as error:
            print(
                f"error: cannot read comparison baseline "
                f"({type(error).__name__})",
                file=sys.stderr,
            )
            return 2
        if not isinstance(previous, dict):
            print(
                "error: comparison baseline must be a JSON object",
                file=sys.stderr,
            )
            return 2
        baseline["comparison"] = comparison_rows(baseline, previous)
    (baseline_dir / "baseline.json").write_text(
        json.dumps(baseline, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (baseline_dir / "SUMMARY.md").write_text(
        render_summary(baseline, notes), encoding="utf-8"
    )
    print(str(baseline_dir / "baseline.json"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
