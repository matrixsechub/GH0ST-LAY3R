"""
Ghost Layer Studio — Agent HQ Registry Schema (v3)

Responsibilities:
- Define the shape of all HQ registry and runtime-event records (schema only)
- No I/O, no parsing, no wiring into the running engine
- The canonical registry data lives in agents/registry.yaml; see
  AGENT_HQ.md for the full protocol this schema supports: registration,
  routing, the HITL Governance Layer, Escalation Lifecycle, Agent Lifecycle
  & Deployment, Multi-Engine Coordination, Operator Surfaces, HQ Health &
  Observability, and Agent Pools
- See AGENT_HQ.md's "Schema versioning" section for the changelog:
  v1 -> v2: EscalationEvent, type discriminators, capabilities
  v2 -> v3: AgentDeploymentRecord, EngineHealthRecord, RoutingTableEntry,
            CapabilityIndex, AuditEvent, OperatorSessionRecord,
            AgentPool, HQHealthRecord
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, Union

AgentMode = Literal["always-on", "conditional", "manual"]
AgentStatus = Literal["active", "experimental", "deprecated", "planned"]
EngineStatus = Literal["active", "planned"]
EscalationStatus = Literal["pending", "acknowledged", "resolved", "dismissed"]
EscalationSeverity = Literal["low", "medium", "high", "critical"]


@dataclass
class EngineBinding:
    """Describes one engine an agent can be bound to."""

    id: str
    status: EngineStatus
    description: str
    entrypoint: str  # dotted Python path, e.g. "core.engine.create_default_engine"
    type: Literal["engine"] = "engine"
    capabilities: List[str] = field(default_factory=list)


@dataclass
class AgentRegistryEntry:
    """Describes one agent: identity, binding, trigger mode, and shape."""

    id: str
    name: str
    module_path: str  # dotted Python path, e.g. "agents.constellation.RouteAdvisoryAgent"
    engine: str  # EngineBinding.id this agent is bound to
    mode: AgentMode
    status: AgentStatus
    type: Literal["agent"] = "agent"
    tags: List[str] = field(default_factory=list)
    capabilities: List[str] = field(default_factory=list)
    description: str = ""
    produces: Dict[str, str] = field(default_factory=dict)


@dataclass
class OperatorEntry:
    """
    Describes the Human-In-The-Loop (HITL) operator. HQ-level, not bound to
    any single EngineBinding — see AGENT_HQ.md's "HITL Governance Layer".
    """

    operator_id: str
    role: str
    authority: str
    priority_lane: str
    escalation_required: bool
    type: Literal["operator"] = "operator"
    capabilities: List[str] = field(default_factory=list)
    binding: str = "HQ-level"


@dataclass
class EscalationEvent:
    """
    Describes one escalation raised under the HITL Governance Layer. Schema
    only — no code in this repo creates, stores, transitions, or resolves
    these. See AGENT_HQ.md's "Escalation Lifecycle" section for the state
    machine and the GOV-n -> severity mapping.
    """

    id: str
    trigger_rule: str  # e.g. "GOV-3"; references AGENT_HQ.md's GOV-n/ROUTE-n rules
    intent_id: str
    severity: EscalationSeverity
    reason: str
    agent_ids: List[str] = field(default_factory=list)  # empty if not agent-specific
    status: EscalationStatus = "pending"
    created_at: str = ""  # ISO 8601 timestamp, populated by whatever creates the event
    resolved_at: Optional[str] = None
    resolution: str = ""
    type: Literal["escalation"] = "escalation"


# ---------------------------------------------------------------------------
# v3 Type aliases
# ---------------------------------------------------------------------------

DeploymentStatus = Literal["pending", "deploying", "healthy", "degraded", "failed", "rolled_back"]
EngineHealthStatus = Literal["healthy", "degraded", "unavailable"]
AuditActorType = Literal["operator", "agent", "system"]

# Intake Agent v2 lifecycle types (see docs/intake-agent-v2-integration-plan.md)
IntakeLifecycleStage = Literal["queued", "processing", "escalated", "completed"]
IntakeOperatorAction = Literal["approve", "escalate", "close", "reassign", "annotate"]


# ---------------------------------------------------------------------------
# v3 Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class AgentDeploymentRecord:
    """
    Records one deployment of an agent into a specific engine instance.
    Registry-level AgentStatus ("active", "experimental", etc.) is a
    lifecycle marker on the spec; DeploymentStatus is the runtime state of
    a concrete deployment. Both must be tracked — an agent can be
    registry-active but currently failed in a deployment.

    State machine: pending -> deploying -> healthy
                   pending/deploying/healthy -> failed -> rolled_back
    See AGENT_HQ.md's "Agent Lifecycle & Deployment" section.
    """

    id: str
    agent_id: str       # AgentRegistryEntry.id
    engine_id: str      # EngineBinding.id
    version: str        # semver or sha ref, e.g. "1.0.0" or "b052566"
    status: DeploymentStatus
    deployed_by: str    # operator_id or system actor; must be the registered operator for GOV-4
    deployed_at: str    # ISO 8601
    rollback_to: Optional[str] = None  # version ref; MSHOPS.NET creates a new record on rollback
    ended_at: Optional[str] = None     # set when rolled_back or superseded
    notes: str = ""
    type: Literal["deployment"] = "deployment"


@dataclass
class EngineHealthRecord:
    """
    Snapshot of one engine's health at a point in time. MSHOPS.NET's
    health-check layer writes these; the HQ routing layer reads them when
    deciding whether to dispatch to an engine. See AGENT_HQ.md's
    "Multi-Engine Coordination" section.
    """

    engine_id: str          # EngineBinding.id
    status: EngineHealthStatus
    checked_at: str         # ISO 8601
    active_agent_count: int = 0
    pending_escalation_count: int = 0
    notes: str = ""
    type: Literal["engine-health"] = "engine-health"


@dataclass
class RoutingTableEntry:
    """
    Maps an intent pattern (by tag set and/or required capability) to a
    target engine. Lower priority number = higher precedence; ties broken
    by id lexicographic order. Subordinate to the HITL Governance Layer:
    ROUTE-1 through ROUTE-6 always override these entries for
    operator-originated intents or intents with open escalations. See
    AGENT_HQ.md's "Multi-Engine Coordination" section.
    """

    id: str
    target_engine_id: str       # EngineBinding.id
    priority: int               # lower = evaluated first
    active: bool = True
    match_tags: List[str] = field(default_factory=list)   # any-of match against intent tags
    match_capability: str = ""  # exact capability string; empty = not used as criterion
    description: str = ""
    type: Literal["routing-entry"] = "routing-entry"


@dataclass
class CapabilityIndex:
    """
    An index record mapping one named capability to the engines and agents
    that declare it. Populated by MSHOPS.NET from EngineBinding.capabilities
    and AgentRegistryEntry.capabilities at registration time. Rebuilt
    whenever an engine or agent is registered, updated, or deregistered.
    See AGENT_HQ.md's "Multi-Engine Coordination" section.
    """

    capability: str
    provided_by_engines: List[str] = field(default_factory=list)  # EngineBinding.id list
    provided_by_agents: List[str] = field(default_factory=list)   # AgentRegistryEntry.id list
    type: Literal["capability-index"] = "capability-index"


@dataclass
class AuditEvent:
    """
    Immutable record of a significant system action. Every state transition
    in the escalation lifecycle, every operator session open/close, every
    deployment status change, and every GOV-n rule firing must produce an
    AuditEvent. MSHOPS.NET owns the write path and persistence. Consumers
    must treat AuditEvent records as append-only — no update or delete
    endpoints exist for them. See AGENT_HQ.md's "Operator Surfaces" section.

    event_type conventions (dot-notation):
      escalation.created, escalation.status_changed,
      deployment.status_changed, operator.session_opened,
      operator.session_closed, gov_rule.fired,
      routing_table.updated, capability_index.rebuilt
    """

    id: str
    event_type: str         # dot-notation string; see docstring above
    actor_id: str           # operator_id, agent id, or system component name
    actor_type: AuditActorType
    timestamp: str          # ISO 8601
    target_id: str = ""     # id of the affected record, if any
    target_type: str = ""   # type discriminator of the affected record, e.g. "escalation"
    payload: Dict[str, Any] = field(default_factory=dict)  # event-specific details
    type: Literal["audit"] = "audit"


@dataclass
class OperatorSessionRecord:
    """
    Records one active or completed operator session. When an operator
    session is open (ended_at is None), the system applies GOV-7 posture
    (more transparency, caution, verbosity, deference). This record is the
    single authoritative signal for GOV-7 — no other mechanism determines
    operator presence. Only the registered operator (operator_id matching
    an OperatorEntry) may open or close their own session. See AGENT_HQ.md's
    "Operator Surfaces" section.
    """

    session_id: str
    operator_id: str    # must match an OperatorEntry.operator_id
    started_at: str     # ISO 8601
    ended_at: Optional[str] = None         # None = session still active
    active_intent_ids: List[str] = field(default_factory=list)
    notes: str = ""
    type: Literal["operator-session"] = "operator-session"


@dataclass
class AgentPool:
    """
    A named, ordered grouping of agents bound to one engine. Enables
    routing decisions at a group level rather than per-agent. Pool
    membership is a routing/governance concept only — AgentConstellation
    .run_all() in this repo has no pool awareness. GOV-2 (conflicting
    outputs) applies across agents within the same pool. See AGENT_HQ.md's
    "Agent Pools" section.
    """

    id: str
    name: str
    engine_id: str          # EngineBinding.id
    agent_ids: List[str] = field(default_factory=list)  # AgentRegistryEntry.id, ordered
    tags: List[str] = field(default_factory=list)       # for pool-level routing matches
    run_mode: Literal["sequential", "parallel"] = "sequential"
    description: str = ""
    type: Literal["agent-pool"] = "agent-pool"


@dataclass
class HQHealthRecord:
    """
    HQ-level health snapshot. Computed and written by MSHOPS.NET's
    health-check layer on a schedule (recommended: at least once per minute).
    operator_online is True if and only if there is an OperatorSessionRecord
    with ended_at = None for any registered operator — this is the single
    authoritative source for GOV-7 activation. degraded_engine_ids and
    unavailable_engine_ids are always disjoint. See AGENT_HQ.md's
    "HQ Health & Observability" section.
    """

    timestamp: str          # ISO 8601
    active_engine_ids: List[str] = field(default_factory=list)
    degraded_engine_ids: List[str] = field(default_factory=list)
    unavailable_engine_ids: List[str] = field(default_factory=list)
    active_agent_ids: List[str] = field(default_factory=list)
    open_escalation_count: int = 0
    operator_online: bool = False
    intake_queue_depth: int = 0
    intake_processing_count: int = 0
    intake_escalated_count: int = 0
    type: Literal["hq-health"] = "hq-health"


@dataclass
class IntakeLifecycleRecord:
    """
    Records one intake lifecycle event for an intent processed by
    IntakeAgentV2. Tracks the intent's progression through lifecycle stages
    and any operator actions taken. Append-only: each operator action or
    stage transition produces a new record rather than mutating an existing
    one. See docs/intake-agent-v2-integration-plan.md.

    Stage machine: queued -> processing -> escalated | completed
    """

    id: str
    intent_id: str
    stage: IntakeLifecycleStage
    created_at: str              # ISO 8601
    updated_at: str              # ISO 8601
    source: str = ""             # origin of the intent (operator, system, etc.)
    operator_action: Optional[IntakeOperatorAction] = None
    operator_notes: str = ""
    resolved_at: Optional[str] = None
    type: Literal["intake-lifecycle"] = "intake-lifecycle"


# ---------------------------------------------------------------------------
# RegistryRecord union (updated for v3)
# ---------------------------------------------------------------------------

# Convenience union for any consumer that reads a heterogeneous list of
# HQ records and needs to discriminate on the `type` field. Purely a
# type-checking aid — no code in this repo constructs or iterates over a
# mixed list like this.
RegistryRecord = Union[
    EngineBinding,
    AgentRegistryEntry,
    OperatorEntry,
    EscalationEvent,
    AgentDeploymentRecord,
    EngineHealthRecord,
    RoutingTableEntry,
    CapabilityIndex,
    AuditEvent,
    OperatorSessionRecord,
    AgentPool,
    HQHealthRecord,
    IntakeLifecycleRecord,
]
