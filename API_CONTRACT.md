# MSHOPS.NET Backend API Contract (Draft v1)

> **Status: draft specification, not implemented.** This document
> describes the HTTP API a future MSHOPS.NET backend service should
> expose. No server code exists in this repo and none should be added
> here — this repo defines the contract; MSHOPS.NET (a separate
> service/repo) implements it. See `AGENT_HQ.md` for the underlying
> concepts (engine, agent, registry, operator, escalation, lane, mode,
> status, severity) these endpoints operate on.
>
> **v1 changelog:** adds `GET /operators` and the `/escalations` group,
> reflecting `AGENT_HQ.md`'s HITL Governance Layer and Escalation
> Lifecycle (schema v2 in `core/registry.py`). `GET /agents` and
> `GET /engines` responses now also carry `type` and `capabilities`,
> since those fields are real as of registry schema v2 — no endpoint
> shape changed otherwise.

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

## Explicitly out of scope for this document

- Auth, rate limiting, pagination, versioning headers — MSHOPS.NET's
  concern, not specified here.
- Persistence/storage design for `GET /intents/:intent_id`.
- Any transport other than HTTP.
- Any real implementation. This is a contract for a system that does
  not exist yet.
