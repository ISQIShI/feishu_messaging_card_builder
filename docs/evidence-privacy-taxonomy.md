# Evidence Privacy Taxonomy

## Purpose

This document defines the evidence/privacy contract for Plan 6 closeout work.
It classifies evidence artifacts by whether they are authoritative for future closeout claims,
whether they may remain under `.sisyphus/evidence/`, and what remediation is required before any PASS claim.

This taxonomy is intentionally strict:

- historical retention is allowed;
- authority is not implied by retention;
- raw/debug evidence is never upgraded by convenience; and
- invalid artifacts block authoritative reuse until fixed or quarantined.

## Artifact Classes

### `safe`

Definition: an artifact that is eligible input for future PASS claims.

Requirements:

- parses successfully if it is structured data;
- contains only intentionally redacted, summarized, or privacy-safe values;
- does not expose raw/equivalent identifiers, nested raw payloads, or sample-value leakage beyond the approved safe projection;
- does not depend on an unresolved generation-order caveat.

Operational rule: `safe` artifacts may be cited as authoritative evidence for Plan closeout work.

### `quarantined`

Definition: a historical or raw artifact retained for context, but explicitly non-authoritative.

Requirements:

- kept only for traceability, debugging history, or audit lineage; and
- not used to support PASS claims, hygiene claims, or privacy claims.

Examples of why an artifact becomes `quarantined`:

- it contains raw/equivalent identifiers such as bridge/session/message/card IDs;
- it preserves nested request/response payloads or raw content bodies;
- it stores raw SQLite state or sampled values that exceed the safe projection.

Operational rule: quarantined artifacts may stay under the evidence roots, but every downstream audit must treat them as context-only.

### `raw-debug-local-only`

Definition: a raw debugging artifact that is not allowed under evidence roots unless it is first reclassified as `quarantined` with an explicit reason.

Requirements:

- never eligible for PASS claims;
- never acceptable as an unlabelled artifact inside `.sisyphus/evidence/`; and
- must either remain outside evidence roots or be intentionally retained as `quarantined` history.

Operational rule: if a raw/debug artifact appears under `.sisyphus/evidence/` without quarantine treatment, that is a privacy/process violation.

### `generation-order-excluded`

Definition: an artifact excluded from a scan only because of authoring order, with an explicit file-level reason recorded at the time of exclusion.

Requirements:

- exclusion reason must be explicit and file-specific;
- exclusion must be temporary and tied to generation order rather than privacy convenience; and
- the excluded artifact must not be used for PASS claims until it is actually generated and independently reviewed.

Operational rule: generation-order exclusions are allowed only as bookkeeping notes; they do not upgrade an artifact to `safe`, and they do not count as evidence themselves.

### `invalid`

Definition: an artifact that cannot be trusted in its current form and must be fixed or quarantined before closeout.

Examples:

- malformed JSON;
- truncated or structurally inconsistent structured output;
- contradictory hygiene output that cannot be mechanically verified.

Operational rule: an `invalid` artifact is not authoritative, is not PASS-eligible, and requires remediation before any closeout that depends on it.

## Classification Rules for Baseline Inventory

The Plan 6 baseline inventory applies the following precedence order:

1. `invalid` if structured parsing fails.
2. `quarantined` if the artifact is historical/raw and currently exposes raw/equivalent identifiers, nested raw payloads, or SQLite sample leakage.
3. `safe` if neither condition above applies.

Notes:

- `raw-debug-local-only` is a policy class, not a default retention class; under evidence roots it must become `quarantined` or be removed from the evidence set.
- `generation-order-excluded` is a scan-status class, not a claim of safety.

## Plan 6 Baseline Expectations

- No artifact should receive a PASS claim merely because it already exists under `.sisyphus/evidence/`.
- Known historical raw Plan 4 inspect/process/SQLite artifacts remain context-only until replaced or superseded.
- Known Plan 5 hygiene artifacts with sampled raw identifiers remain non-authoritative.
- Known malformed Plan 5 final hygiene output remains `invalid` until fixed or quarantined.
