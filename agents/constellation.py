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

A "module" in the Ghost Layer sense is simply an object implementing the
Agent protocol below; there is no separate module abstraction.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Protocol

from core.substrate import SubstrateState
from core.types import IntentVector


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


@dataclass
class RouteAdvisoryAgent:
    """
    Suggests which future Ghost Layer subsystem an intent would plausibly
    route to, based on lightweight tag/volatility heuristics. Advisory only —
    does not perform any actual routing or call any external system.
    """
    name: str = "RouteAdvisoryAgent"

    def supports(self, intent: IntentVector, state: SubstrateState) -> bool:
        return True  # always active, like OperatorDoctrineAgent

    def run(self, intent: IntentVector, state: SubstrateState) -> Dict[str, Any]:
        tags = set(intent.tags)
        if tags.intersection({"high-risk", "escalate", "critical"}):
            suggested_lane = "containment-review"
        elif state.volatility > 0.5:
            suggested_lane = "adversarial-intel"
        else:
            suggested_lane = "general-intake"

        return {
            "suggested_lane": suggested_lane,
            "confidence": "heuristic",
            "basis": {
                "intent_tags": intent.tags,
                "volatility": state.volatility,
            },
        }


@dataclass
class IntakeAgentV2:
    """
    Classifies intents into lifecycle stages and exposes queue metrics for
    HQ observability. Operator-action hooks (approve, escalate, close,
    reassign, annotate) are surfaced through ttx-operator-shell's HQ console.

    GOV-4 gate: this class is defined here but NOT registered in
    create_default_engine() — that registration requires operator approval.
    Status: experimental (see agents/registry.yaml id: intake-agent-v2).
    See docs/intake-agent-v2-integration-plan.md for the full plan.
    """
    name: str = "IntakeAgentV2"
    _ESCALATION_TAGS: tuple = ("high-risk", "escalate", "critical")

    def supports(self, intent: IntentVector, state: SubstrateState) -> bool:
        return True  # always-on once registered (GOV-4 gate is at registration)

    def run(self, intent: IntentVector, state: SubstrateState) -> Dict[str, Any]:
        tags = set(intent.tags)
        needs_escalation = bool(tags.intersection(self._ESCALATION_TAGS)) or state.volatility >= 0.8
        if needs_escalation:
            stage = "escalated"
            operator_action_required = True
            available_actions = ["escalate", "close", "reassign", "annotate"]
        else:
            stage = "processing"
            operator_action_required = False
            available_actions = ["approve", "close", "annotate"]

        return {
            "intake_status": "received",
            "lifecycle_stage": stage,
            "queue_depth": 0,   # placeholder; real count managed by serve.py _intake_lifecycle
            "operator_action_required": operator_action_required,
            "operator_actions_available": available_actions,
        }
