"""
Ghost Layer Studio — Ecosystem Request/Response Contracts

# ADVANCEMENT: Ecosystem contracts
Stable, stdlib-only request/response shapes for MSHOPS / MatrixSecHub integration.
Validators inspect and normalize copies; they never mutate caller-supplied dicts.
"""

from __future__ import annotations
from copy import deepcopy
from typing import Any, Dict, List, Optional

from core.types import ENGINE_VERSION

ENGINE_CONTRACT_VERSION = "1.0.0"
ECOSYSTEM_REQUEST_VERSION = "1.0.0"
ECOSYSTEM_RESPONSE_VERSION = "1.0.0"

_REQUIRED_REQUEST_FIELDS = ("request_id", "source", "command", "input")
_KNOWN_SOURCES = frozenset(
    {
        "hsx",
        "cockpit",
        "mshops",
        "marketplace",
        "fedgrade",
        "automation",
        "cli",
        "demo",
        "ghost-layer",
    }
)


def normalize_ecosystem_request(raw: dict) -> dict:
    """Return a shallow copy of *raw* with optional fields normalized. Never mutates *raw*."""
    req = deepcopy(raw)
    if not isinstance(req.get("context"), dict):
        req["context"] = {}
    if not isinstance(req.get("options"), dict):
        req["options"] = {}
    return req


def validate_ecosystem_request(req: dict) -> dict:
    """
    Validate a normalized ecosystem request.

    Returns ``{"ok": bool, "errors": [...], "warnings": [...]}``.
    """
    errors: List[str] = []
    warnings: List[str] = []

    if not isinstance(req, dict):
        return {"ok": False, "errors": ["request must be a dict"], "warnings": []}

    for field in _REQUIRED_REQUEST_FIELDS:
        if field not in req:
            errors.append(f"missing required field '{field}'")
        elif not isinstance(req[field], str):
            errors.append(f"field '{field}' must be a string")

    if "input" in req and isinstance(req["input"], str) and not req["input"].strip():
        errors.append("input must not be empty")

    source = req.get("source")
    if isinstance(source, str) and source.strip() and source.strip().lower() not in _KNOWN_SOURCES:
        warnings.append(f"unknown source '{source}'")

    context = req.get("context")
    if context is not None and not isinstance(context, dict):
        errors.append("context must be a dict when present")

    options = req.get("options")
    if options is not None and not isinstance(options, dict):
        errors.append("options must be a dict when present")

    return {"ok": len(errors) == 0, "errors": errors, "warnings": warnings}


def _extract_active_agents(envelope: Dict[str, Any]) -> List[str]:
    meta = envelope.get("meta")
    if isinstance(meta, dict) and isinstance(meta.get("active_agents"), list):
        return list(meta["active_agents"])

    payload = envelope.get("payload")
    if isinstance(payload, dict):
        agents = payload.get("agents")
        if isinstance(agents, list):
            return [
                str(item["agent"])
                for item in agents
                if isinstance(item, dict) and item.get("agent")
            ]
    return []


def _build_telemetry(envelope: Dict[str, Any]) -> Dict[str, Any]:
    telemetry: Dict[str, Any] = {}
    meta = envelope.get("meta") if isinstance(envelope, dict) else None
    if isinstance(meta, dict):
        if "duration_ms" in meta:
            telemetry["duration_ms"] = meta["duration_ms"]
        if "recursion_depth" in meta:
            telemetry["recursion_depth"] = meta["recursion_depth"]
    if isinstance(envelope, dict):
        if "volatility" in envelope:
            telemetry["volatility"] = envelope["volatility"]
        if "spectral_density" in envelope:
            telemetry["spectral_density"] = envelope["spectral_density"]
    return telemetry


def build_ecosystem_response(
    request: dict,
    envelope: dict,
    diagnostics: Optional[dict] = None,
    *,
    status: str = "ok",
    warnings: Optional[List[str]] = None,
) -> dict:
    """
    Wrap an engine envelope in the ecosystem response contract.

    Extracts active_agents, duration_ms, recursion_depth, volatility, and
    spectral_density from *envelope* where available.
    """
    request_id = request.get("request_id", "") if isinstance(request, dict) else ""
    active_agents = _extract_active_agents(envelope if isinstance(envelope, dict) else {})
    engine_version = None
    if isinstance(envelope, dict):
        engine_version = envelope.get("engine_version", ENGINE_VERSION)

    resolved_status = status
    if warnings and resolved_status == "ok":
        resolved_status = "warning"

    return {
        "request_id": request_id,
        "status": resolved_status,
        "engine_version": engine_version,
        "contract_version": ECOSYSTEM_RESPONSE_VERSION,
        "active_agents": active_agents,
        "envelope": envelope if isinstance(envelope, dict) else {},
        "diagnostics": diagnostics,
        "telemetry": _build_telemetry(envelope if isinstance(envelope, dict) else {}),
    }


def build_ecosystem_error_response(
    request: dict,
    errors: List[str],
    *,
    warnings: Optional[List[str]] = None,
) -> dict:
    """Safe error response — never exposes stack traces."""
    request_id = ""
    if isinstance(request, dict) and isinstance(request.get("request_id"), str):
        request_id = request["request_id"]

    response: Dict[str, Any] = {
        "request_id": request_id,
        "status": "error",
        "engine_version": None,
        "contract_version": ECOSYSTEM_RESPONSE_VERSION,
        "active_agents": [],
        "envelope": {},
        "diagnostics": None,
        "telemetry": {},
        "errors": list(errors),
    }
    if warnings:
        response["warnings"] = list(warnings)
    return response
