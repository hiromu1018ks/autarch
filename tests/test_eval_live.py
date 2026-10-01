"""Live full-flow smoke test. Costs one real agent run.

Run explicitly:

    AUTARCH_EVAL_LIVE=1 AUTARCH_AGENT_MODEL=<model> \
        python3 -m pytest tests/test_eval_live.py -v
"""

import json
import os
from pathlib import Path

import pytest

import run_full_flow

pytestmark = pytest.mark.skipif(
    os.environ.get("AUTARCH_EVAL_LIVE") != "1",
    reason="set AUTARCH_EVAL_LIVE=1 to run the live full-flow smoke test",
)

SCENARIOS_DIR = Path(__file__).resolve().parent.parent / "evals" / "scenarios"


def test_live_full_flow_database(tmp_path):
    exit_code = run_full_flow.main([
        "--scenarios-dir", str(SCENARIOS_DIR),
        "--out-dir", str(tmp_path),
        "--scenario", "database",
        "--agent-model", os.environ.get("AUTARCH_AGENT_MODEL", "sonnet"),
    ])
    assert exit_code == 0
    record = json.loads(
        (tmp_path / "full_flow_runs.jsonl").read_text().strip()
    )
    assert record["status"] == "ok", record
