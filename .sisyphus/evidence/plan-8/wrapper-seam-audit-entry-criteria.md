# Wrapper-First Seam Sufficiency Audit: Entry Criteria & Roadmap Prep

## Cleanup Gate (Mandatory)
**Plan 7 cleanup pass is required before this plan can execute the seam audit.**
If Plan 7 cleanup does not pass (meaning all harness-level reversibility proofs, 89+ tests, and safe-inspect logic are not verified), this package is NOT activated and the audit is deferred.

## Entry Criteria
The following conditions must be met to start the Wrapper-First Seam Sufficiency Audit:
1. Plan 7 cleanup successfully completed and verified.
2. Hermes runtime observation capability is available (via logs, local websocket interceptor, or shell wrapper).
3. Access to Feishu/Lark websocket message flow documentation or live traces.
4. Established baseline for "native delivery recorded" status.

## Required Inputs
- Hermes runtime outbound message observations (raw vs logical).
- Card entity lifecycle data (creation speed, update latency).
- Mapping of Hermes `session_key` to Feishu `chat_id`.
- Current Hermes Feishu/Lark configuration details.

## Audit Questions & Pass/Fail Matrix

| Audit Question | Pass Criteria | Fail Criteria |
|----------------|---------------|---------------|
| **Stable Final Reply Observation** | Wrapper can reliably detect the completion of a message without internal Hermes state access. | Message completion signal is ambiguous or missing. |
| **Recipient Identity Extraction** | Open_id or chat_id can be extracted from the outbound stream or metadata safely. | Recipient identity is unavailable without Hermes source patch. |
| **Native Text Coexistence/Suppression** | Native text can be suppressed externally OR dual-delivery is acceptable for validation. | Suppression requires Hermes source patch but dual-delivery is rejected. |
| **Reversibility** | Seam integration can be disabled or removed with zero operational impact on Hermes. | Disabling the seam leaves Hermes in a broken or modified state. |
| **Failure Ceiling** | Failed card delivery results in safe fallback to native text or `reconciliation_required`. | Failure leads to message loss or infinite loops. |

## Forced-Seam Escalation Triggers
If any of the following triggers occur during the audit, the "Wrapper-First" approach is considered insufficient, and a **Forced-Seam Decision Memo** must be produced:
1. **Trigger 1**: Cannot observe stable final replies (cannot reliably derive logical ID).
2. **Trigger 2**: Cannot suppress or safely coexist with original text send without source patching.
3. **Trigger 3**: Preventing duplicate native text requires modification of Hermes core code.
4. **Trigger 4**: Recipient identity cannot be extracted safely from the external seam.

## Explicit Non-Goals
The following activities are strictly out of scope for this audit:
- **No live transport implementation**: No production-grade delivery code.
- **No production wrapper implementation**: Only audit/proof-of-concept checks.
- **No Hermes patch**: Zero modification to Hermes source code.
- **No webhook/server**: No HTTP endpoint deployment or design.
- **No installer scripts**: No `install.sh` or automated deployment tools.
- **No queue/retry/dedupe engine**: No background worker or persistence expansion.

## References
- `docs/phase-3-runtime-bridge-design.md`: Normalized event fields (lines 88-123).
- `docs/phase-3-runtime-bridge-design.md`: Forced-seam escalation triggers (lines 267-305).
- Root `AGENTS.md`: Project guardrails (no webhook, no patch, reversible boundary).
