"""
Ghost Layer Studio — Golden Demo Regression Check

# ADVANCEMENT: Pass 2 diagnostics
Locks in the backward-compatible default behavior of the engine. It runs the
default engine through the same public path as scripts.run_demo
(create_default_engine().run(...)) and asserts the golden invariants:
only OperatorDoctrineAgent activates, the recursion trace shape is preserved,
and the Pass 1 additive metadata is present.

Run:  python3 -m scripts.check_golden_demo
Exits 0 on PASS, nonzero on FAIL.
"""

from __future__ import annotations
import sys
from typing import Any, Dict, List, Tuple

from core.engine import create_default_engine

# Same sample input scripts.run_demo uses (low volatility -> single agent).
GOLDEN_INPUT = "Boot sequence: Ghost Layer Studio online."


def _checks(envelope: Dict[str, Any]) -> List[Tuple[str, bool, str]]:
    payload = envelope.get("payload", {}) if isinstance(envelope, dict) else {}
    agents = payload.get("agents", []) if isinstance(payload, dict) else []
    active = [a.get("agent") for a in agents if isinstance(a, dict)]
    meta = envelope.get("meta", {}) if isinstance(envelope, dict) else {}
    metrics = meta.get("ingestion_metrics", {}) if isinstance(meta, dict) else {}
    trace = payload.get("recursion_trace", []) if isinstance(payload, dict) else []

    results: List[Tuple[str, bool, str]] = []
    results.append(("run_succeeds", isinstance(envelope, dict), "engine.run returned a dict"))
    results.append((
        "only_operator_doctrine_active",
        active == ["OperatorDoctrineAgent"],
        f"active agents = {active}",
    ))
    results.append((
        "predictive_agent_inactive",
        "PredictiveAgent" not in active,
        "PredictiveAgent must not activate by default",
    ))
    results.append((
        "stability_agent_inactive",
        "StabilityAgent" not in active,
        "StabilityAgent must not activate by default",
    ))
    results.append((
        "recursion_trace_present",
        isinstance(trace, list) and len(trace) > 0,
        f"recursion_trace has {len(trace) if isinstance(trace, list) else 'n/a'} entries",
    ))
    entry_shape_ok = all(
        isinstance(e, dict) and {"depth", "spectral_density", "volatility"} <= set(e)
        for e in (trace if isinstance(trace, list) else [])
    )
    results.append((
        "recursion_trace_entry_shape",
        entry_shape_ok,
        "each entry has depth/spectral_density/volatility",
    ))
    results.append(("engine_version_present", "engine_version" in envelope, "top-level engine_version"))
    results.append(("duration_ms_present", "duration_ms" in meta, "meta.duration_ms present"))
    results.append((
        "token_count_present",
        "token_count" in metrics,
        "meta.ingestion_metrics.token_count present",
    ))
    results.append((
        "unique_tokens_present",
        "unique_tokens" in metrics,
        "meta.ingestion_metrics.unique_tokens present",
    ))
    return results


def main() -> int:
    engine = create_default_engine()
    envelope = engine.run(GOLDEN_INPUT, source="golden-check")

    print("Ghost Layer Studio — Golden Demo Regression Check")
    print("=" * 52)
    results = _checks(envelope)
    failed = 0
    for name, ok, detail in results:
        status = "PASS" if ok else "FAIL"
        if not ok:
            failed += 1
        print(f"  [{status}] {name}: {detail}")
    print("-" * 52)
    if failed:
        print(f"RESULT: FAIL ({failed} check(s) failed)")
        return 1
    print("RESULT: PASS — default demo behavior is backward-compatible")
    return 0


if __name__ == "__main__":
    sys.exit(main())
