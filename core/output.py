"""
Ghost Layer Studio — Output Reactor

Final shaping layer before results leave the engine.

Responsibilities:
- Wrap fused Oversoul output in a structured envelope
- Attach operator + substrate metadata
- Provide a consistent, extensible output format
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
import time

from core.substrate import SubstrateState
# ADVANCEMENT: Engine evolution — shared type imported from the leaf module
# core.types, so this module no longer depends on core.engine (cycle removed).
from core.types import IntentVector, ENGINE_VERSION


@dataclass
class OutputEnvelope:
    """
    Canonical output structure for Ghost Layer Studio.
    """
    intent_id: str
    source: str
    operator_axis: str
    spectral_density: float
    volatility: float
    payload: Dict[str, Any]
    timestamp: float = field(default_factory=lambda: time.time())
    meta: Dict[str, Any] = field(default_factory=dict)
    # ADVANCEMENT: Engine evolution — additive top-level version stamp.
    engine_version: str = ENGINE_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent_id": self.intent_id,
            "source": self.source,
            "operator_axis": self.operator_axis,
            "spectral_density": self.spectral_density,
            "volatility": self.volatility,
            "payload": self.payload,
            "timestamp": self.timestamp,
            "meta": self.meta,
            # ADVANCEMENT: Behavior preserved — existing keys are untouched;
            # engine_version is a new additive field.
            "engine_version": self.engine_version,
        }


class OutputReactor:
    """
    Output reactor for Ghost Layer Studio.

    This is where:
    - Final payload is wrapped
    - Extra metadata can be attached
    - Different output modes (raw, debug, minimal) can be added later
    """

    def __init__(self, operator_axis: str = "operator-defensive") -> None:
        self.operator_axis = operator_axis

    def emit(
        self,
        intent: IntentVector,
        state: SubstrateState,
        fused_output: Dict[str, Any],
        *,
        extra_meta: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Build and return the final output envelope as a dict.

        # ADVANCEMENT: Behavior preserved — the pre-existing ``intent_tags``
        # meta entry is always present; ``extra_meta`` only adds new keys.
        """
        meta: Dict[str, Any] = {
            "intent_tags": intent.tags,
        }
        if extra_meta:
            meta.update(extra_meta)

        envelope = OutputEnvelope(
            intent_id=intent.id,
            source=intent.source,
            operator_axis=self.operator_axis,
            spectral_density=state.spectral_density,
            volatility=state.volatility,
            payload=fused_output,
            meta=meta,
        )
        return envelope.to_dict()
