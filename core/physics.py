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
# ADVANCEMENT: Engine evolution — shared type imported from the leaf module
# core.types, so this module no longer depends on core.engine (cycle removed).
from core.types import IntentVector, clamp01


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
        # ADVANCEMENT: Behavior preserved — clamp01() centralizes the [0, 1]
        # invariant. For in-range state the result is identical to the previous
        # one-sided min()/max() clamps (this is a safety refactor, not a math
        # change), and it hard-guarantees volatility can never escalate past 1.0.
        if tags.intersection(self.escalation_tags):
            state.volatility = clamp01(state.volatility + self.escalation_boost)
        else:
            state.volatility = clamp01(state.volatility - self.damping_factor)

        # Spectral density shaping (very lightweight)
        if "focus" in tags:
            state.spectral_density = clamp01(state.spectral_density + self.focus_gain)
        elif "diffuse" in tags:
            state.spectral_density = clamp01(state.spectral_density - self.diffusion_loss)

        return state
