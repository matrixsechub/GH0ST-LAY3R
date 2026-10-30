# Intake Agent v2 — HQ Integration Plan

**Status: design specification**
**Branch: feature/intake-agent-v2-hq-bootstrap**
**Scope: gh0st-lay3r only** — ttx-operator-shell changes are a separate,
pending deliverable that requires `ttx-operator-shell` repo access approval.

---

## 1. Purpose

Intake Agent v2 (`IntakeAgentV2`) adds structured lifecycle tracking and
operator-action hooks to the existing intent-ingestion flow. Where the four
existing constellation agents observe substrate state and produce advisory
outputs, `IntakeAgentV2` is the queue-management and operator-surface layer:
it classifies every intent into a lifecycle stage, exposes queue metrics to
HQ observability endpoints, and surfaces the set of operator actions available
for each intent.

**What this is not:** a dispatcher, a real queue store, or a MSHOPS.NET
backend. `IntakeAgentV2` runs inside the existing `GhostLayerEngine` pipeline
and produces structured output. Persistence, real queue management, and
operator-action routing are MSHOPS.NET responsibilities.

---

## 2. GOV-4 Gate

`IntakeAgentV2` is defined in `agents/constellation.py` and registered in
`agents/registry.yaml` with `status: experimental`. It is **not** added to
`create_default_engine()`'s agent list — that registration is the GOV-4
gate. The operator (`operator_id: lupe`) must explicitly approve promotion
from `experimental` to `active` and authorize the runtime registration before
the agent runs inside the engine. Until then, the agent class exists for
design validation and serve.py endpoint testing only.

---

## 3. Lifecycle Stages

`IntakeLifecycleStage` (defined in `core/registry.py`):

Implemented flow (enforced by `_INTAKE_VALID_TRANSITIONS` in `scripts/serve.py`):

```
received ──► validated ──► queued ──► processed
```

Every other transition (skipping a stage, going backwards, leaving
`processed`, or entering `escalated`) is rejected with HTTP 422 and leaves
state and the audit log untouched.

| Stage        | Status       | Meaning                                                  |
|--------------|--------------|----------------------------------------------------------|
| `received`   | implemented  | Submission acknowledged via `POST /api/register`         |
| `validated`  | implemented  | Passed initial checks; grants full marketplace access    |
| `queued`     | implemented  | Waiting in the processing queue                          |
| `processed`  | implemented  | Intake flow finished; `resolved_at` is set               |
| `escalated`  | schema only  | Operator review (future — no transition reaches it yet)  |
| `processing` | schema only  | Pre-TTX stage, kept for schema compatibility             |
| `completed`  | schema only  | Pre-TTX stage, kept for schema compatibility             |

Lifecycle records are append-only: each transition appends a new
`IntakeLifecycleRecord` (in `core/registry.py`) with the same `intent_id`,
leaves the previous record unchanged, and writes an `AuditEvent` with
`event_type: "intake.stage_changed"` (payload: `from_stage`, `stage`,
`previous_record_id`).

### Marketplace access by latest stage

`GET /marketplace` reads the most recently appended lifecycle record:

| Latest stage                         | `mode`     | `access` | Banner |
|--------------------------------------|------------|----------|--------|
| none, `received`, `queued`, `processed` | `observer` | `false`  | "IntakeAgentV2: Access Pending — You are in Observer Mode." |
| `validated`                          | `full`     | `true`   | none |
| `escalated` (future)                 | `review`   | `false`  | "IntakeAgentV2: Operator Review in Progress — Access suspended pending resolution." |

There is no identity layer, so this is one global state for the server,
not per-user.

---

## 4. Operator Actions

**Status: schema only — not implemented.** No endpoint accepts operator
actions yet, and `operator_action` is always `null` on records written by
`serve.py`. This section is the design target for the next pass.

`IntakeOperatorAction` (defined in `core/registry.py`):

| Action     | Intended applicable stages     | Intended effect                   |
|------------|-------------------------------|-----------------------------------|
| `approve`  | received                      | Moves to `validated`             |
| `escalate` | received, validated, queued   | Moves to `escalated`             |
| `close`    | any open stage                | Moves to `processed`, notes why  |
| `reassign` | escalated                     | Routes to a different lane/agent |
| `annotate` | any stage                     | Adds operator notes, no transition|

When implemented, each action should append an `IntakeLifecycleRecord`
(with `operator_action` set) and an `AuditEvent` with
`event_type: "intake.operator_action"`, and must be restricted to the
registered operator (GOV rules in `AGENT_HQ.md`).

The set of available actions for a given intent is returned by
`IntakeAgentV2.run()` in the `operator_actions_available` field, reflecting
the current stage and volatility.

---

## 5. HQ Schema Additions (core/registry.py)

### New type aliases
```python
IntakeLifecycleStage = Literal[
    "received", "validated", "queued", "processing",
    "processed", "escalated", "completed",
]
IntakeOperatorAction = Literal["approve", "escalate", "close", "reassign", "annotate"]
```

### IntakeLifecycleRecord dataclass
Fields: `id`, `intent_id`, `stage`, `created_at`, `updated_at`, `source`,
`operator_action` (Optional), `operator_notes`, `resolved_at` (Optional).
`type` discriminator: `"intake-lifecycle"`. Added to `RegistryRecord` union.

### HQHealthRecord intake fields (additive, all default to 0)
- `intake_received_count`, `intake_validated_count`, `intake_queued_count`,
  `intake_processed_count` — the implemented flow
- `intake_processing_count`, `intake_completed_count`,
  `intake_escalated_count` — schema-only stages
- `intake_queue_depth` — legacy alias of `intake_queued_count`

These are populated by `scripts/serve.py`'s `_compute_hq_health()` from the
`_intake_lifecycle` list at request time.

---

## 6. serve.py Extensions

Endpoints added to `scripts/serve.py`:

| Method | Path | Purpose |
|--------|------|---------|
| GET  | `/agents/intake-agent-v2` | Registry entry |
| GET  | `/intake-agent-v2/lifecycle` | All lifecycle records, append order |
| GET  | `/intake-agent-v2/metrics` | Per-stage counts |
| POST | `/api/register` | Public intake submission → `received` record |
| GET  | `/marketplace` | Access mode + banner from latest stage |
| POST | `/intake-agent-v2/lifecycle/transition` | Advance one record one stage |
| GET  | `/cockpit/intake` | Read-only operator panel |

> **Security:** `POST /api/register` and `POST /intake-agent-v2/lifecycle/transition`
> have no authentication. Anyone who can reach the server can advance a
> record to `validated` and unlock full marketplace access. Run `serve.py`
> on localhost only (its default bind) until operator/session auth exists.

### GET /agents/intake-agent-v2
Returns the registry entry for `intake-agent-v2` from `_registry["agents"]`.
Looks up by `id == "intake-agent-v2"`. Returns 404 if not found (e.g., if
the fallback registry doesn't include it).

### GET /intake-agent-v2/lifecycle
Returns the `_intake_lifecycle` list — all `IntakeLifecycleRecord` dicts
recorded since server start, in append order. Empty list `[]` on a fresh
server. No filtering in this stub; MSHOPS.NET adds pagination and filtering.

### GET /intake-agent-v2/metrics
Returns a metrics snapshot:
```json
{
  "received_count": <int>,
  "validated_count": <int>,
  "queued_count": <int>,
  "processed_count": <int>,
  "processing_count": <int>,
  "escalated_count": <int>,
  "completed_count": <int>,
  "total": <int>
}
```
Counts are records per stage, not intents per current stage: one intent
walked to `processed` contributes one record to each of the four TTX stages.
The same counts are surfaced in `HQHealthRecord`'s `intake_*_count` fields.

### POST /api/register
Body: `{"raw": "...", "source": "...", "intent_id"?: "...", "notes"?: "..."}`.
Returns 201 with `{"lifecycle": <record>, "marketplace": <state>}`.

### GET /marketplace
Returns `{"mode", "access", "banner", "latest_intake_stage", "total_submissions"}`.

### POST /intake-agent-v2/lifecycle/transition
Body: `{"lifecycle_id": "...", "to_stage": "...", "notes"?: "..."}`. Returns
200 with `{"previous", "current", "marketplace"}`; 400 for missing fields;
404 for an unknown `lifecycle_id`; 422 for a disallowed transition.

### GET /cockpit/intake
Read-only: agent status, GOV-4 status, routing-table entry count, per-stage
counts, full timeline, and the last 10 `received` records.

Module-level state: `_intake_lifecycle` (append-only list of
`IntakeLifecycleRecord`-shaped dicts) and `_routing_table` (four
`RoutingTableEntry`-shaped dicts routing `intake`/`register`,
`access-request`, `paywall`, and `register-transition` tags to
`intake-agent-v2`). `POST /intents` records matched routing entries in its
`intent.submitted` audit payload but never runs `IntakeAgentV2`.

`_compute_hq_health()` populates `intake_received_count`,
`intake_validated_count`, `intake_queued_count` (alias `intake_queue_depth`),
`intake_processing_count`, `intake_processed_count`,
`intake_completed_count`, and `intake_escalated_count`.

Regression coverage: `tests/test_intake_agent_v2.py`.

`_REGISTRY_FALLBACK["agents"]` updated to include the `intake-agent-v2` entry
matching `agents/registry.yaml`, so the endpoint is reachable even without PyYAML.

---

## 7. Audit Event Types (intake domain)

| event_type               | Produced by                                   |
|--------------------------|-----------------------------------------------|
| `intake.stage_changed`   | Any lifecycle stage transition                |
| `intake.operator_action` | Any operator action (approve/escalate/etc.)   |

These follow the existing dot-notation convention in `AuditEvent.event_type`.
MSHOPS.NET's write path owns appending them to `_audit_log`; serve.py stubs
return them via `GET /audit?target_type=intake-lifecycle`.

---

## 8. Branch Strategy

| Branch                              | Contains                                   |
|-------------------------------------|--------------------------------------------|
| `claude/claude-md-docs-hpockz`      | Schema v3, AGENT_HQ.md, API_CONTRACT.md   |
| `ghost-layer-hq-serve`              | `scripts/serve.py` (merged into feature)  |
| `feature/intake-agent-v2-hq-bootstrap` | This plan + registry additions (gh0st-lay3r only) |
| `feature/intake-agent-v2-operator`  | Pending: ttx-operator-shell changes (blocked on repo access) |

`feature/intake-agent-v2-hq-bootstrap` is the gh0st-lay3r deliverable.
The ttx-operator-shell work (unified dashboard entry, lifecycle timeline
widget, queue metrics panel, operator action buttons, escalation history
feed, HQ health linkage, plan-mode routing, telemetry stubs) is a separate
branch that requires repo access approval before work can begin.

---

## 9. SCOPE-LOCK Compliance

- No Cloudflare Workers or wrangler deployment assumed.
- No MSHOPS.NET backend assumed as deployed — treated as design target only.
- No changes to `core/engine.py` or `create_default_engine()` — GOV-4 gate.
- All new serve.py state is module-level and in-memory (no external store).
- `IntakeAgentV2` class is defined but not registered — this is the
  explicit, documented GOV-4 gate boundary.
- Escalation and audit linkage is additive: new `intake.*` event types
  follow the existing `AuditEvent` schema without changing it.
