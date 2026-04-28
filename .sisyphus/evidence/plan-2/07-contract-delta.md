# 07-contract-delta: Feishu Card API Validation Memo

This memo summarizes the validated live Feishu card contract facts as of Phase 1, identifying deltas from initial Plan 1 mock assumptions.

## Live Validated Facts

The following operations were successfully validated using `lark-cli` (v2.2.0) against the official Feishu Open Platform.

### 1. Create Card Entity
- **Endpoint**: `POST /open-apis/cardkit/v1/cards`
- **Method**: `create`
- **Identity**: `--as bot`
- **Request Body**: `{"type":"card_json","data":"<card json string>"}`
- **Outcome**: Returned `code: 0` and a valid `card_id`.

### 2. Send Message by card_id
- **Endpoint**: `POST /open-apis/im/v1/messages?receive_id_type=open_id`
- **Method**: `im messages create`
- **Identity**: `--as bot`
- **Request Body**:
  ```json
  {
    "receive_id": "<open_id>",
    "msg_type": "interactive",
    "content": "{\"type\":\"card\",\"data\":{\"card_id\":\"<card_id>\"}}"
  }
  ```
- **Outcome**: Returned `code: 0`. The message was successfully delivered as an `interactive` type.

### 3. Update Card Entity
- **Endpoint**: `PUT /open-apis/cardkit/v1/cards/:card_id`
- **Method**: `cardkit cards update`
- **Identity**: `--as bot`
- **Request Body**:
  ```json
  {
    "card": {
      "type": "card_json",
      "data": "<new card json string>"
    },
    "uuid": "<uuid>",
    "sequence": 2
  }
  ```
- **Outcome**: Returned `code: 0`. The card content updated live in the chat.

### 4. Stale Sequence Behavior
- **Test**: Retried the same update with `sequence: 2`.
- **Outcome**: Returned error `300317` with message `sequence number compare failed`.
- **Fact**: The `sequence` must be strictly increasing for updates to be accepted.

## Contract Delta

| Feature | Plan 1 Mock Assumption | Live Validated Reality |
| :--- | :--- | :--- |
| **Send Path** | `legacy_template_send` (type: template) | **Rejected**. Must use `im messages create` with `msg_type: interactive`. |
| **Send Content** | JSON with `template_id` | JSON with `type: card` and `data: { card_id: "..." }`. |
| **Update Body** | Flat `{ type: "card_json", data: ..., sequence, uuid }` | **Wrapped**. Content must be under `card` key: `{ card: { type, data }, sequence, uuid }`. |
| **Create Body** | Flat `{ type: "card_json", data: ... }` | **Confirmed Correct**. No wrapping required for creation. |

## Identity Used

- **Recipient Lookup**: Executed `--as user` to retrieve the `open_id` of the current authenticated user.
- **Card Operations**: All `create`, `send`, and `update` operations executed `--as bot`.

## Doc-Only Facts (Not Live Tested)

The following properties are documented but were not part of the Phase 1 live validation suite:

1. **Entity Expiry**: Card entities expire 14 days after creation if not updated.
2. **Single-Send Restriction**: A single `card_id` can typically only be used for one successful "send" operation (subsequent updates must use the `card_id` via the Update API).
3. **Cross-Tenant Behavior**: Validation was restricted to a single tenant environment.
4. **Client Version Requirements**: Minimum Feishu client versions required to render certain components.

## Search Terms Reference
- create
- send
- update
- stale sequence
- legacy_template_send
- doc-only
