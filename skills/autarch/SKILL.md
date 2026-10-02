---
name: autarch
description: Resolve a decision by generating alternatives and evaluating them with Jev.
disable-model-invocation: true
---

# Autarch — structured decision resolution

Autarch converts an unresolved decision into a selected option. You (the
agent) build the decision material; Jev (TypeSafe AI System One) evaluates
it; `decide.py` applies the decision policy deterministically. Run this
skill only when the user explicitly invokes `/autarch`. Never invoke it on
your own initiative.

## Execution flow

### Step 1 — Capture the question

Identify the decision currently blocking progress: the question the agent
asked most recently, the conversation context, and the user's original
goal. If the user passed a question as arguments to `/autarch`, use that
question directly.

### Step 2 — Normalize the decision

Restate the question as one clear decision problem: what is being chosen
and why. Do not name a preferred answer.

Example:

- Original: "JWTとCookieどちらにしますか？"
- Decision problem: "Select the authentication state strategy that best
  matches the current project."

Write all decision material in English — `goal`, `question`,
`known_constraints`, `environment`, `evidence`, `alternatives`, and
`criteria`, `hard_constraints`, and `evidence_records` — regardless of the conversation language. Jev's documented
interface and examples are English, and evaluation reliability is
strongest there; a fixed language also keeps evaluations comparable
across decisions. Preserve exact wording as a verbatim quote in the
original language only when the quoting itself is the evidence, adding
a one-line English gloss. User-facing output — the resolution report
and any ASK_USER question — stays in the user's conversation language.

Separate explicit mandatory requirements from preferences. Register every
explicit mandatory requirement in `hard_constraints`; put preferences and
priorities in `criteria`. If it is unclear whether a condition is mandatory,
ask about the user's intent rather than silently promoting a preference.

### Step 3 — Generate alternatives (2–5, neutral)

Generate 2 to 5 materially different, feasible options; default to 3. If
the pending question offers two options, add a materially different third
option (including "keep the current approach") when one exists. Exclude
obviously unreasonable options and mere rewordings of another option.

Generate alternatives neutrally.

Do not describe any option as recommended, best, preferred,
safer, simpler, superior, or inferior before Jev evaluation
unless that statement is directly established by evidence.

Describe every alternative using the same structure and
comparable level of detail.

Each alternative uses the same schema:

```json
{
  "id": "machine_readable_id",
  "name": "Display Name",
  "description": "One-sentence description.",
  "advantages": ["..."],
  "disadvantages": ["..."],
  "assumptions": ["..."]
}
```

Rules for `id`: unique within the state, non-empty, at most 64 characters,
only `A-Za-z0-9._-`, must not start with a symbol, must not contain `__`.

### Step 4 — Gather evidence

Investigate before writing the state. Before you build the state JSON,
check the repository, project documentation, and — when relevant —
external documentation or web search for facts the comparison needs.
Facts you can obtain by investigation belong in the state now;
do not defer them to a post-evaluation investigation round. Only the
user's own preference, plans, or intent is exempt:
never investigate those — return them as a question.

Collect only the context needed to compare the options (for coding
decisions: repository structure, existing dependencies, configuration,
requirements, constraints).

Do not read or include .env files, credential files,
private keys, authentication tokens, or secret stores
as evidence. Apply the same exclusion to newly discovered evidence.

For each hard constraint, assess every original alternative ID. Record
confirmed facts separately from inference in `evidence_records`, with a
non-empty `fact`, a `source` (file and location, official documentation URL,
or identifier of an explicit user statement), a timezone-aware RFC 3339
`checked_at`, and `kind` of `verified` or `inference`. Recheck changing facts at decision time
(for example prices and available features); the engine validates timestamps
but does not open sources or enforce a fixed freshness limit.

Use assessment `status` of `met`, `violated`, or `unknown`, with a
unique list of existing `evidence_ids`. Both `met` and `violated` require
at least one relevant `verified` record that establishes that result;
inference alone must remain `unknown`. An unconfirmed result stays
`unknown`, with an empty list or references to existing evidence. Never
turn absence of evidence into `met`. Keep `known_constraints` and the
string array `evidence` for context; they do not replace structured checks.

### Step 5 — Generate criteria

Generate the evaluation criteria this decision actually needs (0–8). Each
criterion has an ordered rubric whose levels run from worst to best, with
at least 2 levels. `weight` is optional and defaults to 1.0.

```json
{
  "id": "requirement_fit",
  "name": "Requirement fit",
  "weight": 0.35,
  "rubric": ["Very poor fit", "Poor fit", "Acceptable fit", "Good fit", "Excellent fit"]
}
```

Choose criteria for the decision at hand; do not default to a fixed
coding-specific set.

### Step 6 — Write the state JSON

```bash
STATE_FILE=$(mktemp /tmp/autarch-state-XXXXXX.json)
```

State schema (`goal`, `question`, `alternatives` required; `criteria` may
be empty or omitted; include `hard_constraints` and `evidence_records`
when mandatory requirements apply):

```json
{
  "goal": "the user's original goal",
  "question": "the normalized decision problem",
  "known_constraints": ["..."],
  "environment": {},
  "evidence": ["..."],
  "alternatives": ["...as defined in Step 3..."],
  "criteria": ["...as defined in Step 5..."]
}
```

When present, `hard_constraints` and `evidence_records` must be arrays,
not null; non-empty constraints require `evidence_records`. Each constraint
has `id`, non-empty `description`, and `assessments` covering exactly all
original alternative IDs.
`assessments` must be an object keyed by option id, never an array:

```json
"hard_constraints": [
  {
    "id": "offline",
    "description": "Must work fully offline.",
    "assessments": {
      "sqlite": {"status": "met", "evidence_ids": ["runtime_confirmation"]},
      "json": {"status": "unknown", "evidence_ids": []}
    }
  }
]
```

Each record has `id` and the fields in Step 4.
Constraint IDs and evidence IDs follow the Step 3 ID rules and are unique
within their respective arrays. See the complete runnable state example in
[README.md](../../README.md#evidence-backed-hard-constraints).

Omitting `hard_constraints` uses legacy mode. The legacy path has no evidence-backed exclusion guarantee.
An explicit empty array uses structured mode and treats every option as
eligible; it is appropriate only when there are no mandatory requirements.
The engine guarantees the input contract and filtering, not source accuracy
or that a cited fact actually proves the assessment. It evaluates a redacted
copy and leaves the original state unchanged. Keep secrets out of IDs,
facts, sources, and revision summaries; recursive redaction also covers the
new fields.

### Step 7 — Run decide.py

Run the engine from this skill's directory (`scripts/decide.py` sits next
to this SKILL.md):

```bash
SKILL_DIR="$(cd "$(dirname "<path to this SKILL.md>")" && pwd)"
python3 "$SKILL_DIR/scripts/decide.py" --state-file "$STATE_FILE"
```

Requires the `TYPESAFE_API_KEY` environment variable. Optional flags:
`--model jev-latest --auto-select 0.85 --review 0.60 --min-gap 0.15
--human-preference 0.70 --sufficiency 0.60 --blocker-confidence 0.50
--timeout 30 --endpoint https://api.typesafe.ai`.

Exit codes: `0` = a resolution JSON was printed to stdout; `2` = usage
error, missing state file, or malformed JSON; `1` = internal error. For
exit codes other than 0, do not invent a decision — report that Autarch
failed to execute.

### Step 8 — Read the resolution JSON

stdout contains exactly one JSON object with: `decision`, `rule`,
`selected_option`, `confidence`, `probability`, `probabilities`,
`human_preference_probability`, `score_summary`, `evidence_sufficiency`,
`blocker_class`, `blocker_confidence`, `reason`, `detail`, `model`,
`constraint_check`.

`constraint_check` reports `mode` (`legacy` or `structured`),
`eligible_option_ids`, `excluded_options` (each with `option_id`,
`constraint_ids`, and `evidence_ids`), and `unknown_assessments` (each with
`option_id` and `constraint_id`). It is null for invalid input. Violated
options are excluded; unknown conditions on non-violated options stop all
comparison before Jev. Unknown conditions on already excluded options do
not require investigation. Only options with all conditions `met` are
eligible, and at least two are required for comparison. Pre-comparison
stops have null Jev values and empty probabilities and scores; do not
attach Jev confidence to them.

`probabilities` are a probability distribution over the alternatives
(they sum to about 1). They are NOT scores — never present them as
"72 points" or similar. Multi-criterion evaluation lives in
`score_summary`.

### Step 9 — SELECT_OPTION

Adopt `selected_option` and continue the original task. Tell the user
briefly which option was chosen, the one-line reason, and the Jev
confidence.

### Step 10 — SELECT_OPTION_WITH_CAUTION

Same as Step 9, but state the uncertainty first in one short sentence
(for example, which assumption the choice depends on).

### Step 11 — ASK_USER

Do NOT repeat the original technical question. Dispatch on `rule` and
`blocker_class`:

The engine returns `evidence_insufficient` when the missing piece is
investigable (blocker `facts_missing` or `material_bias`) or when the
blocker classification itself is below 0.50 confidence (the engine then
treats the blocker as investigable), and `human_preference` when what is
missing is your intent (blocker `user_preference_unknown` or
`balanced_tie`, or sufficient evidence with high preference dependence).
Follow the rule below either way.

Dispatch on the `rule` first; the blocker class is secondary context.
When the two disagree — an intent-class blocker under rule
`evidence_insufficient` — the engine has fallen back to the investigation
side because the blocker classification itself was below 0.50 confidence,
so investigate.

All constraint verification, evidence investigation, and material repair
use one shared revision round. If `revision` already exists, do not
investigate or repair and re-run again; report confirmed facts and remaining
unknowns, then ask one deciding question. Do not delete or reset `revision`
to gain another round.

**`constraint_unverified`, blocker `facts_missing`, no `revision` —
investigate once, then re-run.** Use `constraint_check.unknown_assessments`
to identify the non-excluded options and conditions to verify. Check
repository sources first, then external documentation or web search when
needed. Update `evidence_records` and the affected `hard_constraints`
assessments using Step 4; retain `unknown` if verification fails. Apply
secret exclusion and recursive redaction to all new material. Set
`"revision": {"round": 1, "action": "investigation", "summary": "..."}`
and re-run decide.py exactly one more time. If verification reveals a
question about the user's intent, stop investigating and ask that one
question instead. Follow Step 12 if the re-run returns
`PROVIDER_UNAVAILABLE`; never call Jev again.

**Rule `evidence_insufficient`, no `revision`** — investigate once, then re-run.
This rule covers blocker `facts_missing` and `material_bias`, and the
engine's low-confidence fallback, which sends any blocker class here
when its classification confidence is below 0.50. Check repository
configuration, code, and documentation first; if the repository does not
answer the question, consult external documentation or web search. This whole
investigation is one round. Append each discovered fact to `evidence`
as a string with its source noted in one short phrase (example:
`"the app runs as a single local CLI tool (pyproject.toml, README)"`).
Never invent facts — if nothing is found, continue anyway. Then add to
the state:

```json
"revision": {"round": 1, "action": "investigation",
             "summary": "what you checked and what you found"}
```

and re-run decide.py on the updated state exactly one more time. If
that second run returns `PROVIDER_UNAVAILABLE`, follow Step 12 — do
not call Jev again.

**`evidence_insufficient`, blocker `material_bias`, no `revision` —
rebalance the material in the same single round.** Rewrite the
alternative descriptions with the same structure and comparable level
of detail, neutrally. Set `"revision": {"round": 1, "action":
"material_fix", "summary": "..."}` and re-run decide.py once.

**`investigation_exhausted` — the revision round is spent and the
evidence or a hard constraint is still unverified.** Use
`constraint_check.unknown_assessments` when present. Return to the user without another
decide.py run: list what was confirmed (verified facts with sources)
and what remains unverified, then ask the single deciding question as
below.

**Rule `human_preference`** — the decision depends on the user's taste,
plans, or a deciding priority (typically blocker `user_preference_unknown` or `balanced_tie`).
Ask for that preference or priority directly instead of technical details.

**Any other `rule`** (`low_confidence`, `probability_gap`,
`choice_score_disagreement`) — using `rule`, `score_summary`,
`probabilities`, and your evidence, reduce the decision to the
smallest question only the user can answer — usually one
distinguishing factor. Present the options as a short list with
one-line neutral descriptors, name the deciding factor, and ask only
that. Example:

```text
Autarch could not decide this on technical merit alone.

The difference comes down to one thing: whether this system will
also be used from mobile apps or external APIs in the future.

A. JWT — suited to multiple clients / external APIs
B. Session Cookie — simplest for this same-origin web app

Do you have such a plan, yes or no?
```

Whatever the branch: never select an option yourself when the engine
says ASK_USER.

### Step 12 — PROVIDER_UNAVAILABLE

State that Jev could not be reached or returned an unusable response (see
`detail`), and that no automatic selection was made. Do not pick an option
yourself unless the user asks you to decide without Autarch.

### Step 13 — INSUFFICIENT_OPTIONS

**`constraint_candidates_insufficient`** — fewer than two eligible options
remain after hard-constraint checks. Read `constraint_check` to explain
which options were excluded and why. Do not automatically adopt a lone
eligible option. If a materially different candidate can meet the existing
requirements, add it and assess it against every hard constraint before
running Steps 6–7 again. Otherwise ask the user one question about the
requirements. Never relax a hard constraint without the user's instruction.
Do not automatically repeat candidate generation or run a regeneration loop.

**`invalid_state`** — the state failed validation (see `detail`). Fix the state — usually the
alternatives structure or ids — and run Steps 6–7 again. If materially
different options cannot be constructed, tell the user why the decision
cannot be structured and ask how to proceed.
