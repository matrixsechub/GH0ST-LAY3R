# MSHOPS.NET Backend API Contract (Draft v2)

> **Status: draft specification, not implemented.** This document
> describes the HTTP API a future MSHOPS.NET backend service should
> expose. No server code exists in this repo and none should be added
> here — this repo defines the contract; MSHOPS.NET (a separate
> service/repo) implements it. See `AGENT_HQ.md` for the underlying
> concepts (engine, agent, registry, operator, escalation, lane, mode,
> status, severity, deployment, health, audit, pool) these endpoints
> operate on.
>
> **v1 changelog:** adds `GET /operators` and the `/escalations` group,
> reflecting `AGENT_HQ.md`'s HITL Governance Layer and Escalation
> Lifecycle (schema v2 in `core/registry.py`). `GET /agents` and
> `GET /engines` responses now also carry `type` and `capabilities`,
> since those fields are real as of registry schema v2 — no endpoint
> shape changed otherwise.
>
> **v2 changelog:** adds eight new endpoint groups corresponding to
> schema v3 in `core/registry.py`: `/deployments` (agent deployment
> lifecycle), `/engines/:id/health` and `PUT` variant (engine health
> records), `/routing-table` (capability/tag-based dispatch table),
> `/capabilities` (capability index + rebuild trigger), `/audit`
> (append-only governance audit trail), `/operator/sessions` (operator
> presence sessions), `/agent-pools` (agent grouping for routing), and
> `/hq/health` (HQ-wide health snapshot).

## Design principle

Every endpoint maps onto something that already exists and runs in this
repo today, or — for `/escalations` — onto a schema this repo defines
(`EscalationEvent`) even though nothing here populates it yet. Nothing
here invents server-side behavior beyond exposing the existing engine
and registry over HTTP.

## Endpoints

### `POST /intents`

Submit a new intent for processing. Maps directly onto
`GhostLayerEngine.run(raw, source=...)` in `core/engine.py`.

Request:

```json
{ "raw": "Boot sequence: Ghost Layer Studio online.", "source": "mshops-web" }
```

Response: the `OutputEnvelope` shape from `core/output.py`'s
`OutputEnvelope.to_dict()` — `intent_id`, `source`, `operator_axis`,
`spectral_density`, `volatility`, `payload`, `timestamp`, `meta`.

### `GET /intents/:intent_id`

Fetch a previously-run intent's envelope. Requires persistence this
repo does not have — the current engine is stateless per call.
Storage design is MSHOPS.NET's responsibility, not specified here.

### `GET /agents`

List all registry entries. Maps onto `agents/registry.yaml`'s `agents:`
list, shaped per `core/registry.py`'s `AgentRegistryEntry`.

### `GET /agents/:id`

Fetch a single registry entry by `id`.

### `POST /agents/:id/run`

Manually invoke a single agent (intended for `mode: manual` agents —
see `AGENT_HQ.md`) against a caller-supplied intent/state, bypassing
`supports()`.

Request:

```json
{
  "intent": { "id": "...", "source": "...", "description": "...", "tags": [] },
  "state": { "spectral_density": 0.0, "volatility": 0.0, "context": {} }
}
```

Response: whatever the target agent's `run()` returns.

### `GET /engines`

List engine bindings, shaped per `core/registry.py`'s `EngineBinding`
(including `type: "engine"` and `capabilities`). Maps onto
`agents/registry.yaml`'s `engines:` list.

### `GET /operators`

List HQ-level operator entries, shaped per `core/registry.py`'s
`OperatorEntry`. Maps onto `agents/registry.yaml`'s `operators:` list.
Today this returns exactly one entry (`operator_id: lupe`).

### `GET /operators/:id`

Fetch a single operator entry by `operator_id`.

### `GET /escalations`

List `EscalationEvent` records (see `AGENT_HQ.md`'s "Escalation
Lifecycle"), optionally filtered by `status` and/or `severity` query
params. No storage backing this exists in this repo; MSHOPS.NET owns
persistence.

### `GET /escalations/:id`

Fetch a single `EscalationEvent` by `id`.

### `POST /escalations`

Create an `EscalationEvent`. Expected to be called by MSHOPS.NET's own
dispatch/governance layer when a `GOV-n` rule fires (see the GOV-n ->
severity mapping in `AGENT_HQ.md`), not typically by an external client.

Request: an `EscalationEvent` minus `id`, `status`, `created_at` (server-
assigned):

```json
{
  "trigger_rule": "GOV-3",
  "intent_id": "...",
  "agent_ids": ["ContainmentAgent"],
  "severity": "high",
  "reason": "Intent tagged high-risk; operator review required."
}
```

Response: the full `EscalationEvent`, `status: "pending"`.

### `PATCH /escalations/:id`

Transition an escalation's status. Per `AGENT_HQ.md`'s Escalation
Lifecycle state machine, any caller may move `pending -> acknowledged`,
but only the registered operator may move to `resolved` or `dismissed` —
enforcing that distinction is MSHOPS.NET's responsibility; this repo only
specifies the rule.

Request:

```json
{ "status": "resolved", "resolution": "Reviewed; approved as-is." }
```

Response: the updated `EscalationEvent`.

### `GET /deployments`

List `AgentDeploymentRecord` entries; filter by `agent_id`, `engine_id`,
`status`.

### `GET /deployments/:id`

Fetch a single `AgentDeploymentRecord` by `id`.

### `POST /deployments`

Create a new deployment record (`status: "pending"`). `deployed_by` must
be the registered operator's `operator_id` (GOV-4 — operator approval is
required). Produces `AuditEvent(event_type="deployment.status_changed")`.

Request (fields server assigns: `id`, `status: "pending"`, `deployed_at`):

```json
{
  "agent_id": "route-advisory-agent",
  "engine_id": "ghost-layer-core",
  "version": "1.2.0",
  "deployed_by": "lupe",
  "rollback_to": "1.1.0",
  "notes": "Promoting to active."
}
```

Response: the full `AgentDeploymentRecord`.

### `PATCH /deployments/:id`

Transition `status`. Each transition produces
`AuditEvent(event_type="deployment.status_changed")`. Only the registered
operator may set `status: "rolled_back"` or create a rollback deployment.

Request:

```json
{ "status": "healthy", "notes": "Health checks passed." }
```

Response: the updated `AgentDeploymentRecord`.

### `GET /engines/:id/health`

Fetch the most recent `EngineHealthRecord` for one engine.

### `PUT /engines/:id/health`

Upsert the health record for an engine. Intended for MSHOPS.NET's
health-check layer, not external callers. Does not produce an `AuditEvent`
— health records are high-frequency telemetry, not governance events.

Request (server assigns nothing; caller provides all fields):

```json
{
  "engine_id": "ghost-layer-core",
  "status": "healthy",
  "checked_at": "2026-07-09T12:00:00Z",
  "active_agent_count": 4,
  "pending_escalation_count": 0
}
```

Response: the upserted `EngineHealthRecord`.

### `GET /routing-table`

List `RoutingTableEntry` records; filter by `active`, `target_engine_id`.

### `GET /routing-table/:id`

Fetch a single `RoutingTableEntry` by `id`.

### `POST /routing-table`

Add a routing table entry. Requires operator authorization (GOV-4 extended
to routing configuration). Produces
`AuditEvent(event_type="routing_table.updated")`.

Request (server assigns `id`):

```json
{
  "target_engine_id": "ghost-layer-core",
  "priority": 10,
  "match_tags": ["security"],
  "match_capability": "",
  "description": "Route security-tagged intents to ghost-layer-core."
}
```

Response: the full `RoutingTableEntry`.

### `PATCH /routing-table/:id`

Enable/disable or reprioritize an entry. Produces `AuditEvent`.

Request:

```json
{ "active": false }
```

Response: the updated `RoutingTableEntry`.

### `DELETE /routing-table/:id`

Remove an entry. Produces `AuditEvent(event_type="routing_table.updated")`.

### `GET /capabilities`

List `CapabilityIndex` records; optionally filter by `capability` substring.

### `GET /capabilities/:capability`

Fetch one `CapabilityIndex` entry by exact capability string.

### `POST /capabilities/rebuild`

Trigger a full rebuild of the capability index from current registry data.
MSHOPS.NET's registration layer calls this after any engine or agent
registration change. Produces
`AuditEvent(event_type="capability_index.rebuilt")`.

Response: `{ "rebuilt_at": "<ISO 8601>", "capability_count": <int> }`.

### `GET /audit`

List `AuditEvent` records. Filter params: `actor_id`, `actor_type`,
`target_id`, `target_type`, `event_type`; range by `since` / `until`
(ISO 8601). Append-only — no `POST`, `PATCH`, or `DELETE`.

### `GET /audit/:id`

Fetch a single `AuditEvent` by `id`.

### `GET /operator/sessions`

List `OperatorSessionRecord` entries. Filter by `operator_id` and/or
`active` (boolean: `ended_at` is `None`).

### `GET /operator/sessions/:id`

Fetch a single `OperatorSessionRecord` by `session_id`.

### `POST /operator/sessions`

Open a new operator session. Only callable by the registered operator.
Produces `AuditEvent(event_type="operator.session_opened")`.

Request (server assigns `session_id`, `started_at`):

```json
{ "operator_id": "lupe", "notes": "Starting review of open escalations." }
```

Response: the full `OperatorSessionRecord` (`ended_at: null`).

### `PATCH /operator/sessions/:id`

Close an active session (`ended_at` set to server time). Only callable by
the same operator who opened it. Produces
`AuditEvent(event_type="operator.session_closed")`.

Request:

```json
{ "notes": "Review complete." }
```

Response: the updated `OperatorSessionRecord`.

### `GET /agent-pools`

List `AgentPool` records; filter by `engine_id`, `tags`.

### `GET /agent-pools/:id`

Fetch a single `AgentPool` by `id`.

### `POST /agent-pools`

Create an agent pool. Produces `AuditEvent`.

Request (server assigns `id`):

```json
{
  "name": "security-pool",
  "engine_id": "ghost-layer-core",
  "agent_ids": ["adversarial-intel-agent", "containment-agent"],
  "tags": ["security"],
  "run_mode": "sequential",
  "description": "Security-focused agent group."
}
```

Response: the full `AgentPool`.

### `PATCH /agent-pools/:id`

Update pool membership, `run_mode`, `tags`, or `description`. Produces
`AuditEvent`.

Response: the updated `AgentPool`.

### `DELETE /agent-pools/:id`

Remove a pool. Does not affect member agents. Produces `AuditEvent`.

### `GET /hq/health`

Fetch the most recent `HQHealthRecord`. No filter params — always the
latest snapshot. Callers that need current state must not cache this
response beyond the health-check write interval.

Response: the most recent `HQHealthRecord`.

## Explicitly out of scope for this document

- Auth, rate limiting, pagination, versioning headers — MSHOPS.NET's
  concern, not specified here.
- Persistence/storage design for `GET /intents/:intent_id`.
- Any transport other than HTTP.
- Any real implementation. This is a contract for a system that does
  not exist yet.
