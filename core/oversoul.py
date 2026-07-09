"""
Ghost Layer Studio — Oversoul Substrate

The Oversoul is the meta‑reasoning layer that:
- Fuses outputs from the agent constellation
- Applies high‑level synthesis rules
- Performs controlled recursion cycles
- Shapes the final payload before the engine synthesizes it

This is intentionally lightweight but extensible.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, TYPE_CHECKING

from core.substrate import SubstrateState

if TYPE_CHECKING:
    from core.engine import IntentVector  # if IntentVector lives in engine.py


@dataclass
class OversoulConfig:
    """Configuration for recursion behavior."""
    max_depth: int = 3
    enable_recursion: bool = True


class Oversoul:
    """
    Base protocol-like class for Oversoul implementations.
    """

    def absorb(
        self,
        intent: IntentVector,
        state: SubstrateState,
        agent_outputs: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        raise NotImplementedError

    def recurse(
        self,
        intent: IntentVector,
        state: SubstrateState,
        fused: Dict[str, Any],
        depth: int,
        max_depth: int,
    ) -> Dict[str, Any]:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Default Implementation
# ---------------------------------------------------------------------------

@dataclass
class DefaultOversoul(Oversoul):
    """
    Default Oversoul for Ghost Layer Studio.

    Behavior:
    - Fuses agent outputs into a single structure
    - Adds lightweight meta‑analysis
    - Performs shallow recursion (depth-limited)
    """

    config: OversoulConfig = field(default_factory=OversoulConfig)

    def absorb(
        self,
        intent: IntentVector,
        state: SubstrateState,
        agent_outputs: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Fuse agent outputs into a single structure.
        """
        fused = {
            "agent_count": len(agent_outputs),
            "agents": agent_outputs,
            "meta": {
                "spectral_density": state.spectral_density,
                "volatility": state.volatility,
                "intent_tags": intent.tags,
            },
        }
        return fused

    def recurse(
        self,
        intent: IntentVector,
        state: SubstrateState,
        fused: Dict[str, Any],
        depth: int,
        max_depth: int,
    ) -> Dict[str, Any]:
        """
        Controlled recursion loop.

        Each recursion cycle:
        - Adds a new layer of meta‑context
        - Slightly adjusts spectral density to simulate "refinement"
        - Stops at max_depth
        """
        if not self.config.enable_recursion:
            return fused

        if depth >= max_depth:
            fused["recursion_complete"] = True
            return fused

        # Add a recursion layer
        fused.setdefault("recursion_trace", []).append(
            {
                "depth": depth,
                "spectral_density": state.spectral_density,
                "volatility": state.volatility,
            }
        )

        # Simulate refinement
        state.spectral_density = min(1.0, state.spectral_density + 0.01)

        # Recurse deeper
        return self.recurse(
            intent=intent,
            state=state,
            fused=fused,
            depth=depth + 1,
            max_depth=max_depth,
        )
