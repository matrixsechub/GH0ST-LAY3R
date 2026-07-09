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
    POST /intents                          — run engine, GOV-7 header support, routing table checked
    GET  /hq/health                        — computed HQHealthRecord (includes all intake counts)
    GET  /audit                            — AuditEvent[] (filter: event_type, actor_id, since)
    GET  /escalations                      — EscalationEvent[] (filter: status, severity)
    GET  /agents                           — agents from registry.yaml
    GET  /engines                          — engines from registry.yaml
    GET  /operators                        — operators from registry.yaml
    GET  /agent-pools                      — in-memory AgentPool[] (empty initially)
    GET  /agents/intake-agent-v2           — registry entry for intake-agent-v2
    GET  /intake-agent-v2/lifecycle        — IntakeLifecycleRecord[] (append-only, since server start)
    GET  /intake-agent-v2/metrics          — all stage counts (received/validated/queued/processed/…)
    POST /api/register                     — submit intake; creates IntakeLifecycleRecord stage=received
    GET  /marketplace                      — lifecycle-aware banner (observer/full/review mode)
    POST /intake-agent-v2/lifecycle/transition — advance stage: received→validated→queued→processed
    GET  /cockpit/intake                   — read-only panel stub (status, timeline, last 10 submissions)

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

# Routing table: seeded at startup; NOT constellation activation (GOV-4 gate).
# IntakeAgentV2 handles these tags via routing-only mode until GOV-4 is lifted.
# See IntakeAgentV2.ROUTING_TAGS in agents/constellation.py.
_routing_table: list = [
    {
        "id": "rt-intake-submissions",
        "type": "routing-entry",
        "target_engine_id": "ghost-layer-core",
        "target_agent_id": "intake-agent-v2",
        "priority": 10,
        "active": True,
        "match_tags": ["intake", "register"],
        "match_capability": "intent-intake",
        "description": "Route intake submissions and register tags to IntakeAgentV2",
    },
    {
        "id": "rt-access-requests",
        "type": "routing-entry",
        "target_engine_id": "ghost-layer-core",
        "target_agent_id": "intake-agent-v2",
        "priority": 10,
        "active": True,
        "match_tags": ["access-request"],
        "match_capability": "",
        "description": "Route access requests to IntakeAgentV2",
    },
    {
        "id": "rt-paywall-transitions",
        "type": "routing-entry",
        "target_engine_id": "ghost-layer-core",
        "target_agent_id": "intake-agent-v2",
        "priority": 10,
        "active": True,
        "match_tags": ["paywall"],
        "match_capability": "",
        "description": "Route paywall transitions to IntakeAgentV2",
    },
    {
        "id": "rt-register-transitions",
        "type": "routing-entry",
        "target_engine_id": "ghost-layer-core",
        "target_agent_id": "intake-agent-v2",
        "priority": 15,
        "active": True,
        "match_tags": ["register-transition"],
        "match_capability": "",
        "description": "Route register transitions to IntakeAgentV2",
    },
]

# Valid stage transitions for the TTX intake flow (received→validated→queued→processed).
# Escalation transitions are future work — not implemented in this rev.
_INTAKE_VALID_TRANSITIONS: dict = {
    "received":  {"validated"},
    "validated": {"queued"},
    "queued":    {"processed"},
}


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


def _check_routing_table(tags: list) -> list:
    """Return active routing entries whose match_tags intersect the provided tags."""
    tag_set = set(tags)
    matched = []
    for entry in sorted(_routing_table, key=lambda e: e.get("priority", 100)):
        if not entry.get("active"):
            continue
        if tag_set.intersection(entry.get("match_tags", [])):
            matched.append(entry)
    return matched


def _marketplace_state(latest_stage: str | None) -> dict:
    """Map the most recent intake lifecycle stage to a marketplace access mode."""
    if latest_stage in ("validated",):
        return {
            "mode": "full",
            "access": True,
            "banner": None,
        }
    if latest_stage in ("escalated",):
        return {
            "mode": "review",
            "access": False,
            "banner": (
                "IntakeAgentV2: Operator Review in Progress — "
                "Access suspended pending resolution."
            ),
        }
    # received / queued / processed / pending / None → observer
    return {
        "mode": "observer",
        "access": False,
        "banner": "IntakeAgentV2: Access Pending — You are in Observer Mode.",
    }


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
    def _stage_count(stage: str) -> int:
        return sum(1 for r in _intake_lifecycle if r.get("stage") == stage)

    return {
        "type": "hq-health",
        "timestamp": _now(),
        "active_engine_ids": active_engine_ids,
        "degraded_engine_ids": [],
        "unavailable_engine_ids": [],
        "active_agent_ids": active_agent_ids,
        "open_escalation_count": open_escalation_count,
        "operator_online": _operator_online(),
        # pre-TTX intake fields
        "intake_queue_depth": _stage_count("queued"),
        "intake_processing_count": _stage_count("processing"),
        "intake_escalated_count": _stage_count("escalated"),
        # TTX intake flow fields
        "intake_received_count": _stage_count("received"),
        "intake_validated_count": _stage_count("validated"),
        "intake_processed_count": _stage_count("processed"),
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
            elif path == "/marketplace":
                self._get_marketplace(params)
            elif path == "/cockpit/intake":
                self._get_cockpit_intake()
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
        elif path == "/api/register":
            self._post_register(body)
        elif path == "/intake-agent-v2/lifecycle/transition":
            self._post_lifecycle_transition(body)
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

            # Routing table check — advisory, not constellation activation.
            routing_matches = _check_routing_table(request_tags)
            routing_info = [
                {"entry_id": e["id"], "target_agent_id": e.get("target_agent_id")}
                for e in routing_matches
            ]

            _write_audit(
                "intent.submitted",
                actor_id=op_id if gov7_active else source,
                actor_type="operator" if gov7_active else "system",
                target_id=intent_id,
                target_type="intent",
                payload={
                    "source": source,
                    "gov7_active": gov7_active,
                    "routing_matches": routing_info,
                },
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

    def _post_register(self, body: dict) -> None:
        """
        POST /api/register — public intake submission entry point.
        Creates an IntakeLifecycleRecord at stage 'received', logs an
        intake.stage_changed AuditEvent, and returns the record.
        No auth — this is the unauthenticated public → intake boundary.
        """
        source = body.get("source", "public")
        raw = body.get("raw", "")
        intent_id = body.get("intent_id") or str(uuid.uuid4())
        notes = body.get("notes", "")

        if not raw and not body:
            _send_error(self, 400, "'raw' or a non-empty body is required")
            return

        now = _now()
        record: dict = {
            "id": str(uuid.uuid4()),
            "type": "intake-lifecycle",
            "intent_id": intent_id,
            "stage": "received",
            "created_at": now,
            "updated_at": now,
            "source": source,
            "operator_action": None,
            "operator_notes": notes,
            "resolved_at": None,
        }

        with _lock:
            _intake_lifecycle.append(record)
            _write_audit(
                "intake.stage_changed",
                actor_id=source,
                actor_type="system",
                target_id=record["id"],
                target_type="intake-lifecycle",
                payload={"intent_id": intent_id, "stage": "received", "from_stage": None},
            )

        _send_json(self, 201, {
            "lifecycle": record,
            "marketplace": _marketplace_state("received"),
        })

    def _get_marketplace(self, params: dict) -> None:
        """
        GET /marketplace — return lifecycle-aware marketplace access state.
        No auth: returns state based on the most recent IntakeLifecycleRecord.
        If no records exist, returns observer mode (default).
        """
        with _lock:
            records = list(_intake_lifecycle)

        latest_stage: str | None = None
        if records:
            latest_stage = records[-1].get("stage")

        state = _marketplace_state(latest_stage)
        _send_json(self, 200, {
            "type": "marketplace-state",
            "mode": state["mode"],
            "access": state["access"],
            "banner": state["banner"],
            "latest_intake_stage": latest_stage,
            "total_submissions": len(records),
        })

    def _post_lifecycle_transition(self, body: dict) -> None:
        """
        POST /intake-agent-v2/lifecycle/transition
        Body: {"lifecycle_id": "...", "to_stage": "validated", "notes": "..."}
        Validates the transition against _INTAKE_VALID_TRANSITIONS and
        appends a new IntakeLifecycleRecord (append-only; does not mutate).
        """
        lifecycle_id = body.get("lifecycle_id", "")
        to_stage = body.get("to_stage", "")
        notes = body.get("notes", "")

        if not lifecycle_id or not to_stage:
            _send_error(self, 400, "'lifecycle_id' and 'to_stage' are required")
            return

        with _lock:
            source_record = next(
                (r for r in _intake_lifecycle if r.get("id") == lifecycle_id), None
            )
            if source_record is None:
                _send_error(self, 404, f"No lifecycle record: {lifecycle_id}")
                return

            from_stage = source_record.get("stage", "")
            allowed = _INTAKE_VALID_TRANSITIONS.get(from_stage, set())
            if to_stage not in allowed:
                _send_error(
                    self, 422,
                    f"Transition '{from_stage}' → '{to_stage}' not allowed. "
                    f"Valid next stages: {sorted(allowed) or 'none (terminal)'}",
                )
                return

            now = _now()
            new_record: dict = {
                "id": str(uuid.uuid4()),
                "type": "intake-lifecycle",
                "intent_id": source_record.get("intent_id", ""),
                "stage": to_stage,
                "created_at": now,
                "updated_at": now,
                "source": source_record.get("source", ""),
                "operator_action": None,
                "operator_notes": notes,
                "resolved_at": now if to_stage == "processed" else None,
            }
            _intake_lifecycle.append(new_record)
            _write_audit(
                "intake.stage_changed",
                actor_id="system",
                actor_type="system",
                target_id=new_record["id"],
                target_type="intake-lifecycle",
                payload={
                    "intent_id": new_record["intent_id"],
                    "from_stage": from_stage,
                    "stage": to_stage,
                    "previous_record_id": lifecycle_id,
                },
            )

        _send_json(self, 200, {
            "previous": source_record,
            "current": new_record,
            "marketplace": _marketplace_state(to_stage),
        })

    def _get_cockpit_intake(self) -> None:
        """
        GET /cockpit/intake — read-only operator cockpit panel stub.
        Returns: agent status, lifecycle timeline (all records), last 10 submissions.
        Read-only until GOV-4 lift — no write endpoints exposed here.
        """
        with _lock:
            records = list(_intake_lifecycle)
            metrics = {}
            for r in records:
                s = r.get("stage", "unknown")
                metrics[s] = metrics.get(s, 0) + 1

        agent_entry = next(
            (a for a in _registry.get("agents", []) if a.get("id") == "intake-agent-v2"),
            {"id": "intake-agent-v2", "status": "not-in-registry"},
        )

        _send_json(self, 200, {
            "type": "cockpit-panel",
            "panel": "intake-agent-v2",
            "agent_status": agent_entry.get("status", "unknown"),
            "gov4_status": "routing-active; constellation activation pending operator approval",
            "routing_table_entries": len(_routing_table),
            "stage_counts": metrics,
            "lifecycle_timeline": records,
            "last_10_submissions": [
                r for r in records if r.get("stage") == "received"
            ][-10:],
            "note": "Read-only until GOV-4 lift. Operator actions available after promotion.",
        })

    def _get_intake_metrics(self) -> None:
        records = list(_intake_lifecycle)
        by_stage: dict = {}
        for r in records:
            s = r.get("stage", "unknown")
            by_stage[s] = by_stage.get(s, 0) + 1
        _send_json(self, 200, {
            # TTX flow counts
            "received_count": by_stage.get("received", 0),
            "validated_count": by_stage.get("validated", 0),
            "queued_count": by_stage.get("queued", 0),
            "processed_count": by_stage.get("processed", 0),
            # legacy / future counts
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
