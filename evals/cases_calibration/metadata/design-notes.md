# Frozen held-out scenarios

These are authored, fictional workload fixtures. Statements prefixed `Scenario`
are stipulated requirements and implementation facts of that fixture, not
claims discovered in a production repository or statements from a real user.
Missing and confirmed cases share the same baseline. Confirmation adds the
previously unresolved deciding fact; it never contradicts a baseline constraint.
No model output was used to create the cases or expectations.

| Topic | Old training deciding fact | Held-out deciding fact | Confirmed expectation |
|---|---|---|---|
| database | offline single-user storage / unspecified workload | four hosts writing one transactional inventory dataset | PostgreSQL |
| authentication | existing sessions / unknown clients | immediate revocation of already issued credentials | durable server sessions |
| test_framework | existing 200-test pytest suite and unchanged CI | existing Playwright browser lifecycle fixtures and browser matrix; no unit-suite migration | pytest integration |
| dependency | CSV size / pandas dependency cost | external native executable forbidden, pure Python packages allowed | pypdf |
| deployment | traffic / operations tradeoff | released application needs durable local uploads and checkpoints | persistent-disk server |

All five missing cases leave the requirement or deployment fact unresolved. A
selection would assume that fact, so the frozen expectation is ASK_USER. The
confirmed alternatives and acceptance sets were read before any model calls.
The calibration cases use the compatible legacy state path intentionally:
structured unknown constraints would stop before capturing model signals, while
confirmed single-option filtering would test constraint elimination instead of
thresholds. The independent constraint track exercises those engine guarantees.

Primary technical sources checked before freeze on 2026-10-01:

- [SQLite use guidance](https://www.sqlite.org/whentouse.html) recommends a
  client/server engine for many concurrent network writers. Embedded SQLite is
  not declared categorically impossible; its given alternative has no coordinating
  server, unlike the offered PostgreSQL design.
- [JWT RFC 7519 §4.1.4](https://www.rfc-editor.org/rfc/rfc7519.html#section-4.1.4)
  defines token expiry. The lack of immediate revocation follows from the
  stipulated signature/expiry-only implementation, not from all JWT designs.
- [Playwright pytest documentation](https://playwright.dev/python/docs/test-runners)
  describes pytest fixtures and the browser matrix. unittest can be adapted,
  but its offered runner does not directly consume the existing pytest fixtures.
- [pypdf documentation](https://pypdf.readthedocs.io/en/stable/) describes pure
  Python PDF processing and text extraction. The offered input excludes encrypted
  PDFs and OCR so optional cryptographic/native processing is not assumed.
- Deployment capabilities are stipulated attributes of two fictional plans;
  no claim is made that managed hosting generally lacks persistent volumes.

Manifest paths are relative to `metadata/`; SHA-256 binds exact case bytes.
`frozen_at` binds chronology; the git commit binds the pre-execution artifact.
