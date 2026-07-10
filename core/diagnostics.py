"""
Ghost Layer Studio — Engine Diagnostics

# ADVANCEMENT: Pass 2 diagnostics
Deterministic, stdlib-only validators for the engine output envelope. These
helpers inspect (never mutate) a run envelope and report structural/contract
health, providing golden-output regression protection and optional in-run
diagnostics.

Import contract: this is a low-level module. It MUST NOT import core.engine
(or any higher-level runtime module) so that core.engine can safely import it.
"""

from __future__ import annotations
from typing import Any, Dict, List, Union

# Original (pre-Pass-1) top-level envelope keys that must always be present.
_LEGACY_TOP_LEVEL_KEYS = (
    "intent_id",
    "source",
    "operator_axis",
    "spectral_density",
    "volatility",
    "payload",
    "timestamp",
    "meta",
)


class _Checks:
    """Small accumulator producing the canonical diagnostics report shape."""

    def __init__(self) -> None:
        self.checks: List[Dict[str, Any]] = []
        self.error_count = 0
        self.warning_count = 0

    def add(self, name: str, ok: bool, detail: str, *, warning: bool = False) -> bool:
        self.checks.append({"name": name, "ok": bool(ok), "detail": str(detail)})
        if not ok:
            if warning:
                self.warning_count += 1
            else:
                self.error_count += 1
        return ok

    def extend(self, other: Dict[str, Any]) -> None:
        """Merge another report's checks and counts into this one."""
        self.checks.extend(other.get("checks", []))
        self.error_count += int(other.get("error_count", 0))
        self.warning_count += int(other.get("warning_count", 0))

    def result(self) -> Dict[str, Any]:
        return {
            # Overall health ignores warnings by design (advisory only).
            "ok": self.error_count == 0,
            "checks": self.checks,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
        }


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _is_number(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


# ---------------------------------------------------------------------------
# Individual validators (each returns the canonical report shape)
# ---------------------------------------------------------------------------

def validate_envelope(envelope: Dict[str, Any]) -> Dict[str, Any]:
    """Validate top-level envelope structure and the Pass 1 version stamp."""
    c = _Checks()
    if not c.add(
        "envelope_is_dict",
        isinstance(envelope, dict),
        "envelope must be a dict",
    ):
        return c.result()

    for key in _LEGACY_TOP_LEVEL_KEYS:
        c.add(
            f"top_level_key:{key}",
            key in envelope,
            f"expected top-level key '{key}'",
        )

    c.add(
        "engine_version_present",
        "engine_version" in envelope,
        "engine_version (Pass 1 additive stamp) must be present",
    )
    return c.result()


def validate_recursion_trace(trace: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Validate recursion_trace entry shape: depth/spectral_density/volatility."""
    c = _Checks()
    if not c.add(
        "recursion_trace_is_list",
        isinstance(trace, list),
        "recursion_trace must be a list",
    ):
        return c.result()

    required = ("depth", "spectral_density", "volatility")
    for idx, entry in enumerate(trace):
        if not c.add(
            f"trace_entry_is_dict:{idx}",
            isinstance(entry, dict),
            "each recursion_trace entry must be a dict",
        ):
            continue
        for field_name in required:
            c.add(
                f"trace_entry_field:{idx}:{field_name}",
                field_name in entry,
                f"recursion_trace[{idx}] missing '{field_name}'",
            )
        if isinstance(entry, dict) and "depth" in entry:
            c.add(
                f"trace_entry_depth_int:{idx}",
                _is_int(entry.get("depth")),
                f"recursion_trace[{idx}].depth must be int",
            )
    return c.result()


def validate_agent_outputs(agent_outputs: Union[List[Any], Dict[str, Any]]) -> Dict[str, Any]:
    """Validate the agent outputs list (or a payload dict containing it)."""
    c = _Checks()

    # Accept either the raw list or a payload/envelope dict carrying "agents".
    if isinstance(agent_outputs, dict):
        outputs = agent_outputs.get("agents")
    else:
        outputs = agent_outputs

    if not c.add(
        "agent_outputs_is_list",
        isinstance(outputs, list),
        "agent outputs must be a list",
    ):
        return c.result()

    for idx, item in enumerate(outputs):
        if not c.add(
            f"agent_output_is_dict:{idx}",
            isinstance(item, dict),
            "each agent output must be a dict",
        ):
            continue
        c.add(
            f"agent_output_has_name:{idx}",
            bool(item.get("agent")),
            "agent output must carry a non-empty 'agent' name",
        )
        # Each activated agent must be non-empty: it either produced a result
        # or reported an error.
        c.add(
            f"agent_output_non_empty:{idx}",
            ("result" in item) or ("error" in item),
            "agent output must contain 'result' or 'error'",
        )
    return c.result()


def validate_engine_meta(envelope: Dict[str, Any]) -> Dict[str, Any]:
    """Validate the Pass 1 additive metadata inside envelope['meta']."""
    c = _Checks()
    if not isinstance(envelope, dict):
        c.add("meta_envelope_is_dict", False, "envelope must be a dict")
        return c.result()

    meta = envelope.get("meta")
    # meta is a Pass 1 addition; treat a total absence as a warning, not a hard
    # error, so pre-Pass-1 envelopes degrade gracefully.
    if meta is None:
        c.add("meta_present", False, "meta block absent", warning=True)
        return c.result()

    if not c.add("meta_is_dict", isinstance(meta, dict), "meta must be a dict"):
        return c.result()

    active = meta.get("active_agents")
    c.add(
        "active_agents_is_list",
        isinstance(active, list),
        "meta.active_agents must be a list",
    )
    c.add(
        "recursion_depth_int",
        _is_int(meta.get("recursion_depth")),
        "meta.recursion_depth must be int-compatible",
    )
    c.add(
        "duration_ms_number",
        _is_number(meta.get("duration_ms")),
        "meta.duration_ms must be number-compatible",
    )

    metrics = meta.get("ingestion_metrics")
    if c.add(
        "ingestion_metrics_is_dict",
        isinstance(metrics, dict),
        "meta.ingestion_metrics must be a dict",
    ):
        c.add(
            "ingestion_metrics_token_count",
            "token_count" in metrics,
            "meta.ingestion_metrics.token_count must be present",
        )
        c.add(
            "ingestion_metrics_unique_tokens",
            "unique_tokens" in metrics,
            "meta.ingestion_metrics.unique_tokens must be present",
        )
    return c.result()


def run_diagnostics(envelope: Dict[str, Any]) -> Dict[str, Any]:
    """
    Aggregate all validators into a single report. Purely read-only.
    """
    c = _Checks()

    c.extend(validate_envelope(envelope))
    c.extend(validate_engine_meta(envelope))

    payload = envelope.get("payload") if isinstance(envelope, dict) else None
    payload = payload if isinstance(payload, dict) else {}

    trace = payload.get("recursion_trace", [])
    c.extend(validate_recursion_trace(trace if isinstance(trace, list) else []))

    c.extend(validate_agent_outputs(payload.get("agents", [])))

    # recursion_complete must be True whenever recursion produced a trace.
    if isinstance(trace, list) and len(trace) > 0:
        c.add(
            "recursion_complete_true",
            payload.get("recursion_complete") is True,
            "recursion_complete must be True when recursion_trace is non-empty",
        )

    # An activated-agent count sanity check: default demo activates exactly one
    # agent, but here we only assert the structural invariant that the fused
    # agent_count matches the number of agent outputs when both are present.
    if "agent_count" in payload and isinstance(payload.get("agents"), list):
        c.add(
            "agent_count_matches_outputs",
            payload.get("agent_count") == len(payload["agents"]),
            "payload.agent_count must equal len(payload.agents)",
        )

    return c.result()
