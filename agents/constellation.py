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
from typing import Any, Dict, List, Protocol

from core.substrate import SubstrateState
# ADVANCEMENT: Engine evolution — shared type imported from the leaf module
# core.types, so this module no longer depends on core.engine (cycle removed).
from core.types import IntentVector, clamp01


# ---------------------------------------------------------------------------
# Agent Protocol
# ---------------------------------------------------------------------------

class Agent(Protocol):
    name: str
    # ADVANCEMENT: Engine evolution — explicit, deterministic activation order.
    # Lower `priority` runs earlier; equal priorities keep registration order.
    priority: int

    def supports(self, intent: IntentVector, state: SubstrateState) -> bool:
        """Return True if this agent should activate."""
        ...

    def run(self, intent: IntentVector, state: SubstrateState) -> Dict[str, Any]:
        """Return structured output for Oversoul fusion.

        Agents are read-only observers: implementations MUST NOT mutate
        ``state`` (spectral density / volatility) or ``intent``.
        """
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
        """Return all agents that support the current intent/state.

        # ADVANCEMENT: Engine evolution — active agents are ordered by
        # ``priority`` using a stable sort, so equal priorities preserve
        # registration order (the pre-existing default run order is unchanged).
        """
        active = [a for a in self.agents if a.supports(intent, state)]
        return sorted(active, key=lambda a: getattr(a, "priority", 100))

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
    priority: int = 100  # ADVANCEMENT: Behavior preserved — default keeps run order.

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
    priority: int = 100  # ADVANCEMENT: Behavior preserved — default keeps run order.

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
    priority: int = 100  # ADVANCEMENT: Behavior preserved — default keeps run order.

    def supports(self, intent: IntentVector, state: SubstrateState) -> bool:
        return True  # always active

    def run(self, intent: IntentVector, state: SubstrateState) -> Dict[str, Any]:
        return {
            "doctrine": "bounded-escalation",
            "intent_tags": intent.tags,
            "spectral_density": state.spectral_density,
        }


# ---------------------------------------------------------------------------
# ADVANCEMENT: Engine evolution — new conditionally-activating agents
# ---------------------------------------------------------------------------
# Both agents are read-only observers (they never mutate `state` or `intent`)
# and are deterministic. Their activation thresholds are deliberately above the
# default demo's volatility (0.0), so the default run output is unchanged; they
# only join the constellation on higher-volatility inputs.

@dataclass
class PredictiveAgent:
    """
    Forecasts the next-cycle volatility trend from the current spectral density
    and volatility. Activates only for non-trivial volatility.
    """
    name: str = "PredictiveAgent"
    priority: int = 120
    activation_threshold: float = 0.3

    def supports(self, intent: IntentVector, state: SubstrateState) -> bool:
        # ADVANCEMENT: Engine evolution — conditional activation.
        return state.volatility > self.activation_threshold

    def run(self, intent: IntentVector, state: SubstrateState) -> Dict[str, Any]:
        # Deterministic projection: higher spectral density (focus) damps the
        # projected volatility for the next cycle. Bounded to [0, 1].
        forecast_volatility = clamp01(state.volatility - 0.05 * state.spectral_density)
        if forecast_volatility < state.volatility:
            trend = "falling"
        elif forecast_volatility > state.volatility:
            trend = "rising"
        else:
            trend = "steady"
        return {
            "forecast_volatility": forecast_volatility,
            "trend": trend,
            "confidence": clamp01(state.spectral_density),
            "basis": {
                "volatility": state.volatility,
                "spectral_density": state.spectral_density,
            },
        }


@dataclass
class StabilityAgent:
    """
    Emits a bounded stability score for mid-band volatility, where the system is
    neither calm nor fully saturated and stabilization guidance is most useful.
    """
    name: str = "StabilityAgent"
    priority: int = 130
    lower_bound: float = 0.2
    upper_bound: float = 0.85

    def supports(self, intent: IntentVector, state: SubstrateState) -> bool:
        # ADVANCEMENT: Engine evolution — conditional activation (mid-band only).
        return self.lower_bound < state.volatility < self.upper_bound

    def run(self, intent: IntentVector, state: SubstrateState) -> Dict[str, Any]:
        # Deterministic, bounded score: calmer (low volatility) and more focused
        # (high spectral density) states score as more stable. Always in [0, 1].
        stability_score = clamp01(
            0.5 * (1.0 - state.volatility) + 0.5 * state.spectral_density
        )
        return {
            "stability_score": stability_score,
            "status": "stable" if stability_score >= 0.5 else "unstable",
            "volatility": state.volatility,
            "spectral_density": state.spectral_density,
        }
