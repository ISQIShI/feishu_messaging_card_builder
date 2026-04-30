# Runtime Bridge Fixtures

These fixtures cover the Plan 7 runtime bridge harness.

## Scope

- Supported: final-reply text only
- Deferred: streaming chunks, tool payloads, card actions

## Fixture rules

- Use only synthetic values such as `mock-session-001`, `test-hermes-msg-001`, and `test-open-id-001`
- Do not use live-looking Feishu IDs, real UUIDs, access tokens, app secrets, or tenant keys
- Keep payloads minimal and focused on classification behavior

## Files

- `minimal_text_turn.json`: minimal valid final-reply text event
- `unsupported_streaming_chunk.json`: streaming event marked unsupported
- `unsupported_tool_payload.json`: tool payload event marked unsupported
- `missing_recipient.json`: valid event missing recipient metadata
- `duplicate_text_turn.json`: duplicate content for idempotency checks
- `malformed_event.json`: malformed structure missing required fields
