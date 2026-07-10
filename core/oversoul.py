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
from typing import Any, Dict, List

from core.substrate import SubstrateState
# ADVANCEMENT: Engine evolution — shared type imported from the leaf module
# core.types, so this module no longer depends on core.engine (cycle removed).
from core.types import IntentVector, clamp01


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

        # ADVANCEMENT: Behavior preserved
        Reimplemented from Python recursion to a bounded iterative loop. The
        emitted ``recursion_trace`` entries, the ``+0.01`` clamped refinement,
        and the terminal ``recursion_complete`` marker are byte-for-byte
        identical to the previous recursive implementation, but iteration
        guarantees deterministic termination and cannot exhaust Python's call
        stack even for a very large ``max_depth``. A negative ``max_depth`` is
        guarded to a no-op (zero cycles), matching the old ``depth >= max_depth``
        short-circuit.
        """
        if not self.config.enable_recursion:
            return fused

        # ADVANCEMENT: Behavior preserved — guard non-positive bounds; range()
        # naturally yields zero cycles, exactly like the old base-case return.
        bounded_max = max_depth if max_depth > 0 else 0

        # ADVANCEMENT: Behavior preserved — the "recursion_trace" key is created
        # lazily on first append (as before), so a zero-cycle run yields only
        # the terminal marker with no empty trace list.
        for current_depth in range(depth, bounded_max):
            fused.setdefault("recursion_trace", []).append(
                {
                    "depth": current_depth,
                    "spectral_density": state.spectral_density,
                    "volatility": state.volatility,
                }
            )
            # Simulate refinement (clamped to the [0, 1] invariant).
            state.spectral_density = clamp01(state.spectral_density + 0.01)

        fused["recursion_complete"] = True
        return fused
