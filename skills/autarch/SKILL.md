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
`criteria` — regardless of the conversation language. Jev's documented
interface and examples are English, and evaluation reliability is
strongest there; a fixed language also keeps evaluations comparable
across decisions. Preserve exact wording as a verbatim quote in the
original language only when the quoting itself is the evidence, adding
a one-line English gloss. User-facing output — the resolution report
and any ASK_USER question — stays in the user's conversation language.

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

Collect only the context needed to compare the options (for coding
decisions: repository structure, existing dependencies, configuration,
requirements, constraints).

Do not read or include .env files, credential files,
private keys, authentication tokens, or secret stores
as evidence.

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
be empty or omitted):

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

### Step 7 — Run decide.py

Run the engine from this skill's directory (`scripts/decide.py` sits next
to this SKILL.md):

```bash
SKILL_DIR="$(cd "$(dirname "<path to this SKILL.md>")" && pwd)"
python3 "$SKILL_DIR/scripts/decide.py" --state-file "$STATE_FILE"
```

Requires the `TYPESAFE_API_KEY` environment variable. Optional flags:
`--model jev-latest --auto-select 0.85 --review 0.60 --min-gap 0.15
--human-preference 0.70 --timeout 30 --endpoint https://api.typesafe.ai`.

Exit codes: `0` = a resolution JSON was printed to stdout; `2` = usage
error, missing state file, or malformed JSON; `1` = internal error. For
exit codes other than 0, do not invent a decision — report that Autarch
failed to execute.

### Step 8 — Read the resolution JSON

stdout contains exactly one JSON object with: `decision`, `rule`,
`selected_option`, `confidence`, `probability`, `probabilities`,
`human_preference_probability`, `score_summary`, `evidence_sufficiency`,
`blocker_class`, `blocker_confidence`, `reason`, `detail`, `model`.

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

**`evidence_insufficient`, blocker `facts_missing`, no `revision` in the
state — investigate once, then re-run.** Check repository configuration,
code, and documentation first; if the repository does not answer the
question, consult external documentation or web search. This whole
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
evidence is still insufficient.** Return to the user without another
decide.py run: list what was confirmed (verified facts with sources)
and what remains unverified, then ask the single deciding question as
below.

**Blocker `user_preference_unknown` or `balanced_tie`, or rule
`human_preference`** — the decision depends on the user's taste,
plans, or a deciding priority. Ask for that preference or priority
directly instead of technical details.

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

The state failed validation (see `detail`). Fix the state — usually the
alternatives structure or ids — and run Steps 6–7 again. If materially
different options cannot be constructed, tell the user why the decision
cannot be structured and ask how to proceed.
