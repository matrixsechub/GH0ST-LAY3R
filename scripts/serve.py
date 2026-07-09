"""
Ghost Layer Studio — HQ HTTP Server (dev-grade)

Responsibilities:
- Thin HTTP interface over GhostLayerEngine for local development and integration
- Implements a subset of API_CONTRACT.md v2 endpoints called by ttx-operator-shell
- Python stdlib only: http.server, json, uuid, datetime, threading, urllib.parse
- In-memory state: AuditEvent, EscalationEvent, OperatorSessionRecord, AgentPool lists
- No persistence — state clears on restart; persistence is MSHOPS.NET's concern

Usage:
    PYTHONPATH=. python3 scripts/serve.py [--host 127.0.0.1] [--port 8000]

Endpoints:
    POST /intents                   — run engine, GOV-7 header support
    GET  /hq/health                 — computed HQHealthRecord (includes intake counts)
    GET  /audit                     — AuditEvent[] (filter: event_type, actor_id, since)
    GET  /escalations               — EscalationEvent[] (filter: status, severity)
    GET  /agents                    — agents from registry.yaml
    GET  /engines                   — engines from registry.yaml
    GET  /operators                 — operators from registry.yaml
    GET  /agent-pools               — in-memory AgentPool[] (empty initially)
    GET  /agents/intake-agent-v2    — registry entry for intake-agent-v2
    GET  /intake-agent-v2/lifecycle — IntakeLifecycleRecord[] (append-only, since server start)
    GET  /intake-agent-v2/metrics   — queue depth / processing / escalated / completed counts

GOV-4 note: This file is a bounded, operator-approved relaxation of the
no-HTTP-server constraint documented in CLAUDE.md. It is not a production
daemon — no systemd unit, Docker image, or process manager is defined here.
See CLAUDE.md "Running things" for the authorised scope.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

# -- Optional PyYAML ----------------------------------------------------------
# If pyyaml is installed: registry.yaml is parsed at startup.
# If not: the hardcoded fallback (a Python mirror of agents/registry.yaml) is used.
try:
    import yaml as _yaml  # type: ignore
    _YAML_AVAILABLE = True
except ImportError:
    _yaml = None
    _YAML_AVAILABLE = False

# Ensure repo root is on sys.path when run as `python3 scripts/serve.py`
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from core.engine import create_default_engine  # noqa: E402  (after sys.path fix)


# ---------------------------------------------------------------------------
# Registry loading
# ---------------------------------------------------------------------------

_REGISTRY_YAML_PATH = os.path.join(_REPO_ROOT, "agents", "registry.yaml")

# Hardcoded fallback — mirrors agents/registry.yaml (schema v3).
# Update this if registry.yaml changes and pyyaml is unavailable.
_REGISTRY_FALLBACK: dict = {
    "schema_version": 3,
    "engines": [
        {
            "type": "engine",
            "id": "ghost-layer-core",
            "status": "active",
            "description": (
                "The Python engine in this repo (core/ + agents/): substrate -> "
                "dominion -> constellation -> oversoul -> reactor. The only engine "
                "that actually exists and runs today."
            ),
            "entrypoint": "core.engine.create_default_engine",
            "capabilities": [
                "substrate-ingestion",
                "dominion-physics",
                "agent-constellation",
                "oversoul-fusion",
                "output-reactor",
            ],
        }
    ],
    "operators": [
        {
            "type": "operator",
            "operator_id": "lupe",
            "role": "HITL",
            "authority": "root",
            "priority_lane": "operator",
            "escalation_required": True,
            "capabilities": ["override", "arbitration", "review", "priority"],
            "binding": "HQ-level",
        }
    ],
    "agents": [
        {
            "type": "agent",
            "id": "adversarial-intel-agent",
            "name": "AdversarialIntelAgent",
            "module_path": "agents.constellation.AdversarialIntelAgent",
            "engine": "ghost-layer-core",
            "mode": "conditional",
            "status": "active",
            "tags": ["security", "volatility"],
            "capabilities": ["threat-detection"],
            "description": "Flags elevated/moderate threat level based on substrate volatility.",
            "produces": {"threat_level": "str", "spectral_density": "float", "volatility": "float"},
        },
        {
            "type": "agent",
            "id": "containment-agent",
            "name": "ContainmentAgent",
            "module_path": "agents.constellation.ContainmentAgent",
            "engine": "ghost-layer-core",
            "mode": "conditional",
            "status": "active",
            "tags": ["security", "containment"],
            "capabilities": ["containment-action", "volatility-clamp"],
            "description": "Activates on high volatility or escalation tags; recommends a volatility clamp.",
            "produces": {
                "containment_action": "str",
                "volatility_before": "float",
                "recommended_clamp": "float",
            },
        },
        {
            "type": "agent",
            "id": "operator-doctrine-agent",
            "name": "OperatorDoctrineAgent",
            "module_path": "agents.constellation.OperatorDoctrineAgent",
            "engine": "ghost-layer-core",
            "mode": "always-on",
            "status": "active",
            "tags": ["doctrine"],
            "capabilities": ["doctrine-echo"],
            "description": "Always active; echoes operator doctrine and intent tags.",
            "produces": {"doctrine": "str", "intent_tags": "list", "spectral_density": "float"},
        },
        {
            "type": "agent",
            "id": "route-advisory-agent",
            "name": "RouteAdvisoryAgent",
            "module_path": "agents.constellation.RouteAdvisoryAgent",
            "engine": "ghost-layer-core",
            "mode": "always-on",
            "status": "active",
            "tags": ["routing", "advisory"],
            "capabilities": ["lane-suggestion"],
            "description": (
                "Always active; suggests a generic routing lane based on "
                "tag/volatility heuristics. Advisory only."
            ),
            "produces": {"suggested_lane": "str", "confidence": "str", "basis": "dict"},
        },
        {
            "type": "agent",
            "id": "intake-agent-v2",
            "name": "IntakeAgentV2",
            "module_path": "agents.constellation.IntakeAgentV2",
            "engine": "ghost-layer-core",
            "mode": "always-on",
            "status": "experimental",
            "tags": ["intake", "lifecycle", "queue", "operator-surface"],
            "capabilities": [
                "intent-intake",
                "queue-management",
                "lifecycle-tracking",
                "operator-action-hooks",
            ],
            "description": (
                "Classifies intents into lifecycle stages and tracks queue metrics "
                "for HQ observability. Status experimental — requires GOV-4 operator "
                "approval to promote to active."
            ),
            "produces": {
                "intake_status": "str",
                "lifecycle_stage": "str",
                "queue_depth": "int",
                "operator_action_required": "bool",
                "operator_actions_available": "list",
            },
        },
    ],
}


def _load_registry() -> dict:
    """Load agents/registry.yaml; fall back to _REGISTRY_FALLBACK if pyyaml absent."""
    if _YAML_AVAILABLE and _yaml is not None:
        try:
            with open(_REGISTRY_YAML_PATH, "r", encoding="utf-8") as fh:
                data = _yaml.safe_load(fh)
            if isinstance(data, dict):
                return data
        except Exception as exc:
            print(f"[SERVE] Warning: could not parse registry.yaml ({exc}); using fallback.")
    return _REGISTRY_FALLBACK


# ---------------------------------------------------------------------------
# Module-level shared state
# ---------------------------------------------------------------------------

_engine = create_default_engine()
_registry: dict = _load_registry()
_lock = threading.Lock()

_audit_log: list = []        # AuditEvent dicts, append-only
_escalations: list = []      # EscalationEvent dicts
_sessions: list = []         # OperatorSessionRecord dicts
_pools: list = []            # AgentPool dicts (empty until created via future endpoint)
_intake_lifecycle: list = []  # IntakeLifecycleRecord dicts, append-only


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _registered_operator_id() -> str:
    operators = _registry.get("operators", [])
    return operators[0].get("operator_id", "lupe") if operators else "lupe"


def _operator_online() -> bool:
    """True if any OperatorSessionRecord has ended_at = None."""
    return any(s.get("ended_at") is None for s in _sessions)


def _active_session_id() -> str | None:
    for s in reversed(_sessions):
        if s.get("ended_at") is None:
            return s["session_id"]
    return None


# ---------------------------------------------------------------------------
# State-mutation helpers (call inside _lock)
# ---------------------------------------------------------------------------

def _write_audit(
    event_type: str,
    actor_id: str,
    actor_type: str,
    *,
    target_id: str = "",
    target_type: str = "",
    payload: dict | None = None,
) -> dict:
    """Append an AuditEvent to _audit_log. Caller must hold _lock."""
    event: dict = {
        "id": str(uuid.uuid4()),
        "type": "audit",
        "event_type": event_type,
        "actor_id": actor_id,
        "actor_type": actor_type,
        "timestamp": _now(),
        "target_id": target_id,
        "target_type": target_type,
        "payload": payload or {},
    }
    _audit_log.append(event)
    return event


def _open_session(operator_id: str) -> dict:
    """Create a new OperatorSessionRecord. Caller must hold _lock."""
    session: dict = {
        "session_id": str(uuid.uuid4()),
        "type": "operator-session",
        "operator_id": operator_id,
        "started_at": _now(),
        "ended_at": None,
        "active_intent_ids": [],
        "notes": "",
    }
    _sessions.append(session)
    _write_audit(
        "operator.session_opened",
        actor_id=operator_id,
        actor_type="operator",
        target_id=session["session_id"],
        target_type="operator-session",
    )
    return session


def _compute_hq_health() -> dict:
    """Compute an HQHealthRecord from current in-memory state. Caller must hold _lock."""
    engines = _registry.get("engines", [])
    agents_list = _registry.get("agents", [])
    active_engine_ids = [e["id"] for e in engines if e.get("status") == "active"]
    active_agent_ids = [a["id"] for a in agents_list if a.get("status") == "active"]
    open_escalation_count = sum(
        1 for e in _escalations if e.get("status") in ("pending", "acknowledged")
    )
    intake_queue_depth = sum(1 for r in _intake_lifecycle if r.get("stage") == "queued")
    intake_processing_count = sum(1 for r in _intake_lifecycle if r.get("stage") == "processing")
    intake_escalated_count = sum(1 for r in _intake_lifecycle if r.get("stage") == "escalated")
    return {
        "type": "hq-health",
        "timestamp": _now(),
        "active_engine_ids": active_engine_ids,
        "degraded_engine_ids": [],
        "unavailable_engine_ids": [],
        "active_agent_ids": active_agent_ids,
        "open_escalation_count": open_escalation_count,
        "operator_online": _operator_online(),
        "intake_queue_depth": intake_queue_depth,
        "intake_processing_count": intake_processing_count,
        "intake_escalated_count": intake_escalated_count,
    }


def _maybe_raise_gov3(intent_id: str, request_tags: list, volatility: float) -> None:
    """
    GOV-3: raise an EscalationEvent when an intent carries escalation-triggering
    tags OR when engine-computed volatility is critically high. Caller must hold _lock.
    """
    GOV3_TAGS = {"escalate", "high-risk", "critical"}
    triggered_tags = GOV3_TAGS & set(request_tags)
    high_volatility = volatility >= 0.8

    if not (triggered_tags or high_volatility):
        return

    reason_parts: list = []
    if triggered_tags:
        reason_parts.append(f"tags={sorted(triggered_tags)}")
    if high_volatility:
        reason_parts.append(f"volatility={volatility:.3f}")

    severity = "critical" if volatility >= 0.9 or "critical" in triggered_tags else "high"

    esc: dict = {
        "id": str(uuid.uuid4()),
        "type": "escalation",
        "trigger_rule": "GOV-3",
        "intent_id": intent_id,
        "severity": severity,
        "reason": f"Operator review required: {'; '.join(reason_parts)}.",
        "agent_ids": ["adversarial-intel-agent", "containment-agent"],
        "status": "pending",
        "created_at": _now(),
        "resolved_at": None,
        "resolution": "",
    }
    _escalations.append(esc)
    _write_audit(
        "escalation.created",
        actor_id="ghost-layer-core",
        actor_type="system",
        target_id=esc["id"],
        target_type="escalation",
        payload={"trigger_rule": "GOV-3", "severity": severity},
    )


# ---------------------------------------------------------------------------
# HTTP response helpers
# ---------------------------------------------------------------------------

def _send_json(handler: BaseHTTPRequestHandler, code: int, data: object) -> None:
    body = json.dumps(data, default=str).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(body)


def _send_error(handler: BaseHTTPRequestHandler, code: int, message: str) -> None:
    _send_json(handler, code, {"error": message})


def _parse_path(raw_path: str) -> tuple[str, dict]:
    parsed = urlparse(raw_path)
    params = {
        k: v[0] if len(v) == 1 else v
        for k, v in parse_qs(parsed.query).items()
    }
    return parsed.path.rstrip("/"), params


# ---------------------------------------------------------------------------
# Request handler
# ---------------------------------------------------------------------------

class GhostHQHandler(BaseHTTPRequestHandler):

    def log_message(self, fmt: str, *args) -> None:
        # Replace Apache combined log format with a compact single line.
        # args: (request_line, response_code, response_size)
        print(f"  {self.command} {self.path.split('?')[0]}  →  {args[1]}", flush=True)

    # -- CORS pre-flight -------------------------------------------------------

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type, X-Ghost-Operator-Online",
        )
        self.end_headers()

    # -- GET -------------------------------------------------------------------

    def do_GET(self) -> None:
        path, params = _parse_path(self.path)
        with _lock:
            if path == "/hq/health":
                _send_json(self, 200, _compute_hq_health())
            elif path == "/audit":
                self._get_audit(params)
            elif path == "/escalations":
                self._get_escalations(params)
            elif path == "/agents":
                _send_json(self, 200, _registry.get("agents", []))
            elif path == "/engines":
                _send_json(self, 200, _registry.get("engines", []))
            elif path == "/operators":
                _send_json(self, 200, _registry.get("operators", []))
            elif path == "/agent-pools":
                _send_json(self, 200, list(_pools))
            elif path == "/agents/intake-agent-v2":
                self._get_intake_agent_entry()
            elif path == "/intake-agent-v2/lifecycle":
                _send_json(self, 200, list(_intake_lifecycle))
            elif path == "/intake-agent-v2/metrics":
                self._get_intake_metrics()
            else:
                _send_error(self, 404, f"No route: {path}")

    # -- POST ------------------------------------------------------------------

    def do_POST(self) -> None:
        path, _ = _parse_path(self.path)
        length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(length) if length > 0 else b"{}"
        try:
            body: dict = json.loads(raw_body or b"{}")
        except json.JSONDecodeError:
            _send_error(self, 400, "Invalid JSON body")
            return

        if path == "/intents":
            self._post_intents(body)
        else:
            _send_error(self, 404, f"No route: {path}")

    # -- Endpoint implementations ----------------------------------------------

    def _post_intents(self, body: dict) -> None:
        raw = body.get("raw", "")
        source = body.get("source", "api")
        request_tags = body.get("tags", [])

        if not isinstance(raw, str) or not raw.strip():
            _send_error(self, 400, "'raw' must be a non-empty string")
            return

        gov7_active = (
            self.headers.get("X-Ghost-Operator-Online", "").lower() == "true"
        )

        # Run engine outside the lock — engine.run() is stateless per call.
        try:
            envelope = _engine.run(raw, source=source)
        except Exception as exc:
            _send_error(self, 500, f"Engine error: {exc}")
            return

        intent_id: str = envelope.get("intent_id", str(uuid.uuid4()))
        volatility: float = float(envelope.get("volatility", 0.0))

        with _lock:
            op_id = _registered_operator_id()

            if gov7_active:
                # GOV-7: operator-presence posture — open session if none active.
                if not _operator_online():
                    sess = _open_session(op_id)
                else:
                    sid = _active_session_id()
                    if sid:
                        for s in _sessions:
                            if s["session_id"] == sid:
                                s["active_intent_ids"].append(intent_id)
                                break
                _write_audit(
                    "gov_rule.fired",
                    actor_id=op_id,
                    actor_type="operator",
                    target_id=intent_id,
                    target_type="intent",
                    payload={"rule": "GOV-7", "source": source},
                )

            _write_audit(
                "intent.submitted",
                actor_id=op_id if gov7_active else source,
                actor_type="operator" if gov7_active else "system",
                target_id=intent_id,
                target_type="intent",
                payload={"source": source, "gov7_active": gov7_active},
            )

            # GOV-3: raise escalation on high-risk tags or critically high volatility.
            _maybe_raise_gov3(intent_id, request_tags, volatility)

        _send_json(self, 200, envelope)

    def _get_audit(self, params: dict) -> None:
        events = list(_audit_log)
        if et := params.get("event_type"):
            events = [e for e in events if e.get("event_type") == et]
        if ai := params.get("actor_id"):
            events = [e for e in events if e.get("actor_id") == ai]
        if since := params.get("since"):
            events = [e for e in events if e.get("timestamp", "") >= since]
        _send_json(self, 200, events)

    def _get_escalations(self, params: dict) -> None:
        escs = list(_escalations)
        if status := params.get("status"):
            allowed = {s.strip() for s in status.split(",")}
            escs = [e for e in escs if e.get("status") in allowed]
        if severity := params.get("severity"):
            escs = [e for e in escs if e.get("severity") == severity]
        _send_json(self, 200, escs)

    def _get_intake_agent_entry(self) -> None:
        agents = _registry.get("agents", [])
        for agent in agents:
            if agent.get("id") == "intake-agent-v2":
                _send_json(self, 200, agent)
                return
        _send_error(self, 404, "intake-agent-v2 not found in registry")

    def _get_intake_metrics(self) -> None:
        records = list(_intake_lifecycle)
        by_stage: dict = {}
        for r in records:
            s = r.get("stage", "unknown")
            by_stage[s] = by_stage.get(s, 0) + 1
        _send_json(self, 200, {
            "queue_depth": by_stage.get("queued", 0),
            "processing_count": by_stage.get("processing", 0),
            "escalated_count": by_stage.get("escalated", 0),
            "completed_count": by_stage.get("completed", 0),
            "total": len(records),
        })


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ghost Layer HQ HTTP server (dev-grade, stdlib only)"
    )
    parser.add_argument(
        "--host", default="127.0.0.1",
        help="Bind address (default: 127.0.0.1; use 0.0.0.0 to expose on LAN)"
    )
    parser.add_argument(
        "--port", type=int, default=8000,
        help="Port (default: 8000)"
    )
    args = parser.parse_args()

    registry_source = "agents/registry.yaml (pyyaml)" if _YAML_AVAILABLE else "hardcoded fallback"
    agent_count = len(_registry.get("agents", []))
    engine_count = len(_registry.get("engines", []))

    print(f"[SERVE] Ghost Layer HQ Server")
    print(f"[SERVE] Registry: {registry_source} — {engine_count} engine(s), {agent_count} agent(s)")
    print(f"[SERVE] Engine:   ghost-layer-core (GhostLayerEngine)")
    print(f"[SERVE] Base URL: http://{args.host}:{args.port}")
    print(f"[SERVE] State:    in-memory only (cleared on restart)")
    print()

    server = ThreadingHTTPServer((args.host, args.port), GhostHQHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[SERVE] Shutting down.")
        server.shutdown()


if __name__ == "__main__":
    main()
