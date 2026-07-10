# Ghost Layer Studio — Engine Advancement (Pass 1)

Additive, behavior-preserving engine advancement. Stdlib-only; boot sequence and
the `substrate -> physics -> agents -> oversoul -> output` pipeline are preserved.
Run entrypoint is unchanged: `python3 -m scripts.run_demo`.

## Changes

1. Shared types extracted to leaf module `core/types.py`
   (`OperatorAxis`, `IntentVector`, `ENGINE_VERSION = "1.1.0"`, `clamp01()`),
   removing the historical circular dependency at its source. `IntentVector`
   and `OperatorAxis` remain importable from `core.engine` for backward compat.

   Import DAG (one-directional):

   ```
   core.types      (leaf; stdlib only)
   core.substrate  (leaf)
   core.physics       -> core.types, core.substrate
   core.oversoul      -> core.types, core.substrate
   core.output        -> core.types, core.substrate
   agents.constellation -> core.types, core.substrate
   core.engine        -> core.types, core.substrate, core.physics,
                         core.oversoul, core.output, agents.constellation
   ```

2. `DefaultOversoul.recurse` reimplemented as a bounded iterative loop —
   identical `recursion_trace` entries, clamped `+0.01` refinement, and terminal
   `recursion_complete` marker, but deterministic termination with no Python
   call-stack limit (verified at `max_depth=200000`). Negative/zero `max_depth`
   is a guarded no-op.

3. `DefaultDominionPhysics.apply` uses the shared `clamp01()` (formulas
   unchanged; volatility/spectral density guaranteed within `[0, 1]`).

4. Agent constellation: added `priority` (stable-sorted, default order
   preserved) and two read-only, deterministic, conditionally-activating agents:
   - `PredictiveAgent` — activates when `volatility > 0.3`; emits a next-cycle
     volatility forecast.
   - `StabilityAgent` — activates for mid-band volatility `0.2 < v < 0.85`;
     emits a `clamp01`-bounded stability score.

5. Additive telemetry + envelope metadata: top-level `engine_version` plus
   `meta.recursion_depth`, `meta.active_agents`, `meta.ingestion_metrics`
   (`token_count`/`unique_tokens`), and `meta.duration_ms`. No existing envelope
   keys were removed, renamed, or restructured.

## Verification results

- `python3 -m scripts.run_demo` — boots; default output preserved: only
  `OperatorDoctrineAgent` activates; `recursion_trace` shape unchanged
  (depth 0/1/2, `recursion_complete: true`); additive `meta` + `engine_version`
  present.
- High-volatility mid-band smoke (`"System drift detected!!!"`, volatility
  `~0.487`): `OperatorDoctrineAgent`, `PredictiveAgent`, and `StabilityAgent`
  all activate; forecast is deterministic; `stability_score` bounded to `[0, 1]`;
  agents do not mutate shared state.
- `python3 -m py_compile core/*.py agents/*.py scripts/*.py` — passes.

Verdict: Advancement applied.
