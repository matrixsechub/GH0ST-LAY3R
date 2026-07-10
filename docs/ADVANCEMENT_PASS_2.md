# Ghost Layer Studio — Engine Advancement (Pass 2)

## Purpose

Pass 2 is an additive hardening and observability layer on top of Pass 1. It
adds deterministic engine diagnostics, golden-output regression protection, and
import-graph validation without changing the runtime pipeline or default demo
semantics. Stdlib-only; no new external dependencies; the pipeline order
`substrate -> physics -> agents -> oversoul -> output` and the default demo
behavior (only `OperatorDoctrineAgent` activates) are unchanged.

## Files changed

- `core/diagnostics.py` (new) — envelope validation helpers.
- `scripts/check_import_dag.py` (new) — static import-graph guard.
- `scripts/check_golden_demo.py` (new) — default-behavior regression check.
- `scripts/check_high_volatility_agents.py` (new) — Pass 1 enhancement lock-in.
- `core/engine.py` — opt-in `run(..., include_diagnostics=False)`.
- `docs/ADVANCEMENT_PASS_2.md` (this file).

## Diagnostic checks (`core/diagnostics.py`)

Read-only validators (never mutate the envelope), each returning
`{ok, checks, error_count, warning_count}`:

- `validate_envelope` — envelope is a dict; legacy top-level keys present;
  `engine_version` present.
- `validate_engine_meta` — `meta` present (warning if absent); `active_agents`
  is a list; `recursion_depth` int-compatible; `duration_ms` number-compatible;
  `ingestion_metrics` includes `token_count` and `unique_tokens`.
- `validate_recursion_trace` — each entry preserves `depth` / `spectral_density`
  / `volatility` (and integer `depth`).
- `validate_agent_outputs` — accepts a list or a payload dict; each activated
  agent output is a dict carrying a name and a `result` or `error`.
- `run_diagnostics` — aggregates the above plus `recursion_complete is True`
  where a trace exists and `agent_count == len(agents)`.

## Import DAG protection (`scripts/check_import_dag.py`)

Parses intra-repo imports (`core/*.py`, `agents/*.py`, `scripts/*.py`) with
`ast` and fails if:

- `core.physics`, `core.oversoul`, `core.output`, or `agents.constellation`
  import `core.engine`; or
- `core.types` (leaf) imports any higher-level runtime module.

## Golden demo validation (`scripts/check_golden_demo.py`)

Runs the default engine through the same public path as `scripts.run_demo` and
asserts: run succeeds; only `OperatorDoctrineAgent` active; `PredictiveAgent`
and `StabilityAgent` inactive; `recursion_trace` present with preserved entry
shape; `engine_version`, `duration_ms`, and `ingestion_metrics.token_count` /
`unique_tokens` present.

## High-volatility validation (`scripts/check_high_volatility_agents.py`)

Uses a deterministic mid-band input (`"System drift detected!!!"`, volatility
`~0.487`) and asserts: `OperatorDoctrineAgent`, `PredictiveAgent`, and
`StabilityAgent` all activate; their outputs exist; `stability_score` is bounded
`[0, 1]`; forecasts are identical across repeated runs; and active agents are
ordered by `priority`.

## Commands

```bash
python3 -m scripts.run_demo
python3 -m scripts.check_import_dag
python3 -m scripts.check_golden_demo
python3 -m scripts.check_high_volatility_agents
python3 -m py_compile core/*.py agents/*.py scripts/*.py
```

## Expected pass criteria

- `run_demo` boots and prints the envelope; default active agent is only
  `OperatorDoctrineAgent`.
- Each `check_*` script prints `RESULT: PASS` and exits 0.
- `py_compile` produces no errors.
- `run(..., include_diagnostics=True)` attaches a `diagnostics` block with
  `ok: true`; `run(...)` (default) contains no `diagnostics` key.

## Known constraints

- Stdlib only; no external dependencies.
- Diagnostics are read-only and never mutate the envelope.
- `core.diagnostics` must not import `core.engine`; `core.engine` may import
  `core.diagnostics`.
- `StabilityAgent`'s mid-band ceiling (`0.85`) excludes very high volatility, so
  the high-volatility check intentionally uses a mid-band input.
- Branch is stacked (see PR note); `main` still cannot boot on its own.
