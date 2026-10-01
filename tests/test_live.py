"""Live integration tests.

Run explicitly with a real key:

    AUTARCH_LIVE=1 TYPESAFE_API_KEY=... python3 -m pytest tests/test_live.py -v
"""

import json
import os
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = (
    Path(__file__).resolve().parent.parent / "skills" / "autarch" / "scripts"
)
sys.path.insert(0, str(SCRIPTS_DIR))

import decide  # noqa: E402

pytestmark = pytest.mark.skipif(
    os.environ.get("AUTARCH_LIVE") != "1"
    or not os.environ.get("TYPESAFE_API_KEY"),
    reason="set AUTARCH_LIVE=1 and TYPESAFE_API_KEY to run live tests",
)

STATE = {
    "goal": "Pick a note-taking approach for a single local user",
    "question": (
        "Which note-taking approach best fits a local single-user workflow?"
    ),
    "known_constraints": ["works offline"],
    "environment": {"os": "linux"},
    "evidence": ["notes are plain text", "no collaboration needed"],
    "alternatives": [
        {
            "id": "plain_files",
            "name": "Plain files",
            "description": "Notes as plain text files in one folder.",
            "advantages": ["no lock-in"],
            "disadvantages": ["no structure"],
            "assumptions": [],
        },
        {
            "id": "structured_app",
            "name": "Structured app",
            "description": "A dedicated app with linking and search.",
            "advantages": ["search"],
            "disadvantages": ["vendor lock-in"],
            "assumptions": [],
        },
    ],
    "criteria": [
        {
            "id": "fit",
            "name": "Requirement fit",
            "rubric": ["Poor fit", "Acceptable fit", "Excellent fit"],
        }
    ],
}


def test_live_end_to_end(tmp_path, capsys):
    state_file = tmp_path / "state.json"
    state_file.write_text(json.dumps(STATE), encoding="utf-8")
    exit_code = decide.main([f"--state-file={state_file}"])
    captured = capsys.readouterr()
    assert exit_code == 0
    output = json.loads(captured.out)
    assert output["decision"] in {
        "SELECT_OPTION",
        "SELECT_OPTION_WITH_CAUTION",
        "ASK_USER",
    }
    assert output["detail"] is None
    assert output["probabilities"] is not None
    assert output["human_preference_probability"] is not None


THIN_STATE = {
    "goal": "Pick a task runner for a small build",
    "question": "Which task runner fits this repository?",
    "known_constraints": [],
    "environment": {},
    "evidence": [],
    "alternatives": [
        {
            "id": "shell_script",
            "name": "Shell script",
            "description": "One plain bash script that runs the build steps.",
            "advantages": [],
            "disadvantages": [],
            "assumptions": [],
        },
        {
            "id": "make",
            "name": "Make",
            "description": "Classic makefile-driven build orchestration.",
            "advantages": [],
            "disadvantages": [],
            "assumptions": [],
        },
    ],
    "criteria": [],
}


def test_live_new_questions_accepted(tmp_path, capsys):
    state_file = tmp_path / "thin.json"
    state_file.write_text(json.dumps(THIN_STATE), encoding="utf-8")
    exit_code = decide.main([f"--state-file={state_file}"])
    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    # PROVIDER_UNAVAILABLE here means Jev rejected the new question shapes.
    assert output["decision"] in {
        "SELECT_OPTION",
        "SELECT_OPTION_WITH_CAUTION",
        "ASK_USER",
    }
    assert isinstance(output["evidence_sufficiency"], (int, float))
    if output["rule"] in ("evidence_insufficient", "investigation_exhausted"):
        assert output["blocker_class"] in decide.BLOCKER_CLASSES
        assert isinstance(output["blocker_confidence"], (int, float))
