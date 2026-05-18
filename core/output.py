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
from typing import Any, Dict
import time

from core.substrate import SubstrateState
from core.engine import IntentVector  # where IntentVector currently lives


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
    ) -> Dict[str, Any]:
        """
        Build and return the final output envelope as a dict.
        """
        envelope = OutputEnvelope(
            intent_id=intent.id,
            source=intent.source,
            operator_axis=self.operator_axis,
            spectral_density=state.spectral_density,
            volatility=state.volatility,
            payload=fused_output,
            meta={
                "intent_tags": intent.tags,
            },
        )
        return envelope.to_dict()
