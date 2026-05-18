"""
Ghost Layer Studio — Dominion Physics

Defines the "laws" that govern how the substrate evolves:
- Applies constraints and transformations to SubstrateState
- Uses intent tags + metadata to modulate volatility and density
- Encodes simple escalation / de-escalation behavior
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol

from core.substrate import SubstrateState
from core.engine import IntentVector  # if IntentVector lives in engine.py


class DominionPhysics(Protocol):
    """
    Interface for dominion physics.

    Any implementation must define how to transform SubstrateState
    given the current IntentVector.
    """

    def apply(self, intent: IntentVector, state: SubstrateState) -> SubstrateState:
        ...


@dataclass
class DefaultDominionPhysics:
    """
    Default dominion physics for Ghost Layer Studio.

    Behavior:
    - If intent is tagged as high-risk / escalation, allow higher volatility
    - If intent is routine / low-risk, dampen volatility
    - Slightly adjust spectral density to simulate "focus" or "diffusion"
    """

    escalation_tags: tuple[str, ...] = ("high-risk", "escalate", "critical")
    damping_factor: float = 0.05
    escalation_boost: float = 0.25
    focus_gain: float = 0.02
    diffusion_loss: float = 0.02

    def apply(self, intent: IntentVector, state: SubstrateState) -> SubstrateState:
        tags = set(intent.tags)

        # Volatility shaping
        if tags.intersection(self.escalation_tags):
            state.volatility = min(1.0, state.volatility + self.escalation_boost)
        else:
            state.volatility = max(0.0, state.volatility - self.damping_factor)

        # Spectral density shaping (very lightweight)
        if "focus" in tags:
            state.spectral_density = min(1.0, state.spectral_density + self.focus_gain)
        elif "diffuse" in tags:
            state.spectral_density = max(0.0, state.spectral_density - self.diffusion_loss)

        return state
