"""Loading and validation for Autarch evaluation cases and scenario expectations."""

import copy
import json
from pathlib import Path

SITUATIONS = ("constraint_clear", "info_missing", "preference_needed")
PERTURBATIONS = ("reorder", "detail_asymmetry", "evidence_removed", "violating_candidate")
TOPICS = ("database", "authentication", "test_framework", "dependency", "deployment")
DECISIONS = ("SELECT_OPTION", "SELECT_OPTION_WITH_CAUTION", "ASK_USER")
PERTURBED_TOPICS = ("database", "authentication")

LOOP_SITUATION = "loop_resolvable"
BLOCKER_CLASSES = (
    "user_preference_unknown",
    "facts_missing",
    "material_bias",
    "balanced_tie",
)


class CaseError(Exception):
    """Raised when a case file cannot be loaded or is invalid."""


def _group_lists(value):
    """Return value only if it is a non-empty list of non-empty keyword groups."""
    if not isinstance(value, list) or not value:
        return None
    for group in value:
        if not isinstance(group, list) or not group:
            return None
        if not all(isinstance(word, str) and word.strip() for word in group):
            return None
    return value


def _validate_expectations(exp, alternative_ids):
    errors = []
    decisions = exp.get("acceptable_decisions")
    if (not isinstance(decisions, list) or not decisions
            or not all(d in DECISIONS for d in decisions)):
        errors.append("acceptable_decisions must be a non-empty subset of " + str(DECISIONS))
        decisions = []
    ask_only = set(decisions) == {"ASK_USER"}
    for field in ("acceptable_selections", "forbidden_selections"):
        value = exp.get(field)
        if not isinstance(value, list):
            errors.append(f"{field} must be a list")
            continue
        if field == "acceptable_selections" and not ask_only and not value:
            errors.append("acceptable_selections must be a non-empty list")
            continue
        unknown = [item for item in value if item not in alternative_ids]
        if unknown:
            errors.append(f"{field} references unknown alternative ids: {unknown}")
    preference = exp.get("requires_human_preference")
    if preference is not None and not isinstance(preference, bool):
        errors.append("requires_human_preference must be a boolean when present")
    return errors


def validate_case(case):
    """Validate one fixed-state case. Returns violations (empty = valid)."""
    if not isinstance(case, dict):
        return ["case must be a JSON object"]
    errors = []
    if not isinstance(case.get("id"), str) or not case["id"]:
        errors.append("id must be a non-empty string")
    if case.get("topic") not in TOPICS:
        errors.append("topic must be one of " + str(TOPICS))
    if case.get("situation") not in SITUATIONS:
        errors.append("situation must be one of " + str(SITUATIONS))
    state = case.get("state")
    if not isinstance(state, dict):
        errors.append("state must be an object")
        state = {}
    alternatives = state.get("alternatives")
    alternative_ids = (
        [a.get("id") for a in alternatives if isinstance(a, dict)]
        if isinstance(alternatives, list) else []
    )
    exp = case.get("expectations")
    if not isinstance(exp, dict):
        errors.append("expectations must be an object")
    else:
        errors.extend(_validate_expectations(exp, alternative_ids))
    derived = case.get("derived_from")
    if derived is not None:
        if (not isinstance(derived, dict)
                or not isinstance(derived.get("base"), str)
                or derived.get("perturbation") not in PERTURBATIONS):
            errors.append(
                'derived_from must be {"base": <case id>, "perturbation": one of '
                + str(PERTURBATIONS) + "}"
            )
    return errors


def validate_scenario_expectations(exp):
    """Validate one full-flow scenario expectations object."""
    if not isinstance(exp, dict):
        return ["expectations must be an object"]
    errors = []
    if exp.get("situation") not in SITUATIONS:
        errors.append("situation must be one of " + str(SITUATIONS))
    if _group_lists(exp.get("required_alternatives")) is None:
        errors.append("required_alternatives must be a non-empty list of keyword groups")
    if exp.get("forbidden_alternatives") not in (None, []):
        if _group_lists(exp.get("forbidden_alternatives")) is None:
            errors.append("forbidden_alternatives must be keyword groups when present")
    decisions = exp.get("acceptable_decisions")
    if (not isinstance(decisions, list) or not decisions
            or not all(d in DECISIONS for d in decisions)):
        errors.append("acceptable_decisions must be a non-empty subset of " + str(DECISIONS))
        decisions = []
    selections = exp.get("acceptable_selections")
    if set(decisions) == {"ASK_USER"}:
        if selections not in (None, []):
            errors.append("acceptable_selections must be empty when ASK_USER is expected")
    elif _group_lists(selections) is None:
        errors.append("acceptable_selections must be a non-empty list of keyword groups")
    preference = exp.get("requires_human_preference")
    if preference is not None and not isinstance(preference, bool):
        errors.append("requires_human_preference must be a boolean when present")
    return errors


def validate_loop_case(case):
    """Validate one two-phase loop case. Returns violations (empty = valid)."""
    if not isinstance(case, dict):
        return ["case must be a JSON object"]
    errors = []
    if not isinstance(case.get("id"), str) or not case["id"]:
        errors.append("id must be a non-empty string")
    if case.get("topic") not in TOPICS:
        errors.append("topic must be one of " + str(TOPICS))
    if case.get("situation") != LOOP_SITUATION:
        errors.append("situation must be " + LOOP_SITUATION)
    state = case.get("state")
    if not isinstance(state, dict):
        errors.append("state must be an object")
        state = {}
    if state.get("revision") is not None:
        errors.append("loop case state must not include revision")
    alternatives = state.get("alternatives")
    alternative_ids = (
        [a.get("id") for a in alternatives if isinstance(a, dict)]
        if isinstance(alternatives, list) else []
    )
    investigation = case.get("investigation")
    if not isinstance(investigation, dict):
        errors.append("investigation must be an object")
    else:
        injected = investigation.get("injected_evidence")
        if (not isinstance(injected, list) or not injected
                or not all(isinstance(item, str) and item.strip()
                           for item in injected)):
            errors.append(
                "injected_evidence must be a non-empty list of non-empty strings"
            )
        phase1 = investigation.get("phase1")
        if (not isinstance(phase1, dict)
                or phase1.get("rule") != "evidence_insufficient"
                or phase1.get("blocker_class") not in BLOCKER_CLASSES):
            errors.append(
                'phase1 must be {"rule": "evidence_insufficient", '
                '"blocker_class": one of ' + str(BLOCKER_CLASSES) + "}"
            )
        phase2 = investigation.get("phase2")
        if not isinstance(phase2, dict):
            errors.append("phase2 must be an object")
        else:
            errors.extend(_validate_expectations(phase2, alternative_ids))
            decisions = phase2.get("acceptable_decisions")
            if isinstance(decisions, list) and not (
                    set(decisions)
                    & {"SELECT_OPTION", "SELECT_OPTION_WITH_CAUTION"}
            ):
                errors.append(
                    "phase2.acceptable_decisions must include a selection decision"
                )
    if case.get("derived_from") is not None:
        errors.append("derived_from must be null for loop cases")
    return errors


def load_loop_cases(cases_dir):
    """Load and validate every loop case file in cases_dir (sorted by filename)."""
    cases = []
    violations = []
    for path in sorted(Path(cases_dir).glob("*.json")):
        try:
            case = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise CaseError(
                f"{path.name}: cannot load ({type(error).__name__})"
            ) from None
        errors = validate_loop_case(case)
        if errors:
            violations.append(f"{path.name}: " + "; ".join(errors))
        cases.append(case)
    if violations:
        raise CaseError(
            "invalid loop case files:\n  - " + "\n  - ".join(violations)
        )
    ids = [case.get("id") for case in cases]
    if len(ids) != len(set(ids)):
        raise CaseError("duplicate loop case ids: " + str(sorted(ids)))
    return cases


def loop_phase2_state(case):
    """The post-investigation state: injected evidence plus a spent revision."""
    state = copy.deepcopy(case["state"])
    state["evidence"] = list(state.get("evidence", [])) + list(
        case["investigation"]["injected_evidence"]
    )
    state["revision"] = {
        "round": 1,
        "action": "investigation",
        "summary": "injected by eval runner",
    }
    return state


def load_cases(cases_dir):
    """Load and validate every case file in cases_dir (sorted by filename)."""
    cases = []
    violations = []
    for path in sorted(Path(cases_dir).glob("*.json")):
        try:
            case = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise CaseError(f"{path.name}: cannot load ({type(error).__name__})") from None
        errors = validate_case(case)
        if errors:
            violations.append(f"{path.name}: " + "; ".join(errors))
        cases.append(case)
    if violations:
        raise CaseError("invalid case files:\n  - " + "\n  - ".join(violations))
    ids = [case.get("id") for case in cases]
    if len(ids) != len(set(ids)):
        raise CaseError("duplicate case ids: " + str(sorted(ids)))
    return cases


def validate_case_set(cases):
    """Set-level invariants: the 5x3 base grid, the 8 derived cases, transformations."""
    errors = []
    by_id = {case["id"]: case for case in cases}
    grid = {(c["topic"], c["situation"]) for c in cases if not c.get("derived_from")}
    expected_grid = {(topic, situation)
                     for topic in TOPICS for situation in SITUATIONS}
    missing = expected_grid - grid
    extra = grid - expected_grid
    if missing:
        errors.append(f"missing base cases: {sorted(missing)}")
    if extra:
        errors.append(f"unexpected base cases: {sorted(extra)}")
    derived = {(c["topic"], c["derived_from"]["perturbation"])
               for c in cases if c.get("derived_from")}
    expected_derived = {(topic, perturbation)
                        for topic in PERTURBED_TOPICS for perturbation in PERTURBATIONS}
    if derived != expected_derived:
        errors.append(
            f"derived cases must be exactly {sorted(expected_derived)} (found {sorted(derived)})"
        )
    for case in cases:
        derived_from = case.get("derived_from")
        if not derived_from:
            continue
        base = by_id.get(derived_from["base"])
        if base is None:
            errors.append(f"{case['id']}: derived_from.base {derived_from['base']!r} not found")
            continue
        if base.get("derived_from"):
            errors.append(f"{case['id']}: base must itself be a base case")
            continue
        if base["topic"] != case["topic"]:
            errors.append(f"{case['id']}: base topic mismatch")
            continue
        perturbation = derived_from["perturbation"]
        base_ids = [a["id"] for a in base["state"]["alternatives"]]
        case_ids = [a["id"] for a in case["state"]["alternatives"]]
        if perturbation == "reorder":
            if sorted(base_ids) != sorted(case_ids) or base_ids == case_ids:
                errors.append(f"{case['id']}: reorder must permute the base alternative ids")
        elif perturbation == "detail_asymmetry":
            if sorted(base_ids) != sorted(case_ids):
                errors.append(f"{case['id']}: detail_asymmetry must keep the base ids")
                continue
            base_desc = {a["id"]: a["description"] for a in base["state"]["alternatives"]}
            case_desc = {a["id"]: a["description"] for a in case["state"]["alternatives"]}
            grew = sum(1 for key in base_desc if len(case_desc[key]) > len(base_desc[key]))
            shrunk = any(len(case_desc[key]) < len(base_desc[key]) for key in base_desc)
            if grew != 1 or shrunk:
                errors.append(
                    f"{case['id']}: detail_asymmetry must lengthen exactly one description"
                )
        elif perturbation == "evidence_removed":
            if not set(case["state"]["evidence"]) < set(base["state"]["evidence"]):
                errors.append(f"{case['id']}: evidence must be a strict subset of the base")
        elif perturbation == "violating_candidate":
            kept = sorted(i for i in case_ids if i in base_ids)
            added = [i for i in case_ids if i not in base_ids]
            if kept != sorted(base_ids) or len(added) != 1:
                errors.append(f"{case['id']}: violating_candidate must add exactly one option")
            elif added != case["expectations"]["forbidden_selections"]:
                errors.append(
                    f"{case['id']}: the added option must be the forbidden selection"
                )
    return errors
