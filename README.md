# Autarch

**English** | [日本語](README.ja.md)

> **Autarch turns uncertainty into structured decisions.**

Autarch is a decision skill for [Claude Code](https://claude.com/claude-code). Run `/autarch` when you want to delegate a decision. The agent builds alternatives, requirements, and evidence. A Python engine checks mandatory requirements before [Jev](https://typesafe.ai/), TypeSafe AI's System One model, evaluates the eligible options. The result can select an option, trigger one investigation, or ask you for a deciding preference.

```text
Agent:  "DBはPostgreSQLとSQLiteのどちらにしますか？"
User:   /autarch
Autarch: SQLite selected — local single-user use case needs no external
         server. Jev confidence: 97%
Agent:  "Understood. Continuing with SQLite."
```

## Usage

After installation, enter `/autarch` when the agent asks you to make a decision. You can also provide the question directly:

```text
/autarch Choose a PDF processing approach. Sending data externally is forbidden. Speed matters.
```

You do not need to write JSON. The agent treats the external-transfer prohibition as a mandatory requirement and speed as an evaluation criterion.

| Situation | What Autarch does |
|---|---|
| An option violates a mandatory requirement | Excludes it before scoring |
| A requirement remains unverified | Stops comparison, investigates once, then evaluates again |
| Evaluation identifies insufficient evidence | Investigates missing facts or repairs biased material, sharing one re-evaluation round |
| Your preference or plans are needed | Asks one deciding question |
| Requirements, evaluation, and confidence meet the selection policy | Adopts an option and continues the original task |

Constraint verification, evidence investigation, and material repair share one re-evaluation round.
State any mandatory requirements when you invoke the skill. Unverified facts stay unverified, and the agent does not relax requirements on its own. See [Install](#install) for setup.

## How it works

Three roles, deliberately separated:

| Role | Responsibility |
|---|---|
| **Agent** | Captures the question, generates 2–5 neutral options, separates requirements from preferences, gathers sourced evidence, and investigates once when needed |
| **Jev** | Answers two Noul questions (human preference and evidence sufficiency), two Choice questions (best option and blocker class), and one Score question per criterion × option |
| **decide.py** | Validates input and requirements, excludes violations, redacts secrets, sends eligible options to the API, applies the policy, and logs the result |

The engine is a **single stdlib-only Python script** — no packages to install, no dependencies to drift. The deterministic part (thresholds, gates, redaction, logging) lives in code, not in the agent's judgment.

Decision material sent to Jev (question, alternatives, evidence, criteria) is always written in **English** for evaluation reliability, whatever language you converse in — results and any question returned to you come back in your conversation language.

### Decision policy

After input validation and hard-constraint checks, the Jev evaluation runs through these gates, in order:

1. **Provider error** → `PROVIDER_UNAVAILABLE` — never auto-select on a failed/unusable API response
2. **Evidence sufficiency** (< 0.60) → `ASK_USER` — the blocker class routes the outcome: missing-but-investigable facts or biased material trigger one investigation/repair round; a user-preference or tie blocker asks one deciding question. A blocker classification below 0.50 confidence falls back to the investigation round.
3. **Human-preference gate** (Noul ≥ 0.70 with sufficient evidence) → `ASK_USER` — if the decision depends on your taste or intent, Autarch refuses to choose even at high confidence
4. **Choice/Score consistency** — if the Choice winner and the weighted Score winner disagree → `ASK_USER`
5. **Probability gap** — if the top two options are within 0.15 of each other → `ASK_USER`
6. **Confidence bands** — ≥ 0.85 → `SELECT_OPTION`, ≥ 0.60 → `SELECT_OPTION_WITH_CAUTION`, else → `ASK_USER`

When `ASK_USER` identifies missing facts or biased material, the agent investigates or repairs the material and re-runs once. When your intent is needed, or that round does not resolve the issue, it asks one deciding question instead of repeating the original technical question.

Note: Choice `probabilities` are a distribution over alternatives (they sum to ~1), not scores. Multi-criterion evaluation is reported separately in `score_summary`.

### Evidence-backed hard constraints

Before calling Jev, the engine checks explicit mandatory requirements in
`hard_constraints`. Preferences belong in `criteria`. Each requirement must
assess every original option using `met`, `violated`, or `unknown`.
`met` and `violated` require at least one referenced `verified` record in
`evidence_records`; inference alone stays `unknown`. Records include the
fact, source, and a timezone-aware RFC 3339 `checked_at`. The agent rechecks
changing facts at decision time.

This complete minimal state illustrates an example conversation in which
the user explicitly confirmed both implementations' offline operation.
Replace the example statements, source, and timestamp with facts checked
for your actual decision; this is not a claim about an existing project.

```json
{
  "goal": "Store a local personal task list.",
  "question": "Choose a storage format for the offline task tool.",
  "known_constraints": [
    "Must work fully offline."
  ],
  "environment": {},
  "evidence": [
    "The user confirmed that both proposed implementations operate without network calls."
  ],
  "alternatives": [
    {
      "id": "sqlite",
      "name": "SQLite file",
      "description": "Store tasks in a local SQLite database."
    },
    {
      "id": "json",
      "name": "JSON file",
      "description": "Store tasks in a local JSON file."
    }
  ],
  "criteria": [],
  "evidence_records": [
    {
      "id": "runtime_confirmation",
      "fact": "The user confirmed that both the SQLite and JSON implementations operate locally without network calls.",
      "source": "example conversation, user message 2",
      "checked_at": "2026-10-01T09:00:00Z",
      "kind": "verified"
    }
  ],
  "hard_constraints": [
    {
      "id": "offline",
      "description": "Must work fully offline.",
      "assessments": {
        "sqlite": {
          "status": "met",
          "evidence_ids": [
            "runtime_confirmation"
          ]
        },
        "json": {
          "status": "met",
          "evidence_ids": [
            "runtime_confirmation"
          ]
        }
      }
    }
  ]
}
```

A violated option is excluded. An unknown condition on a non-excluded
option stops comparison with `ASK_USER / constraint_unverified`; the agent
investigates once and re-runs with `revision.action=investigation`. This
uses the same single revision round as evidence investigation and material
repair. An existing revision means `investigation_exhausted`: the agent
asks one deciding question rather than starting another investigation.
Unknown remains unknown if nothing can be verified.

With fewer than two eligible options, the engine returns
`INSUFFICIENT_OPTIONS / constraint_candidates_insufficient`, even if one
option remains. The agent adds a feasible alternative or asks about the
requirements; it never relaxes a requirement without your instruction or
starts an automatic candidate-generation loop. `constraint_check` reports
mode, eligible IDs, exclusions with condition/evidence IDs, and remaining
unknown option/condition pairs.

Old states that omit `hard_constraints` retain the legacy evaluation path
without the new evidence-backed exclusion guarantee. An explicit empty
array uses structured mode and makes all options eligible. The engine
checks the input contract and filtering; it cannot guarantee source
accuracy or that a fact establishes a condition. Secret exclusion and
recursive redaction apply to the structured evidence and revision too.

## Install

Requirements: Python 3.10+, [Claude Code](https://claude.com/claude-code), and a TypeSafe AI API key.

```bash
# 1. Install the skill via the skills CLI (auto-detects your agent)
npx skills add hiromu1018ks/autarch

# 2. Add your API key (get one at the TypeSafe AI console)
echo 'export TYPESAFE_API_KEY="your-key"' >> ~/.bashrc
```

<details>
<summary>Manual install (clone + symlink)</summary>

```bash
git clone https://github.com/hiromu1018ks/autarch.git
mkdir -p ~/.claude/skills
ln -s /path/to/autarch/skills/autarch ~/.claude/skills/autarch
```

</details>

Then, in any Claude Code session, when the agent asks a question you want to delegate:

```text
/autarch
```

Autarch runs only when you explicitly invoke it (`disable-model-invocation: true`) — the agent will never trigger it on its own.

## The engine CLI

The skill drives `scripts/decide.py`; you can also run it directly. During normal skill use, the agent writes the state JSON:

```bash
python3 skills/autarch/scripts/decide.py --state-file state.json
```

Defaults: `--model jev-latest`, `--auto-select 0.85`, `--review 0.60`,
`--min-gap 0.15`, `--human-preference 0.70`, `--sufficiency 0.60`,
`--blocker-confidence 0.50`, `--timeout 30`, and `--endpoint https://api.typesafe.ai`.
`--capture-evaluation` includes unrounded numeric signals in `evaluation_snapshot` for offline policy replay against the same state.
These evaluation options are not required for normal `/autarch` use.

- Input: a decision state JSON (`goal`, `question`, `alternatives[2–5]`, optional `criteria[0–8]`)
- stdout: exactly one resolution JSON (`decision`, `rule`, `selected_option`, `confidence`, `probabilities`, `score_summary`, ...)
- Exit codes: `0` a resolution was produced (including `PROVIDER_UNAVAILABLE`, `INSUFFICIENT_OPTIONS`, and validation-related `ASK_USER`) · `2` usage/input error · `1` internal error

See [SKILL.md](skills/autarch/SKILL.md) for the full state schema and execution flow.

## Privacy & secrets

- The agent is instructed never to read `.env` files, credentials, private keys, or secret stores as evidence.
- Before anything is sent, the engine recursively redacts sensitive keys (`password`, `token`, `api_key`, ...) and secret-looking string patterns (`sk-...`, `ghp_...`, AWS keys, `Bearer ...`, private key blocks). Only the replacement count is reported.
- The decision log (`~/.autarch/decisions.jsonl`) stores a sanitized question summary, option/criterion ids, and numbers — never the full state, never secret values.
- `--capture-evaluation` retains only validated numbers, known IDs, and classifications; it does not retain provider free text or extra metadata. Keep secrets out of saved evaluation records too.
- Error messages never include secret values.

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install pytest

.venv/bin/python3 -m pytest tests/            # offline tests; no network needed
AUTARCH_LIVE=1 .venv/bin/python3 -m pytest tests/test_live.py -v   # optional: real API smoke test
```

Project layout:

```text
skills/autarch/SKILL.md        # the skill (agent-facing instructions)
skills/autarch/scripts/decide.py  # stdlib-only engine
tests/                          # pytest suite (network-free) + live test
evals/                          # fixed-state, investigation, constraints, full-flow, calibration
docs/                           # requirements & design docs (Japanese)
```

## Implementation and validation status

As of 2026-10-02, the implementation includes mandatory-requirement preflight checks, one shared investigation/repair round, captured-signal replay, and threshold calibration with separate training and held-out cases.
The offline suite passed 638 tests; three live API tests were skipped. The independent constraint evaluation passed all 21 sequences.
After network recovery, the authentication full-flow returned the expected `ASK_USER` and passed all four checks: coverage, forbidden-option avoidance, decision correctness, and state validity.

**Default thresholds remain unchanged.** The training-selected policy failed held-out validation: three of 30 runs auto-selected despite missing evidence, so the policy was rejected.
The final legacy fixed-state evaluation still had 8 unsafe auto-selections out of 69, compared with 7/69 after the first extension.
Deterministic constraint filtering and the agent's ability to gather sufficient evidence are evaluated separately.
Live investigation of unknown requirements and whether cited facts actually establish an assessment remain open quality concerns.

Evaluation code lives in `evals/`: `run_fixed_state.py` covers fixed states and investigation loops,
`run_constraint_cases.py` covers mandatory requirements, and `run_full_flow.py` exercises the skill end to end.
`calibrate_thresholds.py` provides offline `describe`, `search`, and `validate` commands over captured signals.
Select one policy on training data, validate it on separately frozen cases, and do not reselect after seeing held-out results.
Live runners need network access and an API key and record engine decisions in the normal decision log; full-flow also requires Claude Code.
Use each script's `--help` for its arguments.

- [Current state and remaining issues (Japanese)](STATE.md)
- [Final evaluation and limitations (Japanese)](evals/results/hard-constraints-calibration-2026-10-01/final/notes.md)
- [Calibration results and rejection rationale (Japanese)](evals/results/hard-constraints-calibration-2026-10-01/notes.md)
- [Authentication recheck after network recovery (Japanese)](evals/results/hard-constraints-calibration-2026-10-01/auth-live-recheck-2026-10-02/notes.md)

## Documentation

- [Requirements (Japanese)](docs/Autarch_requirements_v0.2.md) — product requirements, KPIs, roadmap
- [Implementation design](docs/superpowers/specs/2026-09-30-autarch-skill-implementation-design.md) — state schema, API contract, policy details
- [Implementation plan](docs/superpowers/plans/2026-09-30-autarch-skill.md) — the 11-task TDD plan that produced this code
- [Evidence investigation design](docs/superpowers/specs/2026-10-01-info-gap-investigation-design.md) — one investigation round and deciding questions
- [Hard constraints and calibration design](docs/superpowers/specs/2026-10-01-hard-constraints-calibration-design.md) — structured evidence, preflight exclusion, and independent threshold validation

## License

[MIT](LICENSE)
