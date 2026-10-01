# Autarch

**English** | [日本語](README.ja.md)

> **Autarch turns uncertainty into structured decisions.**

`/autarch` is a decision skill for [Claude Code](https://claude.com/claude-code). When a coding agent stops and asks you something like *"Should I use SQLite or PostgreSQL?"* — and you don't have the expertise (or energy) to compare — run `/autarch`. The agent builds neutral alternatives and evaluation criteria, [Jev](https://typesafe.ai/) (a System One model by TypeSafe AI) evaluates them, and a deterministic policy either adopts the best option and continues working, or hands you back one small question only you can answer.

```text
Agent:  "DBはPostgreSQLとSQLiteのどちらにしますか？"
User:   /autarch
Autarch: SQLite selected — local single-user use case needs no external
         server. Jev confidence: 97%
Agent:  "Understood. Continuing with SQLite."
```

## How it works

Three roles, deliberately separated:

| Role | Responsibility |
|---|---|
| **Agent** | Captures the pending question, generates 2–5 *neutral* alternatives, gathers evidence, defines evaluation criteria |
| **Jev** | Evaluates: one Noul question (is human preference required?), one Choice question (which option?), and one Score question per criterion × option |
| **decide.py** | Validates input, redacts secrets, calls the API, applies the decision policy deterministically, logs the decision |

The engine is a **single stdlib-only Python script** — no packages to install, no dependencies to drift. The deterministic part (thresholds, gates, redaction, logging) lives in code, not in the agent's judgment.

Decision material sent to Jev (question, alternatives, evidence, criteria) is always written in **English** for evaluation reliability, whatever language you converse in — results and any question returned to you come back in your conversation language.

### Decision policy

After input validation and hard-constraint checks, the Jev evaluation runs through these gates, in order:

1. **Provider error** → `PROVIDER_UNAVAILABLE` — never auto-select on a failed/unusable API response
2. **Human-preference gate** (Noul ≥ 0.70) → `ASK_USER` — if the decision depends on your taste or intent, Autarch refuses to choose even at high confidence
3. **Evidence sufficiency** (< 0.60 with blocker confidence ≥ 0.50) → `ASK_USER` — investigate missing facts or repair biased material once; an existing revision exhausts that round. For preference or tie blockers, ask one deciding question.
4. **Choice/Score consistency** — if the Choice winner and the weighted Score winner disagree → `ASK_USER`
5. **Probability gap** — if the top two options are within 0.15 of each other → `ASK_USER`
6. **Confidence bands** — ≥ 0.85 → `SELECT_OPTION`, ≥ 0.60 → `SELECT_OPTION_WITH_CAUTION`, else → `ASK_USER`

When the decision comes back to you, Autarch does **not** repeat the original technical question. It reduces the decision to the smallest question only you can answer (usually one distinguishing factor).

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

The skill drives `scripts/decide.py`; you can also run it directly:

```bash
python3 skills/autarch/scripts/decide.py --state-file state.json \
  [--model jev-latest] [--auto-select 0.85] [--review 0.60] \
  [--min-gap 0.15] [--human-preference 0.70] \
  [--sufficiency 0.60] [--blocker-confidence 0.50] \
  [--timeout 30] [--endpoint https://api.typesafe.ai]
```

- Input: a decision state JSON (`goal`, `question`, `alternatives[2–5]`, optional `criteria[0–8]`)
- stdout: exactly one resolution JSON (`decision`, `rule`, `selected_option`, `confidence`, `probabilities`, `score_summary`, ...)
- Exit codes: `0` a resolution was produced (including `PROVIDER_UNAVAILABLE`) · `2` usage/input error · `1` internal error

See [SKILL.md](skills/autarch/SKILL.md) for the full state schema and execution flow.

## Privacy & secrets

- The agent is instructed never to read `.env` files, credentials, private keys, or secret stores as evidence.
- Before anything is sent, the engine recursively redacts sensitive keys (`password`, `token`, `api_key`, ...) and secret-looking string patterns (`sk-...`, `ghp_...`, AWS keys, `Bearer ...`, private key blocks). Only the replacement count is reported.
- The decision log (`~/.autarch/decisions.jsonl`) stores a sanitized question summary, option/criterion ids, and numbers — never the full state, never secret values.
- Error messages never include secret values.

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install pytest

.venv/bin/python3 -m pytest tests/            # 107 tests, no network needed
AUTARCH_LIVE=1 .venv/bin/python3 -m pytest tests/test_live.py -v   # optional: real API smoke test
```

Project layout:

```text
skills/autarch/SKILL.md        # the skill (agent-facing instructions)
skills/autarch/scripts/decide.py  # stdlib-only engine
tests/                          # pytest suite (network-free) + live test
docs/                           # requirements & design docs (Japanese)
```

## Documentation

- [Requirements (Japanese)](docs/Autarch_requirements_v0.2.md) — product requirements, KPIs, roadmap
- [Implementation design](docs/superpowers/specs/2026-09-30-autarch-skill-implementation-design.md) — state schema, API contract, policy details
- [Implementation plan](docs/superpowers/plans/2026-09-30-autarch-skill.md) — the 11-task TDD plan that produced this code

## License

[MIT](LICENSE)
