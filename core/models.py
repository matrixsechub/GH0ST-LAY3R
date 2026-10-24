"""
Shared Ghost Layer engine data models.

Keeping these types out of the engine module prevents runtime components from
importing the engine while it is still initializing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class OperatorAxis:
    alignment: str = "operator-defensive"
    doctrine: str = "bounded-escalation"
    signature: str = "MatrixSecHub"


@dataclass
class IntentVector:
    id: str
    source: str
    description: str
    tags: List[str] = field(default_factory=list)


@dataclass
class EngineConfig:
    max_recursion: int = 3
    enable_recursion: bool = True
    telemetry: bool = True
    operator_axis: OperatorAxis = field(default_factory=OperatorAxis)
