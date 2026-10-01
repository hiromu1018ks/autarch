#!/usr/bin/env python3
"""Offline synthetic replay of the ORIGINAL saved auth state; never a live result."""
import contextlib
import copy
import hashlib
import io
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
sys.path[:0] = [str(REPO / 'skills/autarch/scripts'), str(REPO / 'tests'), str(REPO / 'evals')]
import decide
import judging
from test_decide import answers_body, make_answers


def write_json(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    source = REPO / 'evals/results/hard-constraints-calibration-2026-10-01/final/full_flow/authentication/autarch-state.json'
    raw = source.read_bytes()
    state = json.loads(raw)
    original = copy.deepcopy(state)
    assert decide.validate_state(state) == []
    evaluated, constraints, early = decide.check_constraints(state)
    assert early is None
    # Existing helper defaults: first candidate, human_preference=.1,
    # confidence=.9, sufficiency=.9, winner Score=2, other Scores=1.
    body = answers_body(make_answers(evaluated))
    parsed = decide.parse_answers(body, evaluated)
    expected_scores = {'server_session_cookie': 2.0, 'stateless_jwt_bearer': 1.0, 'http_basic_per_request': 1.0}
    assert parsed['scores']['credential_and_session_security'] == expected_scores
    assert state == original
    stdout, stderr = io.StringIO(), io.StringIO()
    calls = []
    def synthetic_response(payload, endpoint, timeout):
        calls.append(payload)
        return 200, body
    with patch.dict('os.environ', {'TYPESAFE_API_KEY': 'synthetic-offline-placeholder'}), \
         patch.object(decide, 'send_request', synthetic_response), \
         patch.object(decide, 'default_log_path', lambda: OUT / 'synthetic_decisions.jsonl'), \
         contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        exit_code = decide.main(['--state-file', str(source), '--capture-evaluation'])
    resolution = json.loads(stdout.getvalue())
    assert exit_code == 0 and len(calls) == 1
    assert resolution['evaluation_snapshot']['parsed'] == parsed
    assert source.read_bytes() == raw
    expectations = json.loads((REPO / 'evals/scenarios/authentication/expectations.json').read_text())
    verdict = judging.judge_full_flow(state, decide.validate_state(state), resolution, expectations)
    write_json('synthetic_response.json', json.loads(body))
    write_json('synthetic_parsed.json', parsed)
    write_json('synthetic_resolution.json', resolution)
    write_json('synthetic_replay_provenance.json', {
        'kind': 'synthetic_offline_replay', 'live_outcome': False,
        'provider_calls': 0, 'agent_calls': 0,
        'main_send_request_stub_calls': len(calls),
        'code_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip(),
        'source_state': str(source.relative_to(REPO)),
        'source_state_sha256': hashlib.sha256(raw).hexdigest(),
        'synthetic_response_sha256': hashlib.sha256(body).hexdigest(),
        'answer_generator': 'tests/test_decide.py make_answers defaults, answers_body',
        'thresholds': resolution['evaluation_snapshot']['thresholds'],
        'gate_order': resolution['evaluation_snapshot']['gate_order'],
        'valid_state_errors': [], 'constraint_check': constraints,
        'expected_credential_scores': expected_scores, 'credential_scores_preserved': True,
        'decision': resolution['decision'], 'rule': resolution['rule'],
        'synthetic_verdict': verdict, 'main_exit_code': exit_code,
        'stderr': stderr.getvalue(),
        'limitation': 'Invented numeric answers prove parser/runtime processing only. Their selection fails the real authentication ASK_USER expectation; no live agent/provider behavior or quality claim follows.'
    })
    print(json.dumps({'kind': 'synthetic_offline_replay', 'provider_calls': 0,
                      'credential_scores_preserved': True, 'decision': resolution['decision'],
                      'rule': resolution['rule'], 'synthetic_verdict': verdict}))

if __name__ == '__main__':
    main()
