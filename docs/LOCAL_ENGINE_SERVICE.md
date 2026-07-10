# Ghost Layer Studio — Local Engine HTTP Service (Pass 4)

## Purpose

Pass 4 exposes Ghost Layer Studio as a **local stdlib-only HTTP service** so
ecosystem components (Node backends, automation scripts, local tooling) can call
the engine through the stable Pass 3 contract boundary without importing Python
modules directly.

## Why local service exists

Pass 3 defined ecosystem request/response contracts and a Python adapter
(`integrations/ecosystem.py`). Pass 4 adds an HTTP transport layer so non-Python
consumers — starting with **marketplace-tracking-backend** — can invoke the
engine over localhost using JSON.

## Local-only security posture

- Default bind address: **`127.0.0.1`** (not `0.0.0.0`).
- No authentication inside Ghost core.
- No outbound network calls from the service.
- Stack traces are never returned to callers.
- Intended for local development and co-located backend integration only.

## Routes

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Service liveness and version info |
| `GET` | `/contracts` | Contract versions and supported command categories |
| `POST` | `/run` | Execute ecosystem request (diagnostics off by default) |
| `POST` | `/run-diagnostics` | Execute with `include_diagnostics=true` forced |
| `POST` | `/validate-request` | Normalize + validate request and command (no engine run) |
| `POST` | `/validate-command` | Validate tri-vector command only |

Start the service:

```bash
python -m scripts.serve_engine
python -m scripts.serve_engine --host 127.0.0.1 --port 8765
```

## Request examples

### POST /run

```json
{
  "request_id": "req_001",
  "source": "hsx",
  "command": "ANALYZE::GHOST_LAYER::DEFAULT",
  "input": "Boot sequence: Ghost Layer Studio online.",
  "context": {},
  "options": {"include_diagnostics": false}
}
```

### POST /validate-command

```json
{
  "command": "ANALYZE::GHOST_LAYER::DEFAULT"
}
```

## Response examples

### GET /health

```json
{
  "status": "ok",
  "service": "ghost-layer-local",
  "engine_version": "1.1.0",
  "contract_version": "1.0.0"
}
```

### POST /run (success)

Returns the Pass 3 ecosystem response shape with `status: "ok"`, `envelope`,
and `telemetry.duration_ms`.

### POST /validate-request (failure)

HTTP 400 with validation details:

```json
{
  "ok": false,
  "request_validation": {"ok": false, "errors": ["..."], "warnings": []},
  "command_validation": {"ok": false, "error": "..."},
  "errors": ["..."]
}
```

## Error behavior

| Condition | HTTP status | Body |
|---|---|---|
| Unknown route | 404 | `{"status": "error", "error": "not found", ...}` |
| Unsupported method | 405 | `{"status": "error", "error": "method not allowed"}` |
| Malformed JSON | 400 | `{"status": "error", "error": "malformed JSON body"}` |
| Validation failure (`/validate-*`) | 400 | Validation result with `ok: false` |
| Engine run failure (`/run*`) | 200 | Ecosystem response with `status: "error"` |

## Non-goals

- No auth implementation inside Ghost core
- No Cloudflare Worker routes
- No production deploy logic
- No external network calls

## Verification commands

```bash
python -m scripts.run_demo
python -m scripts.check_import_dag
python -m scripts.check_golden_demo
python -m scripts.check_high_volatility_agents
python -m scripts.check_ecosystem_contract
python -m scripts.check_local_service
python -m py_compile core/*.py agents/*.py scripts/*.py integrations/*.py
```

On Windows PowerShell, if glob expansion fails, compile files individually or
iterate with a stdlib script — equivalent pass criteria apply.

## Next integration target

**marketplace-tracking-backend** should implement a local Ghost client that
calls `http://127.0.0.1:8765/run` with Pass 3 ecosystem requests when the
local engine service is running alongside the backend.
