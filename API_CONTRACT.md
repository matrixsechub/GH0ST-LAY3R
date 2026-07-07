# MSHOPS.NET Backend API Contract (Draft v0)

> **Status: draft specification, not implemented.** This document
> describes the HTTP API a future MSHOPS.NET backend service should
> expose. No server code exists in this repo and none should be added
> here — this repo defines the contract; MSHOPS.NET (a separate
> service/repo) implements it. See `AGENT_HQ.md` for the underlying
> concepts (engine, agent, registry, lane, mode, status) these
> endpoints operate on.

## Design principle

Every endpoint maps onto something that already exists and runs in this
repo today. Nothing here invents new server-side behavior beyond
exposing the existing engine and registry over HTTP.

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

List engine bindings. Maps onto `agents/registry.yaml`'s `engines:` list.

## Explicitly out of scope for this document

- Auth, rate limiting, pagination, versioning headers — MSHOPS.NET's
  concern, not specified here.
- Persistence/storage design for `GET /intents/:intent_id`.
- Any transport other than HTTP.
- Any real implementation. This is a contract for a system that does
  not exist yet.
