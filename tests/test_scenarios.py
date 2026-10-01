import json
from pathlib import Path

import case_schema

SCENARIOS_DIR = Path(__file__).resolve().parent.parent / "evals" / "scenarios"

EXPECTED_SITUATIONS = {
    "database": "constraint_clear",
    "authentication": "preference_needed",
    "test_framework": "constraint_clear",
    "dependency": "info_missing",
    "deployment": "preference_needed",
}


def test_five_scenarios_exist():
    assert {p.name for p in SCENARIOS_DIR.iterdir() if p.is_dir()} == set(EXPECTED_SITUATIONS)


def test_scenario_expectations_valid_and_prompt_mentions_artifacts():
    for name, situation in EXPECTED_SITUATIONS.items():
        scenario = SCENARIOS_DIR / name
        exp = json.loads((scenario / "expectations.json").read_text(encoding="utf-8"))
        assert case_schema.validate_scenario_expectations(exp) == [], name
        assert exp["situation"] == situation
        prompt = (scenario / "prompt.md").read_text(encoding="utf-8")
        assert "/autarch" in prompt
        assert "autarch-state.json" in prompt
        assert "autarch-resolution.json" in prompt
        assert any((scenario / "fixture").iterdir()), f"{name}: fixture is empty"
