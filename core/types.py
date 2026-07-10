"""
Ghost Layer Studio — Shared Domain Types

# ADVANCEMENT: Engine evolution
This is a leaf module: it depends only on the standard library and must never
import higher-level runtime modules (e.g. core.engine, core.physics, agents.*).
Housing the shared domain types here breaks the historical circular dependency
(physics/oversoul/output/constellation <-> engine) at its source, replacing the
temporary ``TYPE_CHECKING`` import guards with a clean, one-directional import DAG.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List

# ADVANCEMENT: Engine evolution — single source of truth for the engine version.
ENGINE_VERSION = "1.1.0"


# ADVANCEMENT: Engine evolution — centralized [0, 1] clamp for the
# spectral-density / volatility invariants shared across physics, oversoul,
# and the agent constellation.
def clamp01(x: float) -> float:
    """Clamp ``x`` into the closed interval [0.0, 1.0] and return a float."""
    return float(min(1.0, max(0.0, x)))


@dataclass
class OperatorAxis:
    # ADVANCEMENT: Engine evolution — moved from core.engine, semantics preserved.
    alignment: str = "operator-defensive"
    doctrine: str = "bounded-escalation"
    signature: str = "MatrixSecHub"


@dataclass
class IntentVector:
    # ADVANCEMENT: Engine evolution — moved from core.engine, semantics preserved.
    id: str
    source: str
    description: str
    tags: List[str] = field(default_factory=list)
