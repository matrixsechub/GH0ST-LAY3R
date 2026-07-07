"""
Ghost Layer Studio — Agent HQ Registry Schema

Responsibilities:
- Define the shape of an agent/engine registry entry (schema only)
- No I/O, no parsing, no wiring into the running engine
- The canonical registry data lives in agents/registry.yaml; see
  AGENT_HQ.md for the full protocol this schema supports
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Literal

AgentMode = Literal["always-on", "conditional", "manual"]
AgentStatus = Literal["active", "experimental", "deprecated", "planned"]
EngineStatus = Literal["active", "planned"]


@dataclass
class EngineBinding:
    """Describes one engine an agent can be bound to."""

    id: str
    status: EngineStatus
    description: str
    entrypoint: str  # dotted Python path, e.g. "core.engine.create_default_engine"


@dataclass
class AgentRegistryEntry:
    """Describes one agent: identity, binding, trigger mode, and shape."""

    id: str
    name: str
    module_path: str  # dotted Python path, e.g. "agents.constellation.RouteAdvisoryAgent"
    engine: str  # EngineBinding.id this agent is bound to
    mode: AgentMode
    status: AgentStatus
    tags: List[str] = field(default_factory=list)
    description: str = ""
    produces: Dict[str, str] = field(default_factory=dict)
