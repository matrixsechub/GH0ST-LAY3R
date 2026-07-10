"""
Ghost Layer Studio — Ecosystem Integration Adapter

# ADVANCEMENT: Ecosystem contracts
Safe local runner that validates ecosystem requests, executes the engine pipeline,
and wraps results in the stable ecosystem response contract.
"""

from __future__ import annotations
from typing import Any, Dict, Optional

from core.commands import parse_command
from core.contracts import (
    build_ecosystem_error_response,
    build_ecosystem_response,
    normalize_ecosystem_request,
    validate_ecosystem_request,
)
from core.engine import GhostLayerEngine, create_default_engine


def run_ecosystem_request(
    raw_request: dict,
    engine: Optional[GhostLayerEngine] = None,
) -> Dict[str, Any]:
    """
    Execute an ecosystem request through the Ghost Layer engine.

    Never mutates *raw_request*. Never exposes stack traces on failure.
    """
    normalized = normalize_ecosystem_request(raw_request)
    validation = validate_ecosystem_request(normalized)
    if not validation["ok"]:
        return build_ecosystem_error_response(
            normalized,
            validation["errors"],
            warnings=validation.get("warnings") or None,
        )

    command_result = parse_command(normalized["command"])
    if not command_result["ok"]:
        return build_ecosystem_error_response(
            normalized,
            [command_result["error"] or "invalid command"],
            warnings=validation.get("warnings") or None,
        )

    try:
        runner = engine if engine is not None else create_default_engine()
        include_diagnostics = bool(
            normalized.get("options", {}).get("include_diagnostics", False)
        )
        source = normalized.get("source", "ecosystem")
        envelope = runner.run(
            normalized["input"],
            source=source,
            include_diagnostics=include_diagnostics,
        )

        diagnostics = None
        if include_diagnostics and isinstance(envelope, dict):
            diagnostics = envelope.get("diagnostics")

        status = "warning" if validation.get("warnings") else "ok"
        return build_ecosystem_response(
            normalized,
            envelope,
            diagnostics=diagnostics,
            status=status,
            warnings=validation.get("warnings") or None,
        )
    except Exception as exc:
        return build_ecosystem_error_response(
            normalized,
            [str(exc.__class__.__name__)],
            warnings=validation.get("warnings") or None,
        )
