"""
Ghost Layer Studio — Agent Constellation

Defines:
- Base Agent protocol
- Constellation registry
- Example operator-grade agents

Agents are modular intelligence operators that:
- Observe substrate state
- Decide if they should activate
- Produce structured outputs for the Oversoul to fuse
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Protocol, TYPE_CHECKING

from core.substrate import SubstrateState

if TYPE_CHECKING:
    from core.engine import IntentVector


# ---------------------------------------------------------------------------
# Agent Protocol
# ---------------------------------------------------------------------------

class Agent(Protocol):
    name: str

    def supports(self, intent: IntentVector, state: SubstrateState) -> bool:
        """Return True if this agent should activate."""
        ...

    def run(self, intent: IntentVector, state: SubstrateState) -> Dict[str, Any]:
        """Return structured output for Oversoul fusion."""
        ...


# ---------------------------------------------------------------------------
# Constellation Registry
# ---------------------------------------------------------------------------

@dataclass
class AgentConstellation:
    """
    Holds and manages all agents in the system.
    """

    agents: List[Agent]

    def active_agents(self, intent: IntentVector, state: SubstrateState) -> List[Agent]:
        """Return all agents that support the current intent/state."""
        return [a for a in self.agents if a.supports(intent, state)]

    def run_all(self, intent: IntentVector, state: SubstrateState) -> List[Dict[str, Any]]:
        """Run all active agents and collect outputs."""
        outputs = []
        for agent in self.active_agents(intent, state):
            try:
                outputs.append({
                    "agent": agent.name,
                    "result": agent.run(intent, state)
                })
            except Exception as e:
                outputs.append({
                    "agent": agent.name,
                    "error": str(e)
                })
        return outputs


# ---------------------------------------------------------------------------
# Example Agents (Operator-Grade)
# ---------------------------------------------------------------------------

@dataclass
class AdversarialIntelAgent:
    """
    Reads substrate volatility + density to detect adversarial signals.
    """
    name: str = "AdversarialIntelAgent"

    def supports(self, intent: IntentVector, state: SubstrateState) -> bool:
        return state.volatility > 0.4

    def run(self, intent: IntentVector, state: SubstrateState) -> Dict[str, Any]:
        return {
            "threat_level": "elevated" if state.volatility > 0.7 else "moderate",
            "spectral_density": state.spectral_density,
            "volatility": state.volatility,
        }


@dataclass
class ContainmentAgent:
    """
    Activates when volatility is high or intent contains escalation tags.
    """
    name: str = "ContainmentAgent"
    escalation_tags: tuple[str, ...] = ("high-risk", "escalate", "critical")

    def supports(self, intent: IntentVector, state: SubstrateState) -> bool:
        return (
            state.volatility > 0.6
            or any(tag in intent.tags for tag in self.escalation_tags)
        )

    def run(self, intent: IntentVector, state: SubstrateState) -> Dict[str, Any]:
        return {
            "containment_action": "stabilize",
            "volatility_before": state.volatility,
            "recommended_clamp": max(0.0, state.volatility - 0.3),
        }


@dataclass
class OperatorDoctrineAgent:
    """
    Applies operator-axis doctrine to shape interpretation.
    """
    name: str = "OperatorDoctrineAgent"

    def supports(self, intent: IntentVector, state: SubstrateState) -> bool:
        return True  # always active

    def run(self, intent: IntentVector, state: SubstrateState) -> Dict[str, Any]:
        return {
            "doctrine": "bounded-escalation",
            "intent_tags": intent.tags,
            "spectral_density": state.spectral_density,
        }
