## Hermes Final Reply Fixture Schema

These fixtures model the minimal Phase 1 Hermes final-reply payload that can be parsed and rendered into a single Feishu Card JSON v2 markdown component.

### Required fields

- `source_platform` (`string`): source platform name, for Phase 1 fixtures set to `"feishu"`
- `session_key` (`string`): stable session identifier used for title generation and idempotency scope
- `hermes_message_id` (`string`): Hermes message identifier for the final reply
- `final_reply_index` (`integer`): 1-based final reply sequence number within the Hermes message
- `content_markdown` (`string`): final reply markdown body; Phase 1 only supports markdown text content

### Optional fields

- `created_at` (`string`): ISO 8601 timestamp when Hermes emitted the final reply
- `attachments` (`array`): only used by negative fixtures to assert that the renderer rejects unsupported content before any Feishu API call
- `tool_payloads` (`array`): reserved for negative fixtures that assert tool payload rejection

### Validation and rendering rules

- Phase 1 supports **final reply markdown text only**
- Attachments, markdown images, markdown tables, and tool payloads are rejected with typed renderer errors
- Rendered cards must use Card JSON v2 `schema: "2.0"`
- Rendered cards must set `config.update_multi: true`
- Rendered cards use exactly one markdown element in `body.elements`
- Element IDs must be deterministic, start with a letter, contain only letters/digits/underscores, and be no longer than 20 characters
- Rendered card JSON larger than 30 KB is rejected with a typed oversize error

### Fixture files

- `hermes_final_reply.json`: happy path final reply fixture
- `hermes_final_reply_duplicate.json`: duplicate of the happy path idempotency key tuple
- `hermes_unsupported_attachment.json`: negative fixture with unsupported attachment content
- `hermes_oversize_reply.json`: negative fixture with markdown content large enough to exceed the renderer size limit
