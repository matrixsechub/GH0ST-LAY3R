"""
Ghost Layer Studio — High-Volatility Agent Activation Check

# ADVANCEMENT: Pass 2 diagnostics
Locks in the Pass 1 intended enhancement: for a deterministic mid-band
volatility input, OperatorDoctrineAgent, PredictiveAgent, and StabilityAgent
all activate, their outputs are well-formed, the stability score is bounded,
forecasts are deterministic across runs, and active agents are ordered by
priority.

Run:  python3 -m scripts.check_high_volatility_agents
Exits 0 on PASS, nonzero on FAIL.
"""

from __future__ import annotations
import sys
from typing import Any, Dict, List, Tuple

from core.engine import create_default_engine

# 3 exclamation marks -> tanh(3/5) then routine damping (-0.05) -> ~0.487,
# which satisfies volatility > 0.3 and 0.2 < volatility < 0.85 deterministically.
MID_BAND_INPUT = "System drift detected!!!"


def _active_map(envelope: Dict[str, Any]) -> Dict[str, Any]:
    payload = envelope.get("payload", {})
    agents = payload.get("agents", []) if isinstance(payload, dict) else []
    return {a.get("agent"): a.get("result") for a in agents if isinstance(a, dict)}


def _active_order(envelope: Dict[str, Any]) -> List[str]:
    payload = envelope.get("payload", {})
    agents = payload.get("agents", []) if isinstance(payload, dict) else []
    return [a.get("agent") for a in agents if isinstance(a, dict)]


def main() -> int:
    engine = create_default_engine()
    priority_by_name = {a.name: getattr(a, "priority", 100) for a in engine.constellation.agents}

    envelope = engine.run(MID_BAND_INPUT, source="hivol-check")
    envelope2 = engine.run(MID_BAND_INPUT, source="hivol-check")

    active = _active_map(envelope)
    order = _active_order(envelope)
    volatility = envelope.get("volatility")
    predictive = active.get("PredictiveAgent")
    stability = active.get("StabilityAgent")
    score = stability.get("stability_score") if isinstance(stability, dict) else None
    order_priorities = [priority_by_name.get(n, 100) for n in order]

    results: List[Tuple[str, bool, str]] = []
    results.append((
        "volatility_mid_band",
        isinstance(volatility, (int, float)) and 0.3 < volatility < 0.85,
        f"volatility = {volatility}",
    ))
    results.append(("operator_doctrine_active", "OperatorDoctrineAgent" in active, "must be active"))
    results.append(("predictive_active", "PredictiveAgent" in active, "must be active"))
    results.append(("stability_active", "StabilityAgent" in active, "must be active"))
    results.append(("predictive_output_present", isinstance(predictive, dict) and bool(predictive), f"{predictive}"))
    results.append(("stability_output_present", isinstance(stability, dict) and bool(stability), f"{stability}"))
    results.append((
        "stability_score_bounded",
        isinstance(score, (int, float)) and 0.0 <= score <= 1.0,
        f"stability_score = {score}",
    ))
    results.append((
        "forecast_deterministic",
        _active_map(envelope2).get("PredictiveAgent") == predictive,
        "repeated run produces identical PredictiveAgent payload",
    ))
    results.append((
        "active_order_by_priority",
        order_priorities == sorted(order_priorities),
        f"order {order} -> priorities {order_priorities}",
    ))

    print("Ghost Layer Studio — High-Volatility Agent Activation Check")
    print("=" * 60)
    print(f"  input: {MID_BAND_INPUT!r}")
    failed = 0
    for name, ok, detail in results:
        status = "PASS" if ok else "FAIL"
        if not ok:
            failed += 1
        print(f"  [{status}] {name}: {detail}")
    print("-" * 60)
    if failed:
        print(f"RESULT: FAIL ({failed} check(s) failed)")
        return 1
    print("RESULT: PASS — Pass 1 high-volatility enhancement is locked in")
    return 0


if __name__ == "__main__":
    sys.exit(main())
