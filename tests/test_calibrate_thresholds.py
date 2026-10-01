import copy

import pytest

import decide
from test_decide import _valid_state, _constraint_state, _thresholds, make_answers, answers_body


def replay(state, snapshot, thresholds=None, gate_order="human_first"):
    # Import in the call so missing functionality produces focused test failures.
    import calibrate_thresholds
    return calibrate_thresholds.replay_resolution(
        state, snapshot, thresholds or _thresholds(), gate_order)


def snapshot_for(state, **answers_kwargs):
    evaluated, _, early = decide.check_constraints(state)
    assert early is None
    parsed = decide.parse_answers(answers_body(make_answers(evaluated, **answers_kwargs)), evaluated)
    return {"schema_version": 1, "parsed": parsed, "thresholds": _thresholds(),
            "gate_order": "human_first",
            "evaluated_option_ids": [a["id"] for a in evaluated["alternatives"]]}


def test_replay_preserves_close_score_winner():
    state = _valid_state()
    snapshot = snapshot_for(state)
    snapshot["parsed"]["scores"]["fit"] = {"option_a": 1.00004, "option_b": 1.00002}
    direct = decide.resolve(state, snapshot["parsed"], _thresholds())
    assert direct["score_summary"]["option_a"]["composite"] == 0.5
    assert direct["score_summary"]["option_b"]["composite"] == 0.5
    assert (direct["decision"], direct["rule"], direct["selected_option"]) == (
        "SELECT_OPTION", "confidence", "option_a")
    replayed = replay(state, snapshot)
    assert (replayed["decision"], replayed["rule"], replayed["selected_option"]) == (
        "SELECT_OPTION", "confidence", "option_a")


def test_replay_filters_original_state_and_can_override_policy_without_mutation():
    state = _constraint_state()
    snapshot = snapshot_for(state, noul=0.9, sufficiency=0.2)
    before = copy.deepcopy((state, snapshot))
    assert replay(state, snapshot)["rule"] == "human_preference"
    result = replay(state, snapshot, gate_order="evidence_first")
    assert result["rule"] == "evidence_insufficient"
    assert set(result["probabilities"]) == {"option_a", "option_b"}
    assert result["constraint_check"]["eligible_option_ids"] == ["option_a", "option_b"]
    assert (state, snapshot) == before
    thresholds = {**_thresholds(), "human_preference": 1.0, "sufficiency": 0.1}
    assert replay(state, snapshot, thresholds)["decision"] == "SELECT_OPTION"


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf"), True, "0.9"])
@pytest.mark.parametrize("field", ["confidence", "human_preference", "evidence_sufficiency",
                                   "blocker_confidence", "probabilities", "scores"])
def test_replay_rejects_invalid_numbers(field, bad):
    state = _valid_state()
    snapshot = snapshot_for(state)
    if field == "probabilities":
        snapshot["parsed"][field]["option_a"] = bad
    elif field == "scores":
        snapshot["parsed"][field]["fit"]["option_a"] = bad
    else:
        snapshot["parsed"][field] = bad
    with pytest.raises(ValueError):
        replay(state, snapshot)


@pytest.mark.parametrize("field", ["human_preference", "choice", "confidence", "probabilities",
                                   "scores", "evidence_sufficiency", "blocker_class",
                                   "blocker_confidence"])
def test_replay_requires_every_parsed_signal(field):
    state = _valid_state()
    snapshot = snapshot_for(state)
    del snapshot["parsed"][field]
    with pytest.raises(ValueError):
        replay(state, snapshot)


@pytest.mark.parametrize("change", ["version", "bool_version", "missing_thresholds", "threshold_nan",
                                    "gate_order", "parsed_type", "ids_type", "duplicate_ids",
                                    "ids_mismatch", "ids_order", "probability_ids", "score_option_ids",
                                    "score_criterion_ids", "choice", "choice_disagreement", "blocker",
                                    "score_range", "signal_range", "threshold_range", "extra_signal"])
def test_replay_rejects_malformed_snapshot(change):
    state = _valid_state()
    snapshot = snapshot_for(state)
    if change == "version": snapshot["schema_version"] = 2
    elif change == "bool_version": snapshot["schema_version"] = True
    elif change == "missing_thresholds": del snapshot["thresholds"]
    elif change == "threshold_nan": snapshot["thresholds"]["sufficiency"] = float("nan")
    elif change == "gate_order": snapshot["gate_order"] = "unknown"
    elif change == "parsed_type": snapshot["parsed"] = []
    elif change == "ids_type": snapshot["evaluated_option_ids"] = "option_a"
    elif change == "duplicate_ids": snapshot["evaluated_option_ids"] = ["option_a", "option_a"]
    elif change == "ids_mismatch": snapshot["evaluated_option_ids"] = ["option_a", "option_c"]
    elif change == "ids_order": snapshot["evaluated_option_ids"].reverse()
    elif change == "probability_ids": snapshot["parsed"]["probabilities"]["option_c"] = 0.0
    elif change == "score_option_ids": del snapshot["parsed"]["scores"]["fit"]["option_b"]
    elif change == "score_criterion_ids": snapshot["parsed"]["scores"]["other"] = {}
    elif change == "choice": snapshot["parsed"]["choice"] = "option_c"
    elif change == "choice_disagreement": snapshot["parsed"]["choice"] = "option_b"
    elif change == "blocker": snapshot["parsed"]["blocker_class"] = "other"
    elif change == "score_range": snapshot["parsed"]["scores"]["fit"]["option_a"] = 3.0
    elif change == "signal_range": snapshot["parsed"]["confidence"] = 1.1
    elif change == "threshold_range": snapshot["thresholds"]["sufficiency"] = -0.1
    elif change == "extra_signal": snapshot["parsed"]["raw_response"] = "secret"
    with pytest.raises(ValueError):
        replay(state, snapshot)


@pytest.mark.parametrize("change", ["unknown", "one_eligible", "invalid", "nonfinite_weight"])
def test_replay_rejects_state_that_cannot_be_evaluated(change):
    state = _constraint_state()
    snapshot = snapshot_for(state)
    if change == "unknown":
        state["hard_constraints"][0]["assessments"]["option_b"]["status"] = "unknown"
    elif change == "one_eligible":
        state["hard_constraints"][0]["assessments"]["option_b"]["status"] = "violated"
    elif change == "invalid":
        state["question"] = ""
    else:
        state["criteria"][0]["weight"] = float("inf")
    with pytest.raises(ValueError):
        replay(state, snapshot)


@pytest.mark.parametrize("thresholds, order", [
    ({**_thresholds(), "sufficiency": float("inf")}, "human_first"),
    ({**_thresholds(), "review": True}, "human_first"),
    ({k: v for k, v in _thresholds().items() if k != "min_gap"}, "human_first"),
    (_thresholds(), "unknown"),
])
def test_replay_rejects_invalid_override(thresholds, order):
    state = _valid_state()
    with pytest.raises(ValueError):
        replay(state, snapshot_for(state), thresholds, order)


@pytest.mark.parametrize("field", ["schema_version", "parsed", "thresholds", "gate_order",
                                   "evaluated_option_ids"])
def test_replay_requires_snapshot_metadata(field):
    state = _valid_state()
    snapshot = snapshot_for(state)
    del snapshot[field]
    with pytest.raises(ValueError):
        replay(state, snapshot)


@pytest.mark.parametrize("snapshot", [None, [], "", 1])
def test_replay_rejects_nonobject_snapshot(snapshot):
    with pytest.raises(ValueError):
        replay(_valid_state(), snapshot)


@pytest.mark.parametrize("option_id", ["option_a\n", "option__a", "invalid option", "", 1])
def test_replay_rejects_malformed_option_ids(option_id):
    state = _valid_state()
    snapshot = snapshot_for(state)
    snapshot["evaluated_option_ids"][0] = option_id
    with pytest.raises(ValueError):
        replay(state, snapshot)


def test_replay_does_not_allow_secret_choice_identity_from_untrusted_snapshot():
    state = _valid_state()
    state["alternatives"][0]["id"] = "sk-abcdefgh123456"
    snapshot = snapshot_for(_valid_state())
    snapshot["evaluated_option_ids"][0] = "sk-abcdefgh123456"
    parsed = snapshot["parsed"]
    parsed["choice"] = "sk-abcdefgh123456"
    parsed["probabilities"]["sk-abcdefgh123456"] = parsed["probabilities"].pop("option_a")
    parsed["scores"]["fit"]["sk-abcdefgh123456"] = parsed["scores"]["fit"].pop("option_a")
    with pytest.raises(ValueError):
        replay(state, snapshot)


def test_replay_without_criteria_uses_valid_choice_signals():
    state = _valid_state()
    state["criteria"] = []
    result = replay(state, snapshot_for(state))
    assert (result["decision"], result["selected_option"], result["score_summary"]) == (
        "SELECT_OPTION", "option_a", None)


def calibration_case(case_id, situation="constraint_clear", derived=None):
    return {"id": case_id, "topic": "database", "situation": situation,
            "state": _valid_state(), "derived_from": derived,
            "expectations": {"acceptable_decisions": ["SELECT_OPTION", "SELECT_OPTION_WITH_CAUTION"],
                             "acceptable_selections": ["option_a"], "forbidden_selections": []}}


def captured_runs(case, sufficiency=0.9, confidence=0.95, blocker_confidence=0.9, noul=0.1):
    snapshot = snapshot_for(case["state"], sufficiency=sufficiency, confidence=confidence,
                            blocker_confidence=blocker_confidence, noul=noul)
    return [{"case_id": case["id"], "run_index": index,
             "resolution": {**replay(case["state"], snapshot), "evaluation_snapshot": snapshot}}
            for index in (1, 2, 3)]


def test_grid_ranks_90_policies_and_prefers_smallest_current_order_change():
    import calibrate_thresholds as cal
    clear = calibration_case("clear")
    missing = calibration_case("missing", derived={"base": "clear", "perturbation": "evidence_removed"})
    ranked = cal.rank_policies([clear, missing], captured_runs(clear) + captured_runs(missing, 0.82))
    assert len(cal.candidate_policies()) == len(ranked) == 90
    assert ranked[0]["thresholds"] == {**_thresholds(), "sufficiency": 0.85}
    assert ranked[0]["gate_order"] == "human_first"
    assert ranked[0]["counts"]["evidence_misses"] == 0
    assert ranked[0]["counts"]["clear_completed"] == 3
    assert ranked[0]["counts"]["clear_correct"] == 3
    assert cal.candidate_policies()[0]["thresholds"] == {**_thresholds(), "blocker_confidence": 0.0}
    assert cal.candidate_policies()[-1]["thresholds"] == {
        **_thresholds(), "sufficiency": 0.9, "auto_select": 0.95, "blocker_confidence": 0.7}
    assert {p["thresholds"]["review"] for p in ranked} == {0.6}
    assert {p["thresholds"]["min_gap"] for p in ranked} == {0.15}
    assert {p["thresholds"]["human_preference"] for p in ranked} == {0.7}
    assert ranked[-1]["grid_index"] >= 0


def test_rank_keeps_caution_completed_and_missing_provider_runs_out_of_counts():
    import calibrate_thresholds as cal
    case = calibration_case("clear")
    runs = captured_runs(case, confidence=0.8)
    runs[2]["resolution"] = {"decision": "PROVIDER_UNAVAILABLE"}
    summary = cal.rank_policies([case], runs)[0]
    assert summary["counts"]["clear_completed"] == 2
    assert summary["counts"]["unavailable"] == 1
    assert summary["coverage"]["clear"]["1"]["valid"] == 2
    assert not summary["complete"]
    summary = cal.rank_policies([case], runs[:1])[0]
    assert summary["counts"]["missing"] == 2
    assert not summary["complete"]


@pytest.mark.parametrize("change", ["duplicate", "unknown", "index", "phase", "no_snapshot", "wrong_capture"])
def test_rank_rejects_inconsistent_records(change):
    import calibrate_thresholds as cal
    case = calibration_case("clear")
    runs = captured_runs(case)
    if change == "duplicate": runs.append(copy.deepcopy(runs[0]))
    elif change == "unknown": runs[0]["case_id"] = "other"
    elif change == "index": runs[0]["run_index"] = True
    elif change == "phase": runs[0]["phase"] = 2
    elif change == "no_snapshot": runs[0]["resolution"].pop("evaluation_snapshot")
    elif change == "wrong_capture": runs[0]["resolution"]["evaluation_snapshot"]["gate_order"] = "evidence_first"
    with pytest.raises(ValueError):
        cal.rank_policies([case], runs)


def adoption_counts(**changes):
    return {"complete": True, "counts": {"unsafe": 0, "evidence_misses": 0,
            "clear_completed": 15, "clear_correct": 15, "db_loop_passes": 3,
            "db_loop_total": 3, "missing_asked": 15, "confirmed_correct": 15,
            "missing_expected": 15, "confirmed_expected": 15, **changes}}


def test_adoption_requires_improvement_and_all_frozen_validation_pairs():
    import calibrate_thresholds as cal
    reference = adoption_counts(evidence_misses=3)
    candidate = adoption_counts()
    validation = adoption_counts()
    assert cal.adoption_verdict(reference, candidate, validation) == {"accepted": True, "reasons": []}


@pytest.mark.parametrize("target, changes, reason", [
    ("candidate", {"unsafe": 1}, "unsafe increased"),
    ("candidate", {"evidence_misses": 3}, "evidence misses did not decrease"),
    ("candidate", {"clear_completed": 14}, "clear completions decreased"),
    ("candidate", {"clear_correct": 14}, "clear correct selections decreased"),
    ("candidate", {"db_loop_passes": 2}, "db loop did not fully pass"),
    ("validation", {"unsafe": 1}, "validation unsafe is not zero"),
    ("validation", {"missing_asked": 14}, "validation missing ASK_USER must be 15/15"),
    ("validation", {"confirmed_correct": 14}, "validation confirmed selections must be 15/15"),
])
def test_adoption_rejects_each_gate(target, changes, reason):
    import calibrate_thresholds as cal
    reference, candidate, validation = adoption_counts(evidence_misses=3), adoption_counts(), adoption_counts()
    (candidate if target == "candidate" else validation)["counts"].update(changes)
    verdict = cal.adoption_verdict(reference, candidate, validation)
    assert not verdict["accepted"]
    assert reason in verdict["reasons"]


def test_adoption_rejects_incomplete_validation_and_reference():
    import calibrate_thresholds as cal
    reference, candidate, validation = adoption_counts(evidence_misses=3), adoption_counts(), adoption_counts()
    reference["complete"] = validation["complete"] = False
    verdict = cal.adoption_verdict(reference, candidate, validation)
    assert not verdict["accepted"]
    assert "reference requires three valid runs per case phase" in verdict["reasons"]
    assert "validation requires three valid runs per case phase" in verdict["reasons"]


def test_describe_marks_legacy_blocker_unknown_without_claiming_replay(tmp_path):
    import json
    import calibrate_thresholds as cal
    runs = tmp_path / "runs.jsonl"
    runs.write_text(json.dumps({"case_id": "db_constraint_clear", "run_index": 1,
        "resolution": {"decision": "SELECT_OPTION", "confidence": 0.95,
                       "evidence_sufficiency": 0.82, "human_preference_probability": 0.1,
                       "blocker_class": None, "blocker_confidence": None}}) + "\n")
    output = tmp_path / "description.json"
    assert cal.main(["describe", "--runs-file", str(runs), "--out-file", str(output)]) == 0
    described = json.loads(output.read_text())
    entry = described["groups"]["constraint_clear/phase1"]
    assert entry["blocker_class"] == {"unknown": 1}
    assert entry["blocker_confidence"]["missing"] == 1
    assert described["replayable"] == 0
    before = output.read_bytes()
    assert cal.main(["describe", "--runs-file", str(runs), "--out-file", str(output)]) == 2
    assert output.read_bytes() == before


def test_rank_detects_loop_phase2_failure_and_counts_phase1_unsafe():
    import calibrate_thresholds as cal
    case = calibration_case("db_loop", "loop_resolvable")
    case.pop("expectations")
    case["investigation"] = {"injected_evidence": ["Checked local usage"],
        "phase1": {"rule": "evidence_insufficient", "blocker_class": "facts_missing"},
        "phase2": {"acceptable_decisions": ["SELECT_OPTION", "SELECT_OPTION_WITH_CAUTION"],
                   "acceptable_selections": ["option_a"], "forbidden_selections": []}}
    runs = [{**run, "phase": 1} for run in captured_runs(case, 0.65)]
    import case_schema
    second_case = {**case, "state": case_schema.loop_phase2_state(case)}
    runs += [{**run, "phase": 2} for run in captured_runs(second_case, 0.82)]
    ranked = cal.rank_policies([case], runs)
    current = next(row for row in ranked if row["thresholds"] == _thresholds() and row["gate_order"] == "human_first")
    strict = next(row for row in ranked if row["thresholds"] == {**_thresholds(), "sufficiency": 0.85}
                  and row["gate_order"] == "human_first")
    assert current["counts"]["unsafe"] == 3
    assert strict["counts"]["loop_phase2_failures"] == 3
    assert strict["counts"]["db_loop_passes"] == 0


@pytest.mark.parametrize("sufficiency, blocker, expected", [(0.85, 0.5, "SELECT_OPTION"),
    (0.849999, 0.5, "ASK_USER"), (0.849999, 0.499999, "SELECT_OPTION")])
def test_rank_replay_threshold_boundaries(sufficiency, blocker, expected):
    import calibrate_thresholds as cal
    case = calibration_case("clear")
    runs = captured_runs(case, sufficiency, blocker_confidence=blocker)
    ranked = cal.rank_policies([case], runs)
    strict = next(row for row in ranked if row["thresholds"] == {**_thresholds(), "sufficiency": 0.85}
                  and row["gate_order"] == "human_first")
    assert strict["counts"]["clear_completed"] == (3 if expected == "SELECT_OPTION" else 0)


def cli_fixture(tmp_path):
    import hashlib
    import json
    from pathlib import Path
    import case_schema
    root = Path(__file__).resolve().parents[1] / "evals"
    cases = case_schema.load_cases(root / "cases")
    loops = case_schema.load_loop_cases(root / "cases_loop")
    runs = []
    for case in cases + loops:
        for phase in ((1, 2) if "investigation" in case else (1,)):
            state = case_schema.loop_phase2_state(case) if phase == 2 else case["state"]
            exp = case["investigation"]["phase2"] if "investigation" in case else case["expectations"]
            choice = (exp["acceptable_selections"] or [state["alternatives"][0]["id"]])[0]
            removed = (case.get("derived_from") or {}).get("perturbation") == "evidence_removed"
            suff = 0.2 if case["situation"] == "info_missing" or ("investigation" in case and phase == 1) else (0.82 if removed else 0.98)
            snap = snapshot_for(state, choice=choice, sufficiency=suff,
                                noul=0.9 if case["situation"] == "preference_needed" else 0.1)
            for index in (1, 2, 3):
                runs.append({"case_id": case["id"], "phase": phase, "run_index": index,
                             "recorded_at": "2026-10-01T00:00:00Z",
                             "resolution": {"decision": "ASK_USER", "model": "fixture", "evaluation_snapshot": copy.deepcopy(snap)}})
    training = tmp_path / "training.jsonl"
    training.write_text("".join(json.dumps(run) + "\n" for run in runs))
    validation_dir = tmp_path / "validation"
    metadata = validation_dir / "metadata"
    metadata.mkdir(parents=True)
    entries, validation_cases = [], []
    for topic in case_schema.TOPICS:
        for situation in ("info_missing", "constraint_clear"):
            case = calibration_case(f"validation_{topic}_{situation}", situation)
            case["topic"] = topic
            if situation == "info_missing":
                case["expectations"].update(acceptable_decisions=["ASK_USER"], acceptable_selections=[])
            path = validation_dir / (case["id"] + ".json")
            path.write_text(json.dumps(case))
            entries.append({"id": case["id"], "topic": topic, "pair_id": topic,
                            "path": "../" + path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
            validation_cases.append(case)
    manifest = metadata / "manifest.json"
    manifest.write_text(json.dumps({"schema_version": 1, "frozen_at": "2026-10-01T00:00:00Z", "cases": entries}))
    return root, training, manifest, validation_cases


def test_search_freezes_policy_and_validate_accepts_without_live_calls(tmp_path):
    import json
    import calibrate_thresholds as cal
    root, training, manifest, cases = cli_fixture(tmp_path)
    out = tmp_path / "search"
    argv = ["search", "--cases-dir", str(root / "cases"), "--loop-cases-dir", str(root / "cases_loop"),
            "--runs-file", str(training), "--manifest", str(manifest), "--out-dir", str(out)]
    assert cal.main(argv) == 0
    policy = json.loads((out / "selected-policy.json").read_text())
    assert policy["thresholds"]["sufficiency"] == 0.85
    assert policy["training"]["adoption"]["accepted"]
    assert policy["manifest_hash"]
    assert policy["training_case_hash"]
    runs = []
    for case in cases:
        for run in captured_runs(case, 0.2 if case["situation"] == "info_missing" else 0.98):
            run["resolution"]["evaluation_snapshot"]["thresholds"] = policy["thresholds"]
            run["resolution"]["evaluation_snapshot"]["gate_order"] = policy["gate_order"]
            runs.append(run)
    validation = tmp_path / "validation.jsonl"
    validation.write_text("".join(json.dumps(run) + "\n" for run in runs))
    validate_argv = ["validate", "--policy-file", str(out / "selected-policy.json"), "--manifest", str(manifest),
                     "--runs-file", str(validation), "--out-dir", str(tmp_path / "validated")]
    assert cal.main(validate_argv) == 0
    result = json.loads((tmp_path / "validated" / "adoption.json").read_text())
    assert result["accepted"]
    assert result["validation"]["counts"]["missing_asked"] == 15
    assert result["validation"]["counts"]["confirmed_correct"] == 15
    # A missing run rejects adoption, while incompatible captured settings are invalid input.
    validation.write_text("".join(json.dumps(run) + "\n" for run in runs[:-1]))
    validate_argv[-1] = str(tmp_path / "incomplete")
    assert cal.main(validate_argv) == 1
    runs[0]["resolution"]["evaluation_snapshot"]["thresholds"] = _thresholds()
    validation.write_text("".join(json.dumps(run) + "\n" for run in runs))
    validate_argv[-1] = str(tmp_path / "incompatible")
    assert cal.main(validate_argv) == 2
    assert not (tmp_path / "incompatible").exists()
    before = {path.name: path.read_bytes() for path in out.iterdir()}
    assert cal.main(argv) == 2
    assert {path.name: path.read_bytes() for path in out.iterdir()} == before


def test_search_rejects_partial_training_without_creating_outputs(tmp_path):
    import calibrate_thresholds as cal
    root, training, manifest, _ = cli_fixture(tmp_path)
    training.write_text(training.read_text().splitlines()[0] + "\n")
    out = tmp_path / "search"
    assert cal.main(["search", "--cases-dir", str(root / "cases"), "--loop-cases-dir", str(root / "cases_loop"),
                     "--runs-file", str(training), "--manifest", str(manifest), "--out-dir", str(out)]) == 2
    assert not out.exists()


@pytest.mark.parametrize("change", ["hash", "absolute", "escape", "duplicate", "missing_pair"])
def test_validation_manifest_rejects_hash_path_and_pair_errors(tmp_path, change):
    import json
    import calibrate_thresholds as cal
    _, _, manifest, _ = cli_fixture(tmp_path)
    data = json.loads(manifest.read_text())
    if change == "hash": data["cases"][0]["sha256"] = "0" * 64
    elif change == "absolute": data["cases"][0]["path"] = "/tmp/other.json"
    elif change == "escape": data["cases"][0]["path"] = "../../other.json"
    elif change == "duplicate": data["cases"][1] = data["cases"][0]
    else: data["cases"].pop()
    manifest.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        cal.load_validation_manifest(manifest)


def test_grid_ties_use_change_count_order_absolute_delta_and_grid_order():
    import calibrate_thresholds as cal
    case = calibration_case("clear")
    ranked = cal.rank_policies([case], captured_runs(case, 0.98))
    assert ranked[0]["thresholds"] == _thresholds()
    assert ranked[0]["gate_order"] == "human_first"
    assert len({(tuple(sorted(row["thresholds"].items())), row["gate_order"]) for row in ranked}) == 90
    current = ranked[0]
    assert current["rank_key"] == [0, 0, 0, 0, 0, False, 0.0, 2]
    index = {row["grid_index"]: pos for pos, row in enumerate(ranked)}
    # 0.05 auto-select changes sort before the 0.15 sufficiency change.
    assert index[8] < index[20]
    # One order change is preferred to two threshold changes despite human_first.
    assert index[3] < index[18]
    # A current-order threshold change is preferred over an order-only change.
    assert index[8] < index[3]
    # Same change count, order and distance: the declared sufficiency/auto grid wins.
    assert index[32] < index[44]


@pytest.mark.parametrize("resolution", [[], None, "invalid"])
def test_describe_rejects_invalid_resolution_without_output(tmp_path, resolution):
    import json
    import calibrate_thresholds as cal
    runs = tmp_path / "runs.jsonl"
    runs.write_text(json.dumps({"case_id": "clear", "resolution": resolution}) + "\n")
    output = tmp_path / "description.json"
    assert cal.main(["describe", "--runs-file", str(runs), "--out-file", str(output)]) == 2
    assert not output.exists()


def test_validate_rejects_selected_settings_that_differ_from_frozen_training(tmp_path):
    import json
    import calibrate_thresholds as cal
    root, training, manifest, _ = cli_fixture(tmp_path)
    out = tmp_path / "search"
    assert cal.main(["search", "--cases-dir", str(root / "cases"), "--loop-cases-dir", str(root / "cases_loop"),
                     "--runs-file", str(training), "--manifest", str(manifest), "--out-dir", str(out)]) == 0
    policy = json.loads((out / "selected-policy.json").read_text())
    policy["thresholds"]["auto_select"] = 0.95
    with pytest.raises(ValueError):
        cal._validate_selected_policy(policy)


def test_search_records_training_rejection_when_no_policy_can_avoid_clear_regression(tmp_path):
    import json
    import calibrate_thresholds as cal
    root, training, manifest, _ = cli_fixture(tmp_path)
    runs = [json.loads(line) for line in training.read_text().splitlines()]
    for run in runs:
        if run["case_id"] == "db_constraint_clear":
            run["resolution"]["evaluation_snapshot"]["parsed"]["evidence_sufficiency"] = 0.82
    training.write_text("".join(json.dumps(run) + "\n" for run in runs))
    out = tmp_path / "search"
    assert cal.main(["search", "--cases-dir", str(root / "cases"), "--loop-cases-dir", str(root / "cases_loop"),
                     "--runs-file", str(training), "--manifest", str(manifest), "--out-dir", str(out)]) == 0
    policy = json.loads((out / "selected-policy.json").read_text())
    assert not policy["training"]["adoption"]["accepted"]
    assert "clear completions decreased" in policy["training"]["adoption"]["reasons"]
    assert cal.REFERENCE_POLICY["thresholds"]["sufficiency"] == 0.6


def test_summary_reports_all_ask_expected_situations_and_clear_failure_examples():
    import calibrate_thresholds as cal
    missing = calibration_case("missing", "info_missing")
    preference = calibration_case("preference", "preference_needed")
    removed = calibration_case("removed", derived={"base": "clear", "perturbation": "evidence_removed"})
    clear = calibration_case("clear")
    runs = (captured_runs(missing, 0.2) + captured_runs(preference, noul=0.9)
            + captured_runs(removed, 0.82) + captured_runs(clear, 0.82))
    ranked = cal.rank_policies([missing, preference, removed, clear], runs)
    strict = next(row for row in ranked if row["thresholds"] == {**_thresholds(), "sufficiency": 0.85}
                  and row["gate_order"] == "human_first")
    assert strict["counts"]["ask_expected"] == 9
    assert strict["counts"]["asked_ok"] == 9
    assert {failure["case_id"] for failure in strict["failures"]
            if failure["kind"] == "unnecessary_ask"} == {"clear"}


def test_describe_rejects_nonobject_snapshot_parsed_values(tmp_path):
    import json
    import calibrate_thresholds as cal
    runs = tmp_path / "runs.jsonl"
    runs.write_text(json.dumps({"case_id": "clear", "resolution": {
        "evaluation_snapshot": {"schema_version": 1, "parsed": [{}], "thresholds": _thresholds(),
                                "gate_order": "human_first", "evaluated_option_ids": ["option_a", "option_b"]}}}) + "\n")
    assert cal.main(["describe", "--runs-file", str(runs), "--out-file", str(tmp_path / "description.json")]) == 2


@pytest.fixture(scope="module")
def frozen_calibration_policy(tmp_path_factory):
    import json
    import calibrate_thresholds as cal
    tmp = tmp_path_factory.mktemp("frozen_calibration")
    root, training, manifest, cases = cli_fixture(tmp)
    out = tmp / "search"
    assert cal.main(["search", "--cases-dir", str(root / "cases"), "--loop-cases-dir", str(root / "cases_loop"),
                     "--runs-file", str(training), "--manifest", str(manifest), "--out-dir", str(out)]) == 0
    return json.loads((out / "selected-policy.json").read_text()), manifest, cases


def test_search_rejects_training_content_copied_under_new_validation_id(tmp_path):
    import json
    import hashlib
    import calibrate_thresholds as cal
    root, training, manifest, _ = cli_fixture(tmp_path)
    data = json.loads(manifest.read_text())
    entry = data["cases"][0]
    case = json.loads((root / "cases" / "db_info_missing.json").read_text())
    case["id"] = entry["id"]
    case_path = manifest.parent / entry["path"]
    case_path.write_text(json.dumps(case))
    entry["sha256"] = hashlib.sha256(case_path.read_bytes()).hexdigest()
    manifest.write_text(json.dumps(data))
    out = tmp_path / "search"
    assert cal.main(["search", "--cases-dir", str(root / "cases"), "--loop-cases-dir", str(root / "cases_loop"),
                     "--runs-file", str(training), "--manifest", str(manifest), "--out-dir", str(out)]) == 2
    assert not out.exists()


@pytest.mark.parametrize("change", ["no_hashes", "hash_value", "aggregate_hash", "hash_keys", "reference_empty",
    "case_set", "phase_set", "zero_valid", "negative_coverage", "coverage_bool", "coverage_total",
    "complete_false", "unavailable_count", "missing_count", "unsafe_range", "clear_correct_range",
    "clear_partition", "confirmed_correct", "db_pass_range", "evidence_range", "asked_range", "count_bool"])
def test_frozen_policy_rejects_inconsistent_hashes_coverage_and_counts(frozen_calibration_policy, change):
    import calibrate_thresholds as cal
    policy = copy.deepcopy(frozen_calibration_policy[0])
    reference, candidate = policy["training"]["reference"], policy["training"]["candidate"]
    key = next(iter(candidate["coverage"]))
    phase = candidate["coverage"][key]["1"]
    counts = candidate["counts"]
    if change == "no_hashes": policy.pop("training_case_hashes")
    elif change == "hash_value": policy["training_case_hashes"][key] = "invalid"
    elif change == "aggregate_hash": policy["training_case_hash"] = "0" * 64
    elif change == "hash_keys": policy["training_case_hashes"].pop(key)
    elif change == "reference_empty": reference["coverage"] = {}
    elif change == "case_set": candidate["coverage"]["other"] = candidate["coverage"].pop(key)
    elif change == "phase_set": candidate["coverage"][key]["2"] = copy.deepcopy(phase)
    elif change == "zero_valid": phase.update(valid=0, missing=3)
    elif change == "negative_coverage": phase.update(valid=4, missing=-1)
    elif change == "coverage_bool": phase["unavailable"] = False
    elif change == "coverage_total": phase["missing"] = 1
    elif change == "complete_false": candidate["complete"] = False
    elif change == "unavailable_count": counts["unavailable"] = 1
    elif change == "missing_count": counts["missing"] = 1
    elif change == "unsafe_range": counts["unsafe"] = 88
    elif change == "clear_correct_range": counts["clear_correct"] = counts["clear_completed"] + 1
    elif change == "clear_partition": counts["unnecessary_asks"] = 1
    elif change == "confirmed_correct": counts["confirmed_correct"] -= 1
    elif change == "db_pass_range": counts["db_loop_passes"] = 4
    elif change == "evidence_range": counts["evidence_misses"] = 22
    elif change == "asked_range": counts["asked_ok"] = counts["ask_expected"] + 1
    elif change == "count_bool": counts["unsafe"] = False
    with pytest.raises(ValueError):
        cal._validate_selected_policy(policy)


def test_manifest_rejects_overlapping_acceptable_and_forbidden_selections(tmp_path):
    import json
    import hashlib
    import calibrate_thresholds as cal
    _, _, manifest, _ = cli_fixture(tmp_path)
    data = json.loads(manifest.read_text())
    entry = data["cases"][1]
    path = manifest.parent / entry["path"]
    case = json.loads(path.read_text())
    case["expectations"]["forbidden_selections"] = case["expectations"]["acceptable_selections"]
    path.write_text(json.dumps(case))
    entry["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        cal.load_validation_manifest(manifest)


@pytest.mark.parametrize("bad_id", [[], {}, None, 1, True])
def test_validate_returns_input_error_for_nonstring_case_id(tmp_path, frozen_calibration_policy, bad_id):
    import json
    import calibrate_thresholds as cal
    policy, manifest, cases = frozen_calibration_policy
    policy_file = tmp_path / "policy.json"
    policy_file.write_text(json.dumps(policy))
    run = captured_runs(cases[0], 0.2)[0]
    run["case_id"] = bad_id
    run["resolution"]["evaluation_snapshot"]["thresholds"] = policy["thresholds"]
    run["resolution"]["evaluation_snapshot"]["gate_order"] = policy["gate_order"]
    runs = tmp_path / "runs.jsonl"
    runs.write_text(json.dumps(run) + "\n")
    out = tmp_path / "validation"
    assert cal.main(["validate", "--policy-file", str(policy_file), "--manifest", str(manifest),
                     "--runs-file", str(runs), "--out-dir", str(out)]) == 2
    assert not out.exists()
