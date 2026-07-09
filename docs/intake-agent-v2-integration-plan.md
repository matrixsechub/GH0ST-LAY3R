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

```
queued ──► processing ──► completed
                │
                └──► escalated
```

| Stage       | Meaning                                                   |
|-------------|-----------------------------------------------------------|
| `queued`    | Intent received, not yet picked up for processing        |
| `processing`| Active evaluation in progress                            |
| `escalated` | Routed to operator review (GOV-3 triggered or manual)    |
| `completed` | Resolved — approved, closed, or otherwise finished       |

Stage transitions produce an `IntakeLifecycleRecord` (in `core/registry.py`),
which in turn produces an `AuditEvent` with `event_type: "intake.stage_changed"`.

---

## 4. Operator Actions

`IntakeOperatorAction` (defined in `core/registry.py`):

| Action     | Applicable stages              | Effect                            |
|------------|-------------------------------|-----------------------------------|
| `approve`  | processing                    | Moves to `completed`             |
| `escalate` | queued, processing            | Moves to `escalated`             |
| `close`    | any open stage                | Moves to `completed`, notes why  |
| `reassign` | escalated                     | Routes to a different lane/agent |
| `annotate` | any stage                     | Adds operator notes, no transition|

Each action produces an `IntakeLifecycleRecord` (with `operator_action` set)
and an `AuditEvent` with `event_type: "intake.operator_action"`.

The set of available actions for a given intent is returned by
`IntakeAgentV2.run()` in the `operator_actions_available` field, reflecting
the current stage and volatility.

---

## 5. HQ Schema Additions (core/registry.py)

### New type aliases
```python
IntakeLifecycleStage = Literal["queued", "processing", "escalated", "completed"]
IntakeOperatorAction = Literal["approve", "escalate", "close", "reassign", "annotate"]
```

### IntakeLifecycleRecord dataclass
Fields: `id`, `intent_id`, `stage`, `created_at`, `updated_at`, `source`,
`operator_action` (Optional), `operator_notes`, `resolved_at` (Optional).
`type` discriminator: `"intake-lifecycle"`. Added to `RegistryRecord` union.

### HQHealthRecord intake fields (additive, all default to 0)
- `intake_queue_depth: int = 0`
- `intake_processing_count: int = 0`
- `intake_escalated_count: int = 0`

These are populated by `scripts/serve.py`'s `_compute_hq_health()` from the
`_intake_lifecycle` list at request time.

---

## 6. serve.py Extensions

Three new endpoints added to `scripts/serve.py`:

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
  "queue_depth": <int>,
  "processing_count": <int>,
  "escalated_count": <int>,
  "completed_count": <int>,
  "total": <int>
}
```
Derived by counting `_intake_lifecycle` entries by `stage`. This is the same
data surfaced in `HQHealthRecord`'s intake fields, exposed as a dedicated
endpoint for polling by ttx-operator-shell's HQ console widget.

Module-level state added: `_intake_lifecycle: list = []` (append-only list
of `IntakeLifecycleRecord`-shaped dicts).

`_compute_hq_health()` updated to populate `intake_queue_depth`,
`intake_processing_count`, and `intake_escalated_count` from `_intake_lifecycle`.

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
