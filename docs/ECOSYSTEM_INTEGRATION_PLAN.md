# Ghost Layer Studio — Ecosystem Integration Plan (Pass 3)

## Purpose

Pass 3 prepares Ghost Layer Studio for integration into the MSHOPS / MatrixSecHub
ecosystem by defining stable request/response contracts, a tri-vector command
parser, and a safe local integration adapter. This pass is contract and adapter
foundation only — no deploy, no external calls, no auth inside Ghost core.

## Why Pass 3 exists

Pass 1 evolved the engine (shared types, additive metadata, conditional agents).
Pass 2 hardened observability (diagnostics, golden demo, import DAG guards).
Pass 3 adds the **ecosystem boundary**: a versioned contract that upstream
callers (HSX Cockpit, marketplace backends, Workers, FedGrade, automation
pipelines) can depend on without coupling to internal engine envelope details.

## Contract versions

| Constant | Value |
|---|---|
| `ENGINE_CONTRACT_VERSION` | `1.0.0` |
| `ECOSYSTEM_REQUEST_VERSION` | `1.0.0` |
| `ECOSYSTEM_RESPONSE_VERSION` | `1.0.0` |

Engine runtime version (`ENGINE_VERSION` in `core/types.py`) remains separate and
is echoed in responses as `engine_version`.

## Ecosystem request format

```json
{
  "request_id": "string",
  "source": "string",
  "command": "string",
  "input": "string",
  "context": {},
  "options": {}
}
```

- **Required:** `request_id`, `source`, `command`, `input` (non-empty).
- **Optional:** `context`, `options` — normalized to `{}` when absent.
- **Unknown source:** warns, does not fail validation.

## Ecosystem response format

```json
{
  "request_id": "string",
  "status": "ok|warning|error",
  "engine_version": "string",
  "contract_version": "string",
  "active_agents": [],
  "envelope": {},
  "diagnostics": null,
  "telemetry": {}
}
```

On validation failure, responses include an `errors` list and omit engine output.
Stack traces are never exposed.

`telemetry` extracts `duration_ms`, `recursion_depth`, `volatility`, and
`spectral_density` from the engine envelope where available.

## Tri-vector command syntax

```
CATEGORY::TARGET::PARAMETER
```

Example: `ANALYZE::GHOST_LAYER::DEFAULT`

Allowed categories: `ANALYZE`, `SCAN`, `GENERATE`, `SYNTH`, `DEPLOY`, `LOOP`,
`PLAN`, `AGGREGATE`.

Malformed commands (wrong segment count, empty segments, unknown category) fail
with a clear error — never silently accepted.

## Adapter flow

```
raw_request
  → normalize_ecosystem_request()   (copy; default context/options)
  → validate_ecosystem_request()      (contract validation)
  → parse_command()                   (tri-vector validation)
  → engine.run(input, source, include_diagnostics)
  → build_ecosystem_response()        (wrap envelope + telemetry)
```

Implementation: `integrations/ecosystem.py` → `run_ecosystem_request()`.

Diagnostics responsibility split:

- `core/diagnostics.py` validates **engine envelopes** (Pass 2).
- `core/contracts.py` validates **ecosystem wrappers** (Pass 3).
- Neither weakens the other.

## Integration targets

| Target | Role |
|---|---|
| HSX / Cockpit | Operator-facing command dispatch |
| marketplace-tracking-backend | Marketplace signal ingestion |
| mshops-public Worker | Public edge adapter (future route) |
| FedGrade Agent Plane | Graded agent orchestration |
| Automation Builder | Workflow-triggered analysis |
| Microservice Packager | Packaged engine deployment |

## Non-goals (this pass)

- No Cloudflare deploy or Worker route implementation
- No external network calls
- No auth implementation inside Ghost core
- No changes to default demo behavior (only `OperatorDoctrineAgent` activates)

## Verification commands

```bash
python3 -m scripts.run_demo
python3 -m scripts.check_import_dag
python3 -m scripts.check_golden_demo
python3 -m scripts.check_high_volatility_agents
python3 -m scripts.check_ecosystem_contract
python3 -m py_compile core/*.py agents/*.py scripts/*.py integrations/*.py
```

## Expected pass criteria

- All verification commands exit 0.
- `run_ecosystem_request()` with a valid sample returns `status: ok`.
- `include_diagnostics: true` attaches diagnostics with `ok: true`, `error_count: 0`.
- Malformed command returns `status: error` with an `errors` list.
- Default demo and golden checks remain backward-compatible.
- Runtime pipeline order preserved: `substrate → physics → agents → oversoul → output`.

---

## Pass 4: Local Engine HTTP Service

Pass 4 adds a stdlib-only local HTTP adapter (`integrations/http_service.py`)
that exposes Pass 3 ecosystem contracts over localhost JSON endpoints.

### Role

- The service acts as the **adapter boundary** between non-Python ecosystem
  components and the Ghost Layer engine.
- Node and backend systems should call this service **locally**
  (`127.0.0.1:8765` by default).
- The Cloudflare Worker (`mshops-public`) should **not** call this service
  directly until a proper bridge/proxy is available.
- **marketplace-tracking-backend** is the next intended consumer — implement a
  local Ghost client that POSTs ecosystem requests to `/run`.

### Endpoints

`GET /health`, `GET /contracts`, `POST /run`, `POST /run-diagnostics`,
`POST /validate-request`, `POST /validate-command`.

See `docs/LOCAL_ENGINE_SERVICE.md` for full route documentation.

### Verification (Pass 4)

Add to the Pass 3 verification list:

```bash
python -m scripts.check_local_service
```
