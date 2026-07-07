"""
Ghost Layer Studio — Agent HQ Registry Schema (v2)

Responsibilities:
- Define the shape of an engine/agent/operator/escalation registry record
  (schema only)
- No I/O, no parsing, no wiring into the running engine
- The canonical registry data lives in agents/registry.yaml; see
  AGENT_HQ.md for the full protocol this schema supports: registration,
  routing, the HITL Governance Layer, and the Escalation Lifecycle
- See AGENT_HQ.md's "Schema versioning" section for the v1 -> v2 changelog
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional, Union

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


# Convenience union for any consumer that reads a heterogeneous list of
# registry records and needs to discriminate on the `type` field. Purely a
# type-checking aid — no code in this repo constructs or iterates over a
# mixed list like this.
RegistryRecord = Union[EngineBinding, AgentRegistryEntry, OperatorEntry, EscalationEvent]
