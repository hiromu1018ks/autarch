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
