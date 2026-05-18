"""
Ghost Layer Studio — Substrate Ingestion Module

Transforms raw input into a structured SubstrateState:
- Normalizes raw signals
- Extracts lightweight features
- Computes spectral density + volatility
- Attaches contextual metadata for downstream agents
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
import math
import time


@dataclass
class SubstrateState:
    spectral_density: float = 0.0
    volatility: float = 0.0
    context: Dict[str, Any] = field(default_factory=dict)


class SubstrateIngestion:
    """
    Ingestion pipeline for Ghost Layer Studio.

    Responsibilities:
    - Accept raw input (text, dict, list, etc.)
    - Normalize into canonical form
    - Compute signal metrics
    - Populate SubstrateState for the engine
    """

    def ingest(self, raw: Any, state: Optional[SubstrateState] = None) -> SubstrateState:
        state = state or SubstrateState()

        normalized, meta = self._normalize(raw)
        metrics = self._compute_metrics(normalized, meta)

        state.context["raw"] = raw
        state.context["normalized"] = normalized
        state.context["meta"] = meta
        state.context["metrics"] = metrics

        state.spectral_density = metrics["spectral_density"]
        state.volatility = metrics["volatility"]

        return state

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _normalize(self, raw: Any) -> tuple[str, Dict[str, Any]]:
        """Normalize raw input into a string and attach metadata."""
        if isinstance(raw, str):
            text = raw.strip()
            kind = "text"
        elif isinstance(raw, dict):
            text = str(raw)
            kind = "dict"
        elif isinstance(raw, (list, tuple)):
            text = " ".join(map(str, raw))
            kind = "sequence"
        else:
            text = str(raw)
            kind = type(raw).__name__

        meta = {
            "kind": kind,
            "length": len(text),
            "timestamp": time.time(),
        }

        return text, meta

    def _compute_metrics(self, text: str, meta: Dict[str, Any]) -> Dict[str, float]:
        """Compute spectral density + volatility from normalized text."""
        tokens = text.split()
        token_count = len(tokens) or 1
        unique_tokens = len(set(tokens)) or 1

        # Information density
        spectral_density = min(1.0, (unique_tokens / token_count) ** 0.5)

        # Volatility: punctuation + caps intensity
        exclam = text.count("!")
        quest = text.count("?")
        caps = sum(1 for t in tokens if len(t) > 3 and t.isupper())

        volatility_score = exclam + quest + caps * 0.5
        volatility = max(0.0, min(1.0, math.tanh(volatility_score / 5.0)))

        return {
            "spectral_density": spectral_density,
            "volatility": volatility,
        }
