# Phase 1 Live Validation Guide

> [!IMPORTANT]
> **Live Feishu transport is not yet implemented.** Running commands with `--live-feishu` will produce an error message. The commands below show the intended future usage. Mock transport (`--mock-feishu`) is the only working mode for Phase 1.

This document provides instructions for performing optional live validation of the Feishu Messaging Card Builder against a real Feishu tenant.

## Overview

Live validation is **optional evidence** used to confirm that the generated payloads and interaction sequences work correctly with the actual Feishu Open Platform APIs. For Phase 1 completion, **mock tests are authoritative**. Live runs are used to record evidence of real-world compatibility and to detect any undocumented API behavior changes.

## Required Environment Variables

To enable live Feishu interaction, you must set the following environment variables in your shell. These credentials allow the tool to obtain an `app_access_token` from Feishu.

| Variable | Description | Source |
|----------|-------------|--------|
| `FEISHU_APP_ID` | The Unique ID of your Feishu App | Feishu Open Platform -> App Details -> App Credentials |
| `FEISHU_APP_SECRET` | The Secret Key of your Feishu App | Feishu Open Platform -> App Details -> App Credentials |

**Security Warning:**
- Never commit these credentials to the repository.
- Avoid using `.env` files that might be accidentally tracked by version control.
- Use a temporary shell session or a secure secret manager.

## Required Feishu App Permissions

Your Feishu App must have the following scopes enabled and approved in the Feishu Open Platform console:

1. **`cardkit:card:write`**: Required to create and update card entities via the CardKit API.
2. **`im:message:send_as_bot`**: Required to send messages (including cards) as the bot.
3. **`im:message`**: Required for general message operations.

After adding these permissions, ensure you create a new app version and publish it (or use the "Test View" for immediate development testing).

## Required Recipient Identifier

When running live commands, you must provide a valid recipient ID (e.g., `open_id`, `user_id`, or `chat_id`).
- The default mock recipient is `mock-open-id`.
- For live runs, use your own `open_id` (found in the Feishu Open Platform -> Contacts or via the API Explorer).

## Exact Live Commands

The `--live-feishu` flag is reserved for future use. In Phase 1, the CLI will reject this flag with a clear message indicating that live transport is not yet implemented. It is recommended to use a separate database file for live tests to avoid polluting mock state.

### 1. Process Fixture (Create & Send)
This command processes a Hermes fixture, creates a card entity, and sends it to a recipient.

```bash
python -m feishu_messaging_card_builder.cli process-fixture tests/fixtures/hermes_final_reply.json \
  --db .fmcb/live.sqlite \
  --live-feishu \
  --recipient <YOUR_OPEN_ID> \
  --evidence live-evidence.json
```

### 2. Update Card
This command updates an existing card message by its bridge message ID.

```bash
python -m feishu_messaging_card_builder.cli update-card <BRIDGE_MSG_ID> \
  --db .fmcb/live.sqlite \
  --live-feishu \
  --evidence live-update-evidence.json
```

### 3. Inspect State
Check the local records of live interactions.

```bash
python -m feishu_messaging_card_builder.cli inspect-state --db .fmcb/live.sqlite
```

## Payload-Proof Note

The current implementation uses a `legacy_template_send` payload structure for sending by `card_id`. This exact payload shape must be verified against the Feishu API Explorer or a live tenant.

If a live command fails due to a payload mismatch:
1. Record the exact error response in a new evidence file.
2. Update `docs/phase-1-prototype-decisions.md` with the corrected findings.
3. Update the implementation only after the decision is recorded.

## Troubleshooting

- **Permission Denied**: Ensure `cardkit:card:write` and `im:message:send_as_bot` are enabled AND the app is published/in test mode.
- **Invalid Recipient**: Verify that the recipient ID type matches the ID provided (e.g., don't use a `user_id` where an `open_id` is expected).
- **Network Issues**: Check if your environment has access to `open.feishu.cn`.
- **400 Bad Request**: Check the `evidence` JSON file for the specific error code and message from Feishu.

## Optional Evidence Policy

Live validation is intended as **optional evidence**. Failure to run live validation does not block Phase 1 completion, provided that **mock tests are authoritative** and pass successfully.
