# Phase 1 Live Validation Guide

> [!IMPORTANT]
> **Project CLI `--live-feishu` remains unimplemented.** Running commands with `--live-feishu` will produce a message indicating it is not yet available. Live validation for Phase 1 was performed using `lark-cli` to verify API contracts. Evidence of these runs is stored in `.sisyphus/evidence/plan-2/`.

## Overview

Live validation was performed to confirm that the generated payloads and interaction sequences work correctly with the actual Feishu Open Platform APIs. While the project CLI's live transport is pending, manual validation via `lark-cli` has confirmed the **create -> send -> update -> stale-sequence** contract. `lark-cli` was used for validation only; it is not a runtime or package dependency of this project.

## Confirmed API Contracts

Based on live evidence in `.sisyphus/evidence/plan-2/07-contract-delta.md`:

### 1. Create Card Entity
- **Endpoint**: `POST /open-apis/cardkit/v1/cards`
- **Body**: `{"type":"card_json", "data":"..."}`
- **Note**: Confirmed correct. Returns a `card_id`.

### 2. Send Message by card_id
- **Endpoint**: `POST /open-apis/im/v1/messages?receive_id_type=open_id`
- **Body**:
  ```json
  {
    "receive_id": "<id>",
    "msg_type": "interactive",
    "content": "{\"type\":\"card\",\"data\":{\"card_id\":\"<card_id>\"}}"
  }
  ```
- **Note**: This is the official path for interactive messages using a card entity.

### 3. Update Card Entity
- **Endpoint**: `PUT /open-apis/cardkit/v1/cards/:card_id`
- **Body**:
  ```json
  {
    "card": {
      "type": "card_json",
      "data": "<new_json>"
    },
    "uuid": "<uuid>",
    "sequence": <int>
  }
  ```
- **Note**: Card data must be wrapped under the `card` key.

### 4. Stale Sequence
- **Behavior**: Reusing or decreasing a `sequence` number returns error `300317` (`sequence number compare failed`).
- **Contract**: The `sequence` must strictly increase for each update.

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

## Exact Live Commands (Future Usage)

The `--live-feishu` flag is reserved for future implementation. Currently, the CLI will reject this flag with a message indicating it is unimplemented. The commands below represent the target CLI behavior once live transport is integrated.

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

Phase 2 live validation using `lark-cli` has confirmed the official API shapes. The `legacy_template_send` path has been superseded by the `interactive` message type with a `card_id` payload.

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
