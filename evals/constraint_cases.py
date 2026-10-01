"""Independent schema and mechanical verdicts for hard-constraint evaluations.

Cases declare one or two ordered phases, each with an expectations object.
A two-phase case also declares phase2 replacements for evidence_records and
hard_constraints plus a spent investigation revision. Existing evidence is kept.
"""

import copy
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills" / "autarch" / "scripts"))
import decide

DECISIONS = {"SELECT_OPTION", "SELECT_OPTION_WITH_CAUTION", "ASK_USER", "INSUFFICIENT_OPTIONS"}
VERDICTS = ("pass", "fail", "unavailable", "incomplete")


def constraint_phase2_state(case: dict) -> dict:
    """Replace constraint evidence on a deep copy; share the one revision budget."""
    state = copy.deepcopy(case["state"])
    for key in ("evidence_records", "hard_constraints", "revision"):
        state[key] = copy.deepcopy(case["phase2"][key])
    return state


def _ids(value, allowed, label):
    if (not isinstance(value, list) or not all(isinstance(v, str) for v in value)
            or len(value) != len(set(value)) or not set(value) <= allowed):
        raise ValueError(f"{label} must contain unique known ids")
    return set(value)


def _check_expectations(exp, state, invalid):
    if not isinstance(exp, dict):
        raise ValueError("expectations must be an object")
    options = {a["id"] for a in state["alternatives"]}
    constraints = {c["id"] for c in state.get("hard_constraints", [])}
    if exp.get("decision") not in DECISIONS:
        raise ValueError("expectations.decision is invalid")
    if not isinstance(exp.get("rule"), str) or not exp["rule"].strip():
        raise ValueError("expectations.rule must be non-empty")
    eligible = _ids(exp.get("eligible_option_ids"), options, "eligible_option_ids")
    excluded = _ids(exp.get("excluded_option_ids"), options, "excluded_option_ids")
    if eligible & excluded:
        raise ValueError("eligible and excluded ids overlap")
    unknown = exp.get("unknown_assessments")
    if not isinstance(unknown, list):
        raise ValueError("unknown_assessments must be a list")
    pairs = []
    for pair in unknown:
        if (not isinstance(pair, dict) or set(pair) != {"option_id", "constraint_id"}
                or pair["option_id"] not in options or pair["constraint_id"] not in constraints):
            raise ValueError("unknown_assessments must contain known option/constraint pairs")
        if pair["option_id"] in eligible | excluded:
            raise ValueError("unknown option cannot be eligible or excluded")
        pairs.append((pair["option_id"], pair["constraint_id"]))
    if len(pairs) != len(set(pairs)):
        raise ValueError("duplicate unknown assessments")
    if "selected_option" not in exp:
        raise ValueError("selected_option is required (null allowed)")
    selection = exp["selected_option"]
    if exp["decision"] in {"SELECT_OPTION", "SELECT_OPTION_WITH_CAUTION"}:
        if not isinstance(selection, str) or selection not in eligible:
            raise ValueError("selected_option must be eligible")
    elif selection is not None:
        raise ValueError("non-selection decisions require selected_option=null")
    _, check, early = decide.check_constraints(state)
    expected_check = {
        "eligible_option_ids": [*exp["eligible_option_ids"]],
        "excluded_options": [{"option_id": o} for o in exp["excluded_option_ids"]],
        "unknown_assessments": unknown,
    }
    if invalid:
        if (exp["decision"] != "INSUFFICIENT_OPTIONS" or exp["rule"] != "invalid_state"
                or eligible or excluded or unknown):
            raise ValueError("invalid fixtures must expect invalid_state and no constraint check")
    else:
        if _check_parts(check) != _check_parts(expected_check):
            raise ValueError("expectations conflict with constraint assessments")
        if early and (exp["decision"] != early["decision"] or exp["rule"] != early["rule"]):
            raise ValueError("expectations conflict with preflight stop")
        if not early and exp["rule"] in {"invalid_state", "constraint_unverified",
                "constraint_candidates_insufficient", "investigation_exhausted"}:
            raise ValueError("expectations request a preflight stop on an evaluable state")


def _validate_case(case):
    if not isinstance(case, dict):
        raise ValueError("case must be an object")
    if not isinstance(case.get("id"), str) or not re.fullmatch(r"[A-Za-z0-9_-]+", case["id"]):
        raise ValueError("id must be a safe non-empty identifier")
    if not isinstance(case.get("topic"), str) or not case["topic"].strip():
        raise ValueError("topic must be non-empty")
    if "expected_validation_errors" in case and type(case["expected_validation_errors"]) is not bool:
        raise ValueError("expected_validation_errors must be a boolean")
    state = case.get("state")
    errors = decide.validate_state(state)
    invalid = case.get("expected_validation_errors", False)
    if bool(errors) != invalid:
        raise ValueError("state validation contradicts expected_validation_errors: " + "; ".join(errors))
    # Even an intentionally invalid fixture needs the option and constraint IDs
    # required for mechanical expectations, rather than an arbitrary broken object.
    if (not isinstance(state, dict) or not isinstance(state.get("alternatives"), list)
            or not all(isinstance(a, dict) and isinstance(a.get("id"), str)
                       for a in state["alternatives"])
            or not isinstance(state.get("hard_constraints"), list)
            or not all(isinstance(c, dict) and isinstance(c.get("id"), str)
                       for c in state["hard_constraints"])):
        raise ValueError("constraint fixture must declare option and hard-constraint ids")
    phases = case.get("phases")
    if (not isinstance(phases, list) or len(phases) not in (1, 2)
            or not all(isinstance(p, dict) and type(p.get("phase")) is int for p in phases)
            or [p["phase"] for p in phases] != list(range(1, len(phases) + 1))):
        raise ValueError("phases must be ordered phase 1 or phases 1 and 2")
    if len(phases) == 2:
        phase2 = case.get("phase2")
        if (not isinstance(phase2, dict)
                or set(phase2) != {"evidence_records", "hard_constraints", "revision"}
                or not isinstance(phase2["revision"], dict)
                or phase2["revision"].get("action") != "investigation"
                or state.get("revision") is not None or invalid):
            raise ValueError("phase2 must replace constraint fields and spend one investigation revision")
        second = constraint_phase2_state(case)
        errors = decide.validate_state(second)
        if errors:
            raise ValueError("invalid phase2: " + "; ".join(errors))
        _check_expectations(phases[1].get("expectations"), second, False)
    elif "phase2" in case:
        raise ValueError("phase2 requires two phases")
    _check_expectations(phases[0].get("expectations"), state, invalid)


def load_constraint_cases(path: Path) -> list[dict]:
    """Load validated cases; empty directories and duplicate ids are errors."""
    files = sorted(Path(path).glob("*.json"))
    if not files:
        raise ValueError(f"{path} has no case files")
    cases = []
    for file in files:
        try:
            case = json.loads(file.read_text(encoding="utf-8"))
            _validate_case(case)
        except (OSError, UnicodeError, ValueError, TypeError, KeyError) as error:
            raise ValueError(f"{file.name}: {error}") from error
        cases.append(case)
    ids = [case["id"] for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate constraint case ids")
    return cases


def _check_parts(check):
    if not isinstance(check, dict):
        return None
    try:
        eligible = check["eligible_option_ids"]
        excluded = [o["option_id"] for o in check["excluded_options"]]
        unknown = [(p["option_id"], p["constraint_id"]) for p in check["unknown_assessments"]]
        if any(len(items) != len(set(items)) for items in (eligible, excluded, unknown)):
            return None
        return set(eligible), set(excluded), set(unknown)
    except (KeyError, TypeError):
        return None


def constraint_verdict(case: dict, records: list[dict]) -> str:
    """Judge one case repetition; missing phases and provider failure never pass."""
    expected_phases = {p["phase"] for p in case["phases"]}
    by_phase = {}
    indices = set()
    for record in records:
        if record.get("case_id") != case["id"]:
            raise ValueError("unknown case id")
        phase = record.get("phase")
        if type(phase) is not int or phase not in expected_phases:
            raise ValueError("unknown phase")
        if phase in by_phase:
            raise ValueError("duplicate phase")
        index = record.get("run_index")
        if type(index) is not int or index < 1:
            raise ValueError("run_index must be a positive integer")
        indices.add(index)
        by_phase[phase] = record
    if len(indices) > 1:
        raise ValueError("records mix run indices")
    if any(r.get("resolution", {}).get("decision") == "PROVIDER_UNAVAILABLE"
           for r in records):
        return "unavailable"
    if set(by_phase) != expected_phases:
        return "incomplete"
    for phase in case["phases"]:
        exp = phase["expectations"]
        result = by_phase[phase["phase"]].get("resolution", {})
        if any(result.get(key) != exp[key] for key in ("decision", "rule", "selected_option")):
            return "fail"
        check = result.get("constraint_check")
        if exp["rule"] == "invalid_state":
            if check is not None:
                return "fail"
        else:
            expected = {"eligible_option_ids": exp["eligible_option_ids"],
                "excluded_options": [{"option_id": o} for o in exp["excluded_option_ids"]],
                "unknown_assessments": exp["unknown_assessments"]}
            if (not isinstance(check, dict) or check.get("mode") != "structured"
                    or _check_parts(check) != _check_parts(expected)):
                return "fail"
    return "pass"


def constraint_metrics(cases: list[dict], runs: list[dict]) -> dict:
    """Count every case at every observed repetition, including missing records.

    The index range starts at 1; a gap cannot silently reduce the denominator.
    With no records each supplied case is counted as one incomplete repetition.
    """
    by_id = {c["id"]: c for c in cases}
    if len(by_id) != len(cases):
        raise ValueError("duplicate constraint case ids")
    grouped = {}
    max_index = 1
    for run in runs:
        if run.get("case_id") not in by_id:
            raise ValueError("unknown case id")
        index = run.get("run_index")
        if type(index) is not int or index < 1:
            raise ValueError("run_index must be a positive integer")
        max_index = max(max_index, index)
        grouped.setdefault((run["case_id"], index), []).append(run)
    counts = dict.fromkeys(VERDICTS, 0)
    verdicts = []
    for case in cases:
        for index in range(1, max_index + 1):
            verdict = constraint_verdict(case, grouped.get((case["id"], index), []))
            counts[verdict] += 1
            verdicts.append({"case_id": case["id"], "run_index": index, "verdict": verdict})
    judged = counts["pass"] + counts["fail"]
    return {"counts": counts, "pass_rate": round(counts["pass"] / judged, 4) if judged else None,
            "verdicts": verdicts}
