# SDD ledger — plan: docs/superpowers/plans/2026-10-01-hard-constraints-calibration.md
Branch base: ab8c61c
## Preflight
| Tasks | Shared contract | Finding |
|---|---|---|
| 1/2 | decide, test_decide | Sequential integration; contracts consistent |
| 1/4 | decide, test_decide | Sequential integration; contracts consistent |
| 1/8 | decide | Sequential integration; contracts consistent |
| 2/4 | decide, test_decide | Sequential integration; contracts consistent |
| 2/8 | decide | Sequential integration; contracts consistent |
| 3/8 | readme | Sequential integration; contracts consistent |
| 4/5 | fixed | Sequential integration; contracts consistent |
| 4/6 | calibrate | Sequential integration; contracts consistent |
| 4/7 | calibrate | Sequential integration; contracts consistent |
| 4/8 | decide, fixed | Sequential integration; contracts consistent |
| 5/8 | fixed | Sequential integration; contracts consistent |
| 6/7 | calibrate | Sequential integration; contracts consistent |
| 7/8 | results, state | Sequential integration; contracts consistent |
| 1 self | tests/files/interfaces | Consistent; review gate required |
| 2 self | tests/files/interfaces | Consistent; review gate required |
| 3 self | tests/files/interfaces | Consistent; review gate required |
| 4 self | tests/files/interfaces | Consistent; review gate required |
| 5 self | tests/files/interfaces | Consistent; review gate required |
| 6 self | tests/files/interfaces | Consistent; review gate required |
| 7 self | tests/files/interfaces | Consistent; review gate required |
| 8 self | tests/files/interfaces | Consistent; review gate required |
Ruling: Worktree creation proceeds under user authorization to execute the approved isolated development plan — protects main and preserves untracked files — if wrong, remove the reversible worktree after preserving commits.
Ruling: Use the existing root .venv via an ignored symlink; system python lacks pytest — no dependency changes needed — if wrong, recreate a dedicated test environment.
## Tasks
Task 1: complete (commits ab8c61c..5cf4c24, review clean); redaction cross-task item assigned to Task 2
Task 2: complete (commits 5cf4c24..0f9812e, review clean); Task 1 redaction cross-task check resolved
Task 3: complete (commits 0f9812e..48ec030, review clean); enforcement covered by Task 2 review
Task 4: complete (commits 48ec030..6ce293c, review clean)
Task 5: complete (commits 6ce293c..6f0049e, review clean after fix1)
Task 6: complete (commits 6f0049e..ce869db, review clean after fix1)
Task 7: complete (commits ce869db..104cd45, prevalidation and completion reviews clean; candidate rejected; defaults unchanged)
Task 8: running; base 104cd45
Ruling: checked_at uses representable RFC 3339 timestamps, rejecting leap-second notation — stdlib cannot validate it reliably; acquisition timestamps do not need leap seconds — if wrong, legitimate leap-second records require conversion.
Ruling: Resolve Score winner from unrounded composite while preserving rounded display — current code ranks rounded display values, conflicting with exact-signal intent — if wrong, close-score decisions differ from legacy behavior; explicit boundary tests and baseline regression will expose the difference.
Task 5: fix round 1/5 in progress — Important: output directory may overwrite existing environment.json; review base 0120ed5
Task 5: fix round 1/5 (1 addressed, 0 open; commits 0120ed5..6f0049e)
Ruling: Calibration manifest uses schema_version=1, frozen_at, cases entries id/topic/pair_id/path/sha256 with paths relative to metadata/ and constrained to the parent case directory — plan left serialization unspecified; portable hashes connect Task6/7 — if wrong, manifest migration and tests need rework.
Ruling: Use gpt-6.1-sol high for complex independent review after gpt-6-astra usage-limit failure — user requested continuation; retain review scope and gate — if wrong, subtle findings may require another review after availability returns.
Task 6: fix round 1/5 in progress (4 Important: ID-only independence, coverage/hash integrity, contradictory expectations, case_id type; base d8dd5d3)
Ruling: training_case_hash is SHA256 of canonical id-to-case-file-hash map, and map plus matching complete coverage are mandatory — validate lacks original training files, so this checks stored provenance coherently — if wrong, policy serialization must migrate; this is integrity checking, not proof against deliberate forgery.
Task 6: fix round 1/5 (4 addressed, 0 open; commits d8dd5d3..ce869db)
Ruling: Select the best training-eligible policy, applying no-regression adoption gates before ranking, rather than freezing an ineligible global rank1 while 18 eligible policies exist — spec quality/adoption conditions are feasibility constraints; held-out has not run so this is a methodological fix without validation leakage — if wrong, training-based feasible selection overfits; held-out remains frozen and no reselection follows validation. Preserve original rejected search output; require TDD and review before validation.
Task 7: selection-method defect discovered from training; holding validation pending fix/review. Training87 complete; constraints21/21 sequences pass.
Ruling: Reuse a prior reviewer from an unrelated task when new-agent spawn hits thread limit — preserves implementer/reviewer independence and user-requested continuation — if wrong, retained context may bias review; new briefs and scoped packages bound the assignment.
Task 7: prevalidation review clean at046c680/measurement3c87105; implement_7 resumed for corrected search, one policy freeze, held-out validation.
Task 8: original final fixed87 and constraints27 complete; full-flow auth parser-redaction bug reproduced offline, dependency HTTP520 unrelated, database correct with coverage omission, deployment incorrect. Preserve originals. Await final fifth scenario before dedicated fix and affected-only rerun.
Ruling: Fix parse_answers structural-ID redaction in scope before completion — legal credential-bearing criterion IDs reproducibly destroy valid typed Score answers; this prevents trustworthy full-flow — if wrong, preserving known response identifiers may weaken redaction; typed validation and no untrusted text retention must be tested. Re-evaluate only actually affected scenarios, preserving original records.
Task 8: original evaluations saved a6ae255; pending response-ID bugfix by implement_7 (base a6ae255), independent review, auth-only rerun, final whole-branch review.

Task 8: response-ID fix a6ae255..f4e8920 independently approved; controller verification 617 passed / 3 skipped (14.79s), diff-check exit0. Auth-only evaluation/docs dispatched; original evidence unchanged.
Final whole-branch review ab8c61c..f4e8920: 0 Critical, 1 Important (legal keyword-ID snapshot replay redaction), 0 Minor. ONE fix wave dispatched; no controller code fixes.
Ruling: Accept reviewer declined-to-judge source semantics as outside deterministic engine guarantee — approved design validates structured evidence and excludes assessed violations, not truth of source facts; reports preserve overgeneralization risks — if wrong, a semantic-verification feature and its evaluation are required.
Ruling: Accept reviewer declined-to-judge post-rejection retuning and old loop expectation changes — frozen held-out evaluation prohibits reselection and user requested quality-first evidence — if wrong, further independently frozen experiments are needed; current failures remain visible.
Task 8: affected auth-only run completed once, runner0/Claude1, EAI_AGAIN, no state/resolution or live verdict. Original23 artifacts unchanged. Synthetic original-state replay retains legal IDs, zero network calls, no quality claim; docs/results uncommitted due git read-only.
Final fix wave: one finding addressed in worktree, report final-fix-wave-report.md; RED8fail, focused22pass, full638pass/3skip, diffcheck0. gitadd128 index.lock Read-only file system; scoped re-review pending.
Ruling: Preserve this plan workspace instead of cleanup while final edits cannot be committed — git metadata is read-only and cleanup would discard the persistent review/decision record before git history can hold it — if wrong, ignored review scratch remains until a writable session can commit and finish cleanup.
Final scoped re-review: Important ADDRESSED, new breakage0, code Approved; Task8 evidence/docs Approved. Current tree ready in code-quality terms; commit/integration blocked by read-only Git. Reports final-scoped-review.md and appended final-branch-review.md.
Task 8: evaluation/review work complete in working tree; original104cd45..a6ae255 and runtimefixf4e8920 committed, final replayfix and affected evaluation/docs NOT committed. Finishing blocked on writable Git; auth live verification still unobserved due EAI_AGAIN. Preserve branch/worktree/workspace.
